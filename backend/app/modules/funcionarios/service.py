import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ReferenciaAuditoria, ResponsavelRef
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.funcionarios.repository import (
    RepositorioFotos,
    RepositorioFuncionarios,
    RepositorioResponsaveis,
)
from app.modules.funcionarios.schemas import EventoHistoricoFuncionario, FuncionarioEntrada


class FuncionariosService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto
        self.funcionarios = RepositorioFuncionarios(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)
        self.fotos = RepositorioFotos(session, contexto)

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
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="funcionario.cadastrar",
                recurso_tipo="funcionario",
                recurso_id=funcionario.id,
                responsavel=ResponsavelRef("administracao", responsavel.id),
                antes={},
                depois={"nome": funcionario.nome, "funcao": funcionario.funcao, "ativo": True},
            )
            self.session.commit()
            return funcionario
        except Exception:
            self.session.rollback()
            raise

    def _exigir_administracao(self) -> None:
        # A Portaria pode listar nomes, mas não ler dados completos nem o histórico.
        if self.contexto.perfil != "administracao":
            raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")

    def obter(self, id_: uuid.UUID) -> Funcionario:
        self._exigir_administracao()
        return self.funcionarios.obter(id_)

    def editar(self, id_: uuid.UUID, dados: FuncionarioEntrada, *, ip: str | None) -> Funcionario:
        try:
            self._exigir_administracao()
            responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)
            funcionario = self.funcionarios.bloquear(id_)
            if dados.foto_arquivo_id is not None:
                self.fotos.conferir(dados.foto_arquivo_id)
            campos = dados.model_dump(exclude={"responsavel_id"})
            antes = {
                campo: getattr(funcionario, campo)
                for campo, valor in campos.items()
                if getattr(funcionario, campo) != valor
            }
            if antes:
                for campo, valor in campos.items():
                    setattr(funcionario, campo, valor)
                self.session.flush()
                auditoria.registrar_acao(
                    self.session,
                    ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                    acao="funcionario.editar",
                    recurso_tipo="funcionario",
                    recurso_id=funcionario.id,
                    responsavel=ResponsavelRef("administracao", responsavel.id),
                    antes=antes,
                    depois={campo: campos[campo] for campo in antes},
                )
            self.session.commit()
            return funcionario
        except Exception:
            self.session.rollback()
            raise

    def historico(
        self, id_: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[list[EventoHistoricoFuncionario], int]:
        self.obter(id_)  # Confere perfil e recurso, incluindo desligados; não existe -> 404.
        linhas, total = self.funcionarios.historico(id_, page=page, page_size=page_size)
        return [
            EventoHistoricoFuncionario(
                acao=acao,
                criado_em=criado_em,
                responsavel_nome=responsavel_nome,
                usuario=ReferenciaAuditoria(id=usuario_id, nome=usuario_nome)
                if usuario_id is not None and usuario_nome is not None
                else None,
            )
            for acao, criado_em, responsavel_nome, usuario_id, usuario_nome in linhas
        ], total

    def desligar(self, id_: uuid.UUID, responsavel_id: uuid.UUID, *, ip: str | None) -> Funcionario:
        try:
            responsavel = self.responsaveis.obter_ativo(responsavel_id)
            funcionario = self.funcionarios.bloquear(id_)
            if not funcionario.ativo:
                raise ApiError(409, "conflict", "Funcionário já desligado.", reason="ja_desligado")
            funcionario.ativo = False
            funcionario.desligado_em = datetime.now(UTC)
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="funcionario.desativar",
                recurso_tipo="funcionario",
                recurso_id=funcionario.id,
                responsavel=ResponsavelRef("administracao", responsavel.id),
                antes={"ativo": True},
                depois={"ativo": False, "desligado_em": funcionario.desligado_em.isoformat()},
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
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="responsaveis.alterar",
                recurso_tipo="responsavel_administracao",
                recurso_id=responsavel.id,
                antes={},
                depois={"nome": responsavel.nome, "ativo": True},
            )
            self.session.commit()
            return responsavel
        except Exception:
            self.session.rollback()
            raise
