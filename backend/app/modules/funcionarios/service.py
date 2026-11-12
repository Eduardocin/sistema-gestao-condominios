import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.funcionarios.repository import (
    RepositorioAuditoriaFuncionarios,
    RepositorioFotos,
    RepositorioFuncionarios,
    RepositorioResponsaveis,
)
from app.modules.funcionarios.schemas import FuncionarioEntrada


class FuncionariosService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.funcionarios = RepositorioFuncionarios(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)
        self.fotos = RepositorioFotos(session, contexto)
        self.auditoria = RepositorioAuditoriaFuncionarios(session, contexto)

    def listar(
        self, *, ativo: bool, busca: str | None, page: int, page_size: int
    ) -> tuple[list[Funcionario], int]:
        # A portaria só consulta os nomes ativos, mesmo enviando ativo=false.
        return self.funcionarios.pagina(
            ativo=True if self.contexto.perfil == "funcionario" else ativo,
            busca=busca,
            page=page,
            page_size=page_size,
        )

    def cadastrar(self, dados: FuncionarioEntrada, *, ip: str | None) -> Funcionario:
        try:
            responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)
            if dados.foto_arquivo_id is not None:
                self.fotos.conferir(dados.foto_arquivo_id)
            funcionario = self.funcionarios.criar(dados.model_dump(exclude={"responsavel_id"}))
            self.auditoria.registrar(
                acao="funcionario.cadastrar",
                recurso_tipo="funcionario",
                recurso_id=funcionario.id,
                responsavel_nome=responsavel.nome,
                antes={},
                depois={"nome": funcionario.nome, "funcao": funcionario.funcao, "ativo": True},
                ip=ip,
            )
            self.session.commit()
            return funcionario
        except Exception:
            self.session.rollback()
            raise

    def desligar(self, id_: uuid.UUID, responsavel_id: uuid.UUID, *, ip: str | None) -> Funcionario:
        try:
            responsavel = self.responsaveis.obter_ativo(responsavel_id)
            funcionario = self.funcionarios.bloquear(id_)
            if not funcionario.ativo:
                raise ApiError(409, "conflict", "Funcionário já desligado.", reason="ja_desligado")
            funcionario.ativo = False
            funcionario.desligado_em = datetime.now(UTC)
            self.auditoria.registrar(
                acao="funcionario.desativar",
                recurso_tipo="funcionario",
                recurso_id=funcionario.id,
                responsavel_nome=responsavel.nome,
                antes={"ativo": True},
                depois={"ativo": False, "desligado_em": funcionario.desligado_em.isoformat()},
                ip=ip,
            )
            self.session.commit()
            return funcionario
        except Exception:
            self.session.rollback()
            raise

    def listar_responsaveis(self, *, ativo: bool) -> list[ResponsavelAdministracao]:
        return self.responsaveis.ativos(ativo=ativo)

    def cadastrar_responsavel(self, nome: str, *, ip: str | None) -> ResponsavelAdministracao:
        try:
            self.responsaveis.bloquear_cadastro()
            if self.responsaveis.nome_em_uso(nome):
                raise ApiError(
                    409,
                    "conflict",
                    "Já existe um responsável ativo com este nome.",
                    reason="nome_duplicado",
                )
            responsavel = self.responsaveis.criar({"nome": nome})
            self.auditoria.registrar(
                acao="responsaveis.alterar",
                recurso_tipo="responsavel_administracao",
                recurso_id=responsavel.id,
                responsavel_nome=None,
                antes={},
                depois={"nome": responsavel.nome, "ativo": True},
                ip=ip,
            )
            self.session.commit()
            return responsavel
        except Exception:
            self.session.rollback()
            raise
