import uuid
from datetime import datetime

from sqlalchemy import Select, func, select

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import Condominio, VinculoCondominio
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
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def bloquear_cadastro(self) -> Condominio:
        # Ordem da US-210: condomínio -> responsável -> conta. NO KEY UPDATE é compatível
        # com KEY SHARE das FKs de operações que já validaram um responsável (FOR SHARE).
        condominio = self.session.scalar(
            select(Condominio)
            .where(Condominio.id == self.contexto.condominio_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if condominio is None:
            raise RecursoNaoEncontrado
        return condominio

    def bloquear(self, id_: uuid.UUID) -> ResponsavelAdministracao:
        item = self.session.scalar(
            self.consulta()
            .where(ResponsavelAdministracao.id == id_)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def contar_ativos(self) -> int:
        consulta = self.consulta().where(ResponsavelAdministracao.ativo.is_(True))
        return self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0

    def nome_em_uso(self, nome: str, *, exceto: uuid.UUID | None = None) -> bool:
        consulta = self.consulta().where(
            ResponsavelAdministracao.ativo.is_(True),
            func.lower(ResponsavelAdministracao.nome) == nome.lower(),
        )
        if exceto is not None:
            consulta = consulta.where(ResponsavelAdministracao.id != exceto)
        return self.session.scalar(consulta.limit(1)) is not None


class RepositorioContaFuncionarios(RepositorioDoCondominio[VinculoCondominio]):
    modelo = VinculoCondominio

    def vinculo(self) -> VinculoCondominio | None:
        return self.session.scalar(
            self.consulta()
            .where(VinculoCondominio.perfil == "funcionario")
            .execution_options(populate_existing=True)
        )

    def usuario(self, vinculo: VinculoCondominio, *, bloquear: bool = False) -> Usuario:
        # ID obtido exclusivamente do vínculo do condomínio, nunca recebido do cliente.
        consulta = select(Usuario).where(Usuario.id == vinculo.usuario_id)
        if bloquear:
            consulta = consulta.with_for_update(key_share=True)
        usuario = self.session.scalar(consulta.execution_options(populate_existing=True))
        if usuario is None:
            raise RecursoNaoEncontrado
        return usuario

    def quantidade_vinculos(self, usuario_id: uuid.UUID) -> int:
        # Verificação global restrita à identidade já localizada neste condomínio.
        return (
            self.session.scalar(
                select(func.count())
                .select_from(VinculoCondominio)
                .where(VinculoCondominio.usuario_id == usuario_id)
            )
            or 0
        )

    def criar_usuario(self, *, login: str, senha_hash: str) -> Usuario:
        usuario = Usuario(nome="Conta de Funcionários", email=login, senha_hash=senha_hash)
        self.session.add(usuario)
        self.session.flush()
        return usuario


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
