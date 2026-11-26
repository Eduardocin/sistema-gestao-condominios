import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.auth.rate_limit import LoginRateLimiter
from app.modules.auth.security import (
    gastar_tempo_de_verificacao,
    hash_do_token,
    hash_senha,
    verificar_senha,
)
from app.modules.auth.service import SessaoEmitida, emitir_sessao_do_usuario
from app.modules.contas import repository
from app.modules.contas.schemas import (
    MENSAGEM_SENHA,
    CadastroAdministracao,
    CadastroConta,
    ContaSaida,
    EdicaoConta,
    RedefinicaoSenha,
    SolicitacaoRecuperacaoSenha,
    TrocaSenha,
    conferir_senha,
)
from app.modules.notificacoes.smtp import Mensagem, obter_backend
from app.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

TIPOS_DE_CADASTRO = {"morador", "administracao"}
MENSAGEM_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."
MENSAGEM_SENHA_ATUAL = "A senha atual está incorreta."
MENSAGEM_SENHA_IGUAL = "A nova senha precisa ser diferente da atual."
# Um só erro para token inexistente, expirado, já usado ou de conta que não pode redefinir:
# a resposta não diz qual foi o caso.
MENSAGEM_TOKEN_INVALIDO = "Link de redefinição inválido ou expirado. Peça um novo."


def _cadastro_global(usuario: Usuario) -> bool:
    """Morador ou Administração com cadastro próprio. Conta compartilhada e ADM ficam de fora."""
    return usuario.tipo_cadastro in TIPOS_DE_CADASTRO and not usuario.administrador_plataforma


def _senha_invalida() -> ApiError:
    return ApiError(422, "validation_error", MENSAGEM_SENHA)


def _token_invalido() -> ApiError:
    return ApiError(422, "validation_error", MENSAGEM_TOKEN_INVALIDO, reason="token_invalido")


def solicitar_recuperacao_senha(
    session: Session,
    dados: SolicitacaoRecuperacaoSenha,
    *,
    limiter: LoginRateLimiter,
    settings: Settings,
    ip: str | None,
) -> Mensagem | None:
    """Cria um token de uso único, sem revelar se a conta existe, e confirma a transação."""
    chave = f"recuperacao:{ip or 'desconhecido'}"
    segundos = limiter.bloqueio_restante(chave)
    if segundos > 0:
        raise ApiError(
            429,
            "too_many_attempts",
            "Muitas solicitações. Tente novamente mais tarde.",
            headers={"Retry-After": str(segundos)},
        )
    limiter.registrar_falha(chave)

    mensagem: Mensagem | None = None
    try:
        # Custo fixo reduz a diferença de tempo entre contas elegíveis e e-mails sem conta.
        gastar_tempo_de_verificacao(dados.email)
        usuario = repository.obter_conta_para_recuperacao(session, dados.email)
        if usuario is not None:
            token = secrets.token_urlsafe(32)
            repository.inutilizar_tokens_pendentes(session, usuario.id)
            repository.criar_token_recuperacao(
                session,
                usuario.id,
                hash_do_token(token),
                datetime.now(UTC) + timedelta(minutes=settings.password_reset_token_expire_minutes),
            )
            auditoria.registrar_acao(
                session,
                ctx=ContextoAuditoria(usuario_id=usuario.id, ip=ip),
                acao="conta.senha_recuperacao_solicitar",
                recurso_tipo="usuario",
                recurso_id=usuario.id,
                antes={},
                depois={},
            )
            link = f"{settings.frontend_base_url.rstrip('/')}/redefinir-senha?token={token}"
            mensagem = Mensagem(
                destinatario=usuario.email,
                assunto="Redefinição de senha — Gestão de Condomínios",
                corpo=(
                    "Recebemos uma solicitação para redefinir sua senha.\n\n"
                    "Acesse este link em até "
                    f"{settings.password_reset_token_expire_minutes} minutos:\n"
                    f"{link}\n\n"
                    "Se você não solicitou a redefinição, ignore este e-mail."
                ),
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return mensagem


def enviar_email_recuperacao(mensagem: Mensagem, settings: Settings) -> None:
    """Entrega fora da transação HTTP; falha no provedor não invalida a solicitação."""
    if settings.email_backend == "console":
        logger.info(
            "Envio de recuperação ignorado com EMAIL_BACKEND=console; configure SMTP/Mailpit."
        )
        return
    try:
        obter_backend(settings).enviar(mensagem)
    except Exception as erro:
        # Não registrar mensagem, destinatário, URL ou texto da exceção: podem conter o token.
        logger.warning("Falha no envio do e-mail de recuperação (%s).", type(erro).__name__)


def _conflito(campo: str) -> ApiError:
    return ApiError(
        409, "conflict", "Já existe uma conta com este dado.", reason=f"{campo}_ja_cadastrado"
    )


def cadastrar(
    session: Session,
    dados: CadastroConta,
    tipo: Literal["morador", "administracao"],
    settings: Settings,
    *,
    ip: str | None = None,
) -> SessaoEmitida:
    documento = dados.documento if isinstance(dados, CadastroAdministracao) else None
    valores = {"email": dados.email, "telefone": dados.telefone, "documento": documento}
    for campo, valor in valores.items():
        if valor is not None and repository.campo_em_uso(session, campo, valor):
            raise _conflito(campo)
    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        telefone=dados.telefone,
        documento=documento,
        tipo_cadastro=tipo,
        senha_hash=hash_senha(dados.senha),
    )
    try:
        session.add(usuario)
        session.flush()
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria(usuario_id=usuario.id, ip=ip),
            acao="conta.criar",
            recurso_tipo="usuario",
            recurso_id=usuario.id,
            antes={},
            # Whitelist de saída: nunca inclui senha, hash ou a sessão emitida abaixo.
            depois=ContaSaida.model_validate(usuario).model_dump(exclude={"id"}),
        )
        sessao = emitir_sessao_do_usuario(session, usuario=usuario, settings=settings)
        session.commit()
    except IntegrityError as erro:
        # As constraints também protegem dois cadastros concorrentes do mesmo dado.
        session.rollback()
        for campo, valor in valores.items():
            if valor is not None and repository.campo_em_uso(session, campo, valor):
                raise _conflito(campo) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return sessao


def editar_propria_conta(
    session: Session, usuario: Usuario, dados: EdicaoConta, *, ip: str | None
) -> ContaSaida:
    usuario = repository.bloquear_conta(session, usuario.id)
    # Este recorte trata cadastros globais. Contas compartilhadas não podem trocar seu
    # acesso por esta rota e contornar o responsável e a revogação de sessões da US-210.
    if not _cadastro_global(usuario):
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    if usuario.tipo_cadastro == "morador" and len(dados.nome.split()) < 2:
        raise ApiError(422, "validation_error", "Informe o nome completo.")
    usuario_id = usuario.id
    valores = dados.model_dump()
    for campo in ("email", "telefone"):
        if repository.campo_em_uso(session, campo, valores[campo], exceto_usuario_id=usuario_id):
            raise _conflito(campo)
    antes = {
        campo: getattr(usuario, campo)
        for campo in valores
        if getattr(usuario, campo) != valores[campo]
    }
    depois = {campo: valores[campo] for campo in antes}
    try:
        repository.atualizar_conta(session, usuario, **valores)
        auditoria.registrar_acao(
            session,
            # Operação global de conta própria, mesmo quando o JWT contém um cid.
            # Tipo de cadastro não é perfil de condomínio; não inventamos vínculo/responsável.
            ctx=ContextoAuditoria(usuario_id=usuario_id, ip=ip),
            acao="conta.editar",
            recurso_tipo="usuario",
            recurso_id=usuario_id,
            antes=antes,
            depois=depois,
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        for campo in ("email", "telefone"):
            if repository.campo_em_uso(
                session, campo, valores[campo], exceto_usuario_id=usuario_id
            ):
                raise _conflito(campo) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return ContaSaida.model_validate(usuario)


def trocar_propria_senha(
    session: Session,
    usuario: Usuario,
    dados: TrocaSenha,
    *,
    limiter: LoginRateLimiter,
    settings: Settings,
    ip: str | None,
    condominio_id_atual: uuid.UUID | None = None,
) -> SessaoEmitida:
    """Troca a senha de quem está logado e devolve uma sessão nova (as antigas caem pelo `sv`)."""
    if not _cadastro_global(usuario):
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)

    chave = f"senha:{usuario.id}"
    segundos = limiter.bloqueio_restante(chave)
    if segundos > 0:
        raise ApiError(
            429,
            "too_many_attempts",
            "Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(segundos)},
        )

    versao_token = usuario.sessao_versao
    try:
        # Trava a conta: duas trocas simultâneas não usam a mesma senha atual nem a mesma versão.
        usuario = repository.bloquear_conta(session, usuario.id)
        if usuario.sessao_versao != versao_token:
            raise ApiError(
                401,
                "not_authenticated",
                "Sessão inválida ou expirada. Entre novamente.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Mesmo recorte do PUT /contas/me: conta compartilhada troca acesso pela US-210, com
        # responsável; o ADM da plataforma não tem cadastro global.
        if not _cadastro_global(usuario):
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)

        if usuario.senha_hash is None or not verificar_senha(dados.senha_atual, usuario.senha_hash):
            limiter.registrar_falha(chave)
            raise ApiError(
                422, "validation_error", MENSAGEM_SENHA_ATUAL, reason="senha_atual_incorreta"
            )
        limiter.limpar(chave)

        if dados.senha_nova == dados.senha_atual:
            raise ApiError(
                422, "validation_error", MENSAGEM_SENHA_IGUAL, reason="senha_nova_igual_atual"
            )
        try:
            conferir_senha(
                dados.senha_nova, usuario.email
            )  # a parte da regra que depende do e-mail
        except ValueError as erro:
            raise _senha_invalida() from erro

        versao_antiga = usuario.sessao_versao
        repository.gravar_senha(session, usuario, hash_senha(dados.senha_nova))
        repository.inutilizar_tokens_pendentes(session, usuario.id)
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria(usuario_id=usuario.id, ip=ip),
            acao="conta.senha_alterar",
            recurso_tipo="usuario",
            recurso_id=usuario.id,
            # Só a versão da sessão: senha, hash e tokens nunca entram na trilha (RN-84).
            antes={"sessao_versao": versao_antiga},
            depois={"sessao_versao": usuario.sessao_versao},
        )
        sessao = emitir_sessao_do_usuario(
            session,
            usuario=usuario,
            settings=settings,
            condominio_id_atual=condominio_id_atual,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return sessao


def redefinir_senha(
    session: Session,
    dados: RedefinicaoSenha,
    *,
    limiter: LoginRateLimiter | None = None,
    ip: str | None,
) -> None:
    """Consome o token e grava a senha nova, tudo ou nada.

    Qualquer falha (token inválido, conta que não pode redefinir, senha igual ao e-mail,
    auditoria) desfaz a transação inteira: o UPDATE que consumiu o token também volta, e um
    token válido continua válido.
    """
    # argon2 antes de tocar no banco, para não segurar as travas durante o cálculo.
    novo_hash = hash_senha(dados.senha_nova)
    try:
        token_hash = hash_do_token(dados.token)
        usuario_id = repository.obter_usuario_id_token_recuperacao(session, token_hash)
        if usuario_id is None:
            raise _token_invalido()
        usuario = repository.obter_conta_travada(session, usuario_id)
        if usuario is None or not usuario.ativo or not _cadastro_global(usuario):
            raise _token_invalido()  # o mesmo erro: não revelamos o estado da conta
        # Serializa todos os tokens da mesma conta pelo lock do usuário. A requisição seguinte
        # só chega aqui depois do commit e verá seu token invalidado pela primeira redefinição.
        if repository.consumir_token_recuperacao(session, token_hash) != usuario.id:
            raise _token_invalido()
        try:
            conferir_senha(dados.senha_nova, usuario.email)
        except ValueError as erro:
            raise _senha_invalida() from erro

        versao_antiga = usuario.sessao_versao
        email_conta = usuario.email
        repository.gravar_senha(session, usuario, novo_hash)
        repository.inutilizar_tokens_pendentes(session, usuario.id)
        auditoria.registrar_acao(
            session,
            # Rota pública: como em conta.criar, a identidade auditada é a dona do token.
            ctx=ContextoAuditoria(usuario_id=usuario.id, ip=ip),
            acao="conta.senha_redefinir",
            recurso_tipo="usuario",
            recurso_id=usuario.id,
            antes={"sessao_versao": versao_antiga},
            depois={"sessao_versao": usuario.sessao_versao},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    if limiter is not None:
        limiter.limpar(email_conta)
        limiter.limpar(f"senha:{usuario_id}")
