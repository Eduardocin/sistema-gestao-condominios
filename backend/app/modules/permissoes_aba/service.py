"""Regras das permissões por aba: listar os moradores da unidade e mudar o acesso de cada um.

Quem chama já passou por `require_permission` (perfil) e `require_aba("usuarios")` (unidade e
aba): ver o router. Aqui ficam o passo 6 da matriz, a regra de negócio: a trava do último
morador com a aba Usuários, a auditoria e o commit.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.modules.permissoes_aba.repository import (
    RepositorioAuditoria,
    RepositorioMoradores,
    RepositorioPermissoes,
    RepositorioUnidades,
)
from app.modules.unidades.models import ABAS_MORADOR, MoradorUnidade

ACAO_AUDITORIA = "permissao_aba.alterar"
MENSAGEM_ULTIMO_USUARIOS = "A unidade precisa ter ao menos um morador com acesso à aba Usuários."


@dataclass(frozen=True)
class MoradorDaUnidade:
    id: uuid.UUID
    nome: str
    parentesco: str | None
    vinculado_em: datetime
    eu: bool
    permissoes: dict[str, bool]


@dataclass(frozen=True)
class MoradoresPaginados:
    items: list[MoradorDaUnidade]
    page: int
    page_size: int
    total: int


class PermissoesAbaService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.unidades = RepositorioUnidades(session, contexto)
        self.moradores = RepositorioMoradores(session, contexto)
        self.permissoes = RepositorioPermissoes(session, contexto)
        self.auditoria = RepositorioAuditoria(session, contexto)

    def _montar(
        self, morador: MoradorUnidade, nome: str, abas: Mapping[str, bool]
    ) -> MoradorDaUnidade:
        return MoradorDaUnidade(
            id=morador.id,
            nome=nome,
            parentesco=morador.parentesco,
            vinculado_em=morador.vinculado_em,
            eu=morador.usuario_id == self.contexto.usuario_id,
            # Sempre as sete, na ordem do DER. Aba sem linha no banco conta como Sem Acesso.
            permissoes={aba: abas.get(aba, False) for aba in ABAS_MORADOR},
        )

    def listar_moradores(
        self, unidade_id: uuid.UUID, *, page: int, page_size: int
    ) -> MoradoresPaginados:
        linhas = self.moradores.listar_da_unidade(
            unidade_id, limite=page_size, deslocamento=(page - 1) * page_size
        )
        abas = self.permissoes.dos_moradores([morador.id for morador, _ in linhas])
        return MoradoresPaginados(
            items=[self._montar(morador, nome, abas[morador.id]) for morador, nome in linhas],
            page=page,
            page_size=page_size,
            total=self.moradores.contar_da_unidade(unidade_id),
        )

    def alterar_permissoes(
        self,
        unidade_id: uuid.UUID,
        morador_unidade_id: uuid.UUID,
        abas: Mapping[str, bool],
        *,
        ip: str | None,
    ) -> MoradorDaUnidade:
        """Muda Com Acesso/Sem Acesso das abas informadas e registra na auditoria.

        Tudo-ou-nada: a trava, a gravação e o evento de auditoria acontecem na mesma transação,
        com um único commit no fim. Se qualquer passo falhar, nada fica gravado.
        """
        # 1) Uma alteração por vez em cada unidade: a trava do último usuário depende de
        # contar quem tem a aba, e essa conta não pode mudar no meio do caminho.
        self.unidades.bloquear(unidade_id)

        # 2) O morador precisa ser ativo NESTA unidade; outra unidade ou outro condomínio é 404.
        morador, nome = self.moradores.obter_da_unidade(unidade_id, morador_unidade_id)
        atuais = self.permissoes.do_morador(morador.id)

        # 3) Só o que de fato muda: repetir o mesmo valor não gera gravação nem auditoria.
        mudancas = {aba: novo for aba, novo in abas.items() if atuais.get(aba, False) != novo}
        if mudancas:
            self._conferir_trava_do_ultimo(unidade_id, morador.id, atuais, mudancas)
            self.permissoes.definir(morador.id, mudancas, alterado_por=self.contexto.usuario_id)
            self.auditoria.registrar(
                acao=ACAO_AUDITORIA,
                recurso_tipo="morador_unidade",
                recurso_id=morador.id,
                antes={aba: atuais.get(aba, False) for aba in mudancas},
                depois=dict(mudancas),
                ip=ip,
            )
        self.session.commit()  # também solta a tranca da unidade

        return self._montar(morador, nome, self.permissoes.do_morador(morador.id))

    def _conferir_trava_do_ultimo(
        self,
        unidade_id: uuid.UUID,
        morador_id: uuid.UUID,
        atuais: Mapping[str, bool],
        mudancas: Mapping[str, bool],
    ) -> None:
        """Ninguém tira a aba Usuários do último que a tem: senão a unidade fica sem ninguém
        para mudar permissões (matriz, seção 8)."""
        perde_usuarios = "usuarios" in mudancas and atuais.get("usuarios", False)
        if (
            perde_usuarios
            and self.permissoes.contar_com_usuarios(unidade_id, excluindo=morador_id) == 0
        ):
            raise ApiError(409, "conflict", MENSAGEM_ULTIMO_USUARIOS, reason="ultimo_usuarios")
