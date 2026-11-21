import uuid
from datetime import datetime

from sqlalchemy import Select, func, select

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import Condominio
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.storage.models import Arquivo
from app.modules.usuarios.models import Usuario


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

    def historico(
        self, id_: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[tuple[str, datetime, str | None, uuid.UUID | None, str | None]], int]:
        # Exceção restrita da US-209: não carrega antes/depois, IP ou outros metadados.
        consulta = (
            select(
                RegistroAuditoria.acao,
                RegistroAuditoria.criado_em,
                RegistroAuditoria.responsavel_nome,
                Usuario.id,
                Usuario.nome,
            )
            .outerjoin(Usuario, Usuario.id == RegistroAuditoria.usuario_id)
            .where(
                RegistroAuditoria.condominio_id == self.contexto.condominio_id,
                RegistroAuditoria.recurso_tipo == "funcionario",
                RegistroAuditoria.recurso_id == id_,
                RegistroAuditoria.acao.in_(
                    ["funcionario.cadastrar", "funcionario.editar", "funcionario.desativar"]
                ),
            )
        )
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            consulta.order_by(RegistroAuditoria.criado_em.desc(), RegistroAuditoria.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return [
            (acao, criado_em, responsavel_nome, usuario_id, usuario_nome)
            for acao, criado_em, responsavel_nome, usuario_id, usuario_nome in linhas
        ], total


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
