import uuid
from typing import Any

from sqlalchemy import Select, func, select

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import Condominio
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.storage.models import Arquivo


class RepositorioFuncionarios(RepositorioDoCondominio[Funcionario]):
    modelo = Funcionario

    def filtrada(self, *, ativo: bool, busca: str | None) -> Select[tuple[Funcionario]]:
        consulta = self.consulta().where(Funcionario.ativo == ativo)
        if busca:
            consulta = consulta.where(Funcionario.nome.icontains(busca, autoescape=True))
        return consulta

    def pagina(
        self, *, ativo: bool, busca: str | None, page: int, page_size: int
    ) -> tuple[list[Funcionario], int]:
        consulta = self.filtrada(ativo=ativo, busca=busca)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        items = list(
            self.session.scalars(
                consulta.order_by(Funcionario.nome, Funcionario.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        return items, total

    def bloquear(self, id_: uuid.UUID) -> Funcionario:
        item = self.session.scalar(self.consulta().where(Funcionario.id == id_).with_for_update())
        if item is None:
            raise RecursoNaoEncontrado
        return item


class RepositorioResponsaveis(RepositorioDoCondominio[ResponsavelAdministracao]):
    modelo = ResponsavelAdministracao

    def ativos(self, *, ativo: bool) -> list[ResponsavelAdministracao]:
        return list(
            self.session.scalars(
                self.consulta()
                .where(ResponsavelAdministracao.ativo == ativo)
                .order_by(ResponsavelAdministracao.nome, ResponsavelAdministracao.id)
            )
        )

    def obter_ativo(self, id_: uuid.UUID) -> ResponsavelAdministracao:
        item = self.session.scalar(
            self.consulta()
            .where(ResponsavelAdministracao.id == id_, ResponsavelAdministracao.ativo.is_(True))
            .with_for_update(read=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def bloquear_cadastro(self) -> None:
        # Serializa o teste de unicidade por nome entre cadastros concorrentes do prédio.
        if (
            self.session.scalar(
                select(Condominio.id)
                .where(Condominio.id == self.contexto.condominio_id)
                .with_for_update()
            )
            is None
        ):
            raise RecursoNaoEncontrado

    def nome_em_uso(self, nome: str) -> bool:
        return (
            self.session.scalar(
                self.consulta()
                .where(
                    ResponsavelAdministracao.ativo.is_(True),
                    func.lower(ResponsavelAdministracao.nome) == nome.lower(),
                )
                .limit(1)
            )
            is not None
        )


class RepositorioFotos(RepositorioDoCondominio[Arquivo]):
    modelo = Arquivo

    def conferir(self, id_: uuid.UUID) -> None:
        arquivo = self.obter(id_)
        chave_esperada = f"condominio/{self.contexto.condominio_id}/fotos/{arquivo.id}"
        if (
            not arquivo.tipo_mime.startswith("image/")
            or arquivo.enviado_por_usuario_id != self.contexto.usuario_id
            or arquivo.chave_storage != chave_esperada
        ):
            raise RecursoNaoEncontrado


class RepositorioAuditoriaFuncionarios(RepositorioDoCondominio[RegistroAuditoria]):
    modelo = RegistroAuditoria

    def registrar(
        self,
        *,
        acao: str,
        recurso_tipo: str,
        recurso_id: uuid.UUID,
        responsavel_nome: str | None,
        antes: dict[str, Any],
        depois: dict[str, Any],
        ip: str | None,
    ) -> None:
        self.criar(
            {
                "usuario_id": self.contexto.usuario_id,
                "perfil": self.contexto.perfil,
                "responsavel_nome": responsavel_nome,
                "acao": acao,
                "recurso_tipo": recurso_tipo,
                "recurso_id": recurso_id,
                "antes": antes,
                "depois": depois,
                "ip": ip,
            }
        )
