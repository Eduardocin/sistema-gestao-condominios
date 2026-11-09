"""Consultas do módulo de permissões por aba (US-304). Só aqui se fala com o banco.

Todos herdam de `RepositorioDoCondominio`: o filtro por condomínio vem junto (R3). Os selects
partem de `self.consulta()` ou de `self._do_condominio()`, nunca de um `select` solto.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.unidades.models import MoradorUnidade, PermissaoAba, Unidade
from app.modules.usuarios.models import Usuario


class RepositorioUnidades(RepositorioDoCondominio[Unidade]):
    modelo = Unidade

    def bloquear(self, unidade_id: uuid.UUID) -> None:
        """Tranca a unidade até o fim da transação (ou 404 se ela não for deste condomínio).

        Serve para duas pessoas não retirarem a aba Usuários uma da outra ao mesmo tempo: sem a
        tranca, cada uma enxergaria a outra Com Acesso e a unidade ficaria sem ninguém. Usamos
        `FOR NO KEY UPDATE` (e não `FOR UPDATE`) para não atrapalhar quem só referencia a unidade
        por chave estrangeira, como o vínculo de um morador novo.
        """
        consulta = self.consulta().where(Unidade.id == unidade_id).with_for_update(key_share=True)
        if self.session.scalar(consulta) is None:
            raise RecursoNaoEncontrado


class RepositorioMoradores(RepositorioDoCondominio[MoradorUnidade]):
    modelo = MoradorUnidade

    def _ativos_da_unidade(self, unidade_id: uuid.UUID) -> Select[tuple[MoradorUnidade]]:
        return self.consulta().where(
            MoradorUnidade.unidade_id == unidade_id, MoradorUnidade.status == "ativo"
        )

    def contar_da_unidade(self, unidade_id: uuid.UUID) -> int:
        consulta = select(func.count()).select_from(self._ativos_da_unidade(unidade_id).subquery())
        return self.session.scalar(consulta) or 0

    def listar_da_unidade(
        self, unidade_id: uuid.UUID, *, limite: int, deslocamento: int
    ) -> list[tuple[MoradorUnidade, str]]:
        """Moradores ativos da unidade com o nome da conta. Mais recentes primeiro, ID desempata."""
        consulta = (
            self._ativos_da_unidade(unidade_id)
            .add_columns(Usuario.nome)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
            .order_by(MoradorUnidade.vinculado_em.desc(), MoradorUnidade.id)
            .limit(limite)
            .offset(deslocamento)
        )
        return [(morador, nome) for morador, nome in self.session.execute(consulta).tuples()]

    def obter_da_unidade(
        self, unidade_id: uuid.UUID, morador_unidade_id: uuid.UUID
    ) -> tuple[MoradorUnidade, str]:
        """O morador ATIVO desta unidade, ou 404. Morador de outra unidade também é 404."""
        consulta = (
            self._ativos_da_unidade(unidade_id)
            .where(MoradorUnidade.id == morador_unidade_id)
            .add_columns(Usuario.nome)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
        )
        linha = self.session.execute(consulta).tuples().first()
        if linha is None:
            raise RecursoNaoEncontrado
        return linha


class RepositorioPermissoes(RepositorioDoCondominio[PermissaoAba]):
    modelo = PermissaoAba

    # `PermissaoAba` tem chave composta (morador + aba) e não tem `id`: os métodos genéricos da
    # base não servem. Em vez de falharem com um erro obscuro, avisam qual método usar.
    def obter(self, item_id: uuid.UUID) -> PermissaoAba:
        raise NotImplementedError("Use `do_morador`: PermissaoAba tem chave composta.")

    def atualizar(self, item_id: uuid.UUID, dados: Mapping[str, Any]) -> PermissaoAba:
        raise NotImplementedError("Use `definir`: PermissaoAba tem chave composta.")

    def remover(self, item_id: uuid.UUID) -> None:
        raise NotImplementedError("Permissão por aba não se apaga: troque para Sem Acesso.")

    def dos_moradores(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, bool]]:
        """{morador_unidade_id: {aba: com_acesso}} de vários moradores numa só consulta."""
        consulta = self.consulta().where(PermissaoAba.morador_unidade_id.in_(ids))
        resultado: dict[uuid.UUID, dict[str, bool]] = {id_: {} for id_ in ids}
        for permissao in self.session.scalars(consulta):
            resultado[permissao.morador_unidade_id][permissao.aba] = permissao.com_acesso
        return resultado

    def do_morador(self, morador_unidade_id: uuid.UUID) -> dict[str, bool]:
        return self.dos_moradores([morador_unidade_id])[morador_unidade_id]

    def contar_com_usuarios(self, unidade_id: uuid.UUID, *, excluindo: uuid.UUID) -> int:
        """Quantos OUTROS moradores ativos da unidade estão Com Acesso à aba Usuários."""
        consulta = (
            select(func.count())
            .select_from(PermissaoAba)
            .join(
                MoradorUnidade,
                (MoradorUnidade.id == PermissaoAba.morador_unidade_id)
                & (MoradorUnidade.condominio_id == PermissaoAba.condominio_id),
            )
            .where(
                self._do_condominio(),
                MoradorUnidade.unidade_id == unidade_id,
                MoradorUnidade.status == "ativo",
                MoradorUnidade.id != excluindo,
                PermissaoAba.aba == "usuarios",
                PermissaoAba.com_acesso.is_(True),
            )
        )
        return self.session.scalar(consulta) or 0

    def definir(
        self, morador_unidade_id: uuid.UUID, abas: Mapping[str, bool], *, alterado_por: uuid.UUID
    ) -> None:
        """Grava Com Acesso/Sem Acesso das abas informadas (cria a linha se ainda não existir).

        O `condominio_id` vem do contexto, nunca de fora; e a chave estrangeira composta do banco
        garante que o morador pertence a este condomínio.
        """
        inserir = pg_insert(PermissaoAba).values(
            [
                {
                    "morador_unidade_id": morador_unidade_id,
                    "aba": aba,
                    "condominio_id": self.contexto.condominio_id,
                    "com_acesso": com_acesso,
                    "alterado_por_usuario_id": alterado_por,
                }
                for aba, com_acesso in abas.items()
            ]
        )
        self.session.execute(
            inserir.on_conflict_do_update(
                index_elements=[PermissaoAba.morador_unidade_id, PermissaoAba.aba],
                set_={
                    "com_acesso": inserir.excluded.com_acesso,
                    "alterado_por_usuario_id": inserir.excluded.alterado_por_usuario_id,
                    "alterado_em": func.now(),
                },
            )
        )


class RepositorioAuditoria(RepositorioDoCondominio[RegistroAuditoria]):
    """Grava eventos na trilha. PROVISÓRIO: quando a TASK-24 (US-1004) criar o serviço de
    auditoria, troque `registrar` por ele. A tabela só aceita INSERT (trigger do banco)."""

    modelo = RegistroAuditoria

    def registrar(
        self,
        *,
        acao: str,
        recurso_tipo: str,
        recurso_id: uuid.UUID,
        antes: dict[str, Any],
        depois: dict[str, Any],
        ip: str | None,
    ) -> None:
        self.criar(
            {
                "usuario_id": self.contexto.usuario_id,
                "perfil": self.contexto.perfil,
                "acao": acao,
                "recurso_tipo": recurso_tipo,
                "recurso_id": recurso_id,
                "antes": antes,
                "depois": depois,
                "ip": ip,
            }
        )
