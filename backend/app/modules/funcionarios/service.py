import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ReferenciaAuditoria, ResponsavelRef
from app.modules.auth.security import hash_senha, verificar_senha
from app.modules.condominios.models import VinculoCondominio
from app.modules.contas import repository as contas_repository
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.funcionarios.repository import (
    RepositorioContaFuncionarios,
    RepositorioFotos,
    RepositorioFuncionarios,
    RepositorioResponsaveis,
)
from app.modules.funcionarios.schemas import (
    ContaFuncionariosEntrada,
    ContaFuncionariosSaida,
    EventoHistoricoFuncionario,
    FuncionarioEntrada,
)
from app.modules.usuarios.models import Usuario


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
            self._bloquear_responsaveis()
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

    def _bloquear_responsaveis(self) -> None:
        self._exigir_administracao()
        condominio = self.responsaveis.bloquear_cadastro()
        if condominio.status not in {"pendente", "rejeitado", "ativo"}:
            raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")

    def editar_responsavel(
        self, id_: uuid.UUID, nome: str, *, ip: str | None
    ) -> ResponsavelAdministracao:
        try:
            self._bloquear_responsaveis()
            item = self.responsaveis.bloquear(id_)
            if item.ativo and self.responsaveis.nome_em_uso(nome, exceto=id_):
                raise ApiError(409, "conflict", "Nome indisponível.", reason="nome_duplicado")
            if item.nome != nome:
                antes = {"nome": item.nome}
                item.nome = nome
                self._auditar_responsavel(item, antes=antes, depois={"nome": nome}, ip=ip)
            self.session.commit()
            return item
        except Exception:
            self.session.rollback()
            raise

    def desativar_responsavel(self, id_: uuid.UUID, *, ip: str | None) -> ResponsavelAdministracao:
        try:
            self._bloquear_responsaveis()
            item = self.responsaveis.bloquear(id_)
            if not item.ativo:
                raise ApiError(
                    409, "conflict", "Responsável já desativado.", reason="ja_desativado"
                )
            if self.responsaveis.contar_ativos() <= 1:
                raise ApiError(
                    409,
                    "conflict",
                    "Cadastre outro responsável ativo antes de desativar este.",
                    reason="ultimo_responsavel",
                )
            item.ativo = False
            self._auditar_responsavel(item, antes={"ativo": True}, depois={"ativo": False}, ip=ip)
            self.session.commit()
            return item
        except Exception:
            self.session.rollback()
            raise

    def _auditar_responsavel(
        self,
        item: ResponsavelAdministracao,
        *,
        antes: Mapping[str, str | bool],
        depois: Mapping[str, str | bool],
        ip: str | None,
    ) -> None:
        auditoria.registrar_acao(
            self.session,
            ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
            acao="responsaveis.alterar",
            recurso_tipo="responsavel_administracao",
            recurso_id=item.id,
            antes=antes,
            depois=depois,
        )


class ContaFuncionariosService:
    def __init__(
        self, session: Session, contexto: ContextoCondominio, relogio: Relogio = agora
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.relogio = relogio
        self.contas = RepositorioContaFuncionarios(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)

    def _conferir(self, vinculo: VinculoCondominio, usuario: Usuario) -> None:
        if (
            not vinculo.ativo
            or not usuario.ativo
            or usuario.tipo_cadastro is not None
            or usuario.administrador_plataforma
            or usuario.telefone is not None
            or usuario.documento is not None
            or usuario.senha_hash is None
            or vinculo.unidade_id is not None
            or self.contas.quantidade_vinculos(usuario.id) != 1
        ):
            raise ApiError(
                409,
                "conflict",
                "Conta de Funcionários indisponível; regularização explícita necessária.",
                reason="conta_compartilhada_incompativel",
            )

    @staticmethod
    def _saida(vinculo: VinculoCondominio, usuario: Usuario) -> ContaFuncionariosSaida:
        return ContaFuncionariosSaida(
            login=usuario.email,
            atualizada_em=vinculo.credenciais_atualizadas_em.astimezone(UTC)
            if vinculo.credenciais_atualizadas_em is not None
            else None,
        )

    def obter(self) -> ContaFuncionariosSaida:
        vinculo = self.contas.vinculo()
        if vinculo is None:
            raise RecursoNaoEncontrado
        usuario = self.contas.usuario(vinculo)
        self._conferir(vinculo, usuario)
        return self._saida(vinculo, usuario)

    def definir(self, dados: ContaFuncionariosEntrada, *, ip: str | None) -> ContaFuncionariosSaida:
        try:
            condominio = self.responsaveis.bloquear_cadastro()
            if condominio.status != "ativo":
                raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")
            responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)
            vinculo = self.contas.vinculo()
            usuario = self.contas.usuario(vinculo, bloquear=True) if vinculo else None
            if vinculo is not None and usuario is not None:
                self._conferir(vinculo, usuario)
            if contas_repository.campo_em_uso(
                self.session,
                "email",
                dados.login,
                exceto_usuario_id=usuario.id if usuario else None,
            ):
                raise self._login_indisponivel()
            antes: dict[str, str | int] = {}
            if usuario is None:
                usuario = self.contas.criar_usuario(
                    login=dados.login, senha_hash=hash_senha(dados.senha)
                )
                vinculo = self.contas.criar(
                    {
                        "usuario_id": usuario.id,
                        "perfil": "funcionario",
                        "credenciais_atualizadas_em": self.relogio(),
                    }
                )
            else:
                assert vinculo is not None
                if usuario.email == dados.login and verificar_senha(
                    dados.senha, usuario.senha_hash or ""
                ):
                    saida = self._saida(vinculo, usuario)
                    self.session.commit()
                    return saida
                antes = {"login": usuario.email, "sessao_versao": usuario.sessao_versao}
                usuario.email = dados.login
                usuario.senha_hash = hash_senha(dados.senha)
                usuario.sessao_versao += 1
                vinculo.credenciais_atualizadas_em = self.relogio()
            self.session.flush()
            auditoria.registrar_acao(
                self.session,
                ctx=ContextoAuditoria.do_condominio(self.contexto, ip=ip),
                acao="conta_compartilhada.trocar_acesso",
                recurso_tipo="usuario",
                recurso_id=usuario.id,
                responsavel=ResponsavelRef("administracao", responsavel.id),
                antes=antes,
                depois={"login": usuario.email, "sessao_versao": usuario.sessao_versao},
            )
            assert vinculo is not None
            saida = self._saida(vinculo, usuario)
            self.session.commit()
            return saida
        except IntegrityError as erro:
            self.session.rollback()
            if (
                getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
                == "uq_usuarios_email"
            ):
                raise self._login_indisponivel() from None
            raise ApiError(500, "internal_error", "Não foi possível alterar o acesso.") from None
        except SQLAlchemyError:
            self.session.rollback()
            raise ApiError(500, "internal_error", "Não foi possível alterar o acesso.") from None
        except Exception:
            self.session.rollback()
            raise

    @staticmethod
    def _login_indisponivel() -> ApiError:
        return ApiError(
            409, "conflict", "O login informado não está disponível.", reason="login_indisponivel"
        )
