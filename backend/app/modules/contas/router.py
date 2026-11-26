from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.auth.presentation import resposta_de_sessao
from app.modules.auth.rate_limit import LoginRateLimiter, get_login_rate_limiter
from app.modules.auth.schemas import LoginResponse
from app.modules.contas.schemas import (
    CadastroAdministracao,
    CadastroMorador,
    ContaSaida,
    EdicaoConta,
    RedefinicaoSenha,
    SolicitacaoRecuperacaoSenha,
    TrocaSenha,
)
from app.modules.contas.service import (
    cadastrar,
    editar_propria_conta,
    enviar_email_recuperacao,
    redefinir_senha,
    solicitar_recuperacao_senha,
    trocar_propria_senha,
)

router = APIRouter(prefix="/contas", tags=["contas"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]
LimiterDep = Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)]


@router.post("/morador", response_model=LoginResponse, status_code=201)
def cadastrar_morador(
    dados: CadastroMorador, session: SessionDep, settings: SettingsDep, request: Request
) -> LoginResponse:
    return resposta_de_sessao(
        cadastrar(session, dados, "morador", settings, ip=ip_do_cliente(request))
    )


@router.post("/administracao", response_model=LoginResponse, status_code=201)
def cadastrar_administracao(
    dados: CadastroAdministracao, session: SessionDep, settings: SettingsDep, request: Request
) -> LoginResponse:
    return resposta_de_sessao(
        cadastrar(session, dados, "administracao", settings, ip=ip_do_cliente(request))
    )


@router.get("/me", response_model=ContaSaida)
def consultar_propria_conta(autenticado: UsuarioDep) -> ContaSaida:
    return ContaSaida.model_validate(autenticado.usuario)


@router.put("/me", response_model=ContaSaida)
def editar_conta(
    dados: EdicaoConta, autenticado: UsuarioDep, session: SessionDep, request: Request
) -> ContaSaida:
    return editar_propria_conta(session, autenticado.usuario, dados, ip=ip_do_cliente(request))


_ERROS_SENHA: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Conta sem cadastro próprio: compartilhada ou ADM (`forbidden`)."},
    422: {
        "description": "Senha nova fora da regra, `senha_atual_incorreta` ou "
        "`senha_nova_igual_atual`."
    },
    429: {"description": "Muitas tentativas com a senha atual errada (`too_many_attempts`)."},
}


@router.put(
    "/me/senha",
    response_model=LoginResponse,
    summary="Trocar a própria senha (derruba as outras sessões e devolve tokens novos)",
    responses=_ERROS_SENHA,
)
def trocar_senha(
    dados: TrocaSenha,
    autenticado: UsuarioDep,
    session: SessionDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    request: Request,
) -> LoginResponse:
    sessao = trocar_propria_senha(
        session,
        autenticado.usuario,
        dados,
        limiter=limiter,
        settings=settings,
        ip=ip_do_cliente(request),
        condominio_id_atual=autenticado.condominio_id,
    )
    return resposta_de_sessao(sessao)


@router.post(
    "/recuperacao-senha",
    status_code=202,
    summary="Solicitar link de redefinição de senha",
    responses={
        202: {"description": "Solicitação aceita, exista ou não uma conta elegível."},
        422: {"description": "E-mail inválido."},
        429: {"description": "Limite de solicitações por endereço IP excedido."},
    },
)
def solicitar_recuperacao(
    dados: SolicitacaoRecuperacaoSenha,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    request: Request,
) -> None:
    mensagem = solicitar_recuperacao_senha(
        session,
        dados,
        limiter=limiter,
        settings=settings,
        ip=ip_do_cliente(request),
    )
    if mensagem is not None:
        background_tasks.add_task(enviar_email_recuperacao, mensagem, settings)


@router.post(
    "/redefinicao-senha",
    status_code=204,
    summary="Redefinir a senha com o token de uso único do e-mail",
    responses={
        422: {"description": "Senha nova fora da regra ou `token_invalido` (sempre igual)."}
    },
)
def redefinir(
    dados: RedefinicaoSenha, session: SessionDep, limiter: LimiterDep, request: Request
) -> None:
    # Sem sessão na resposta: a pessoa entra pelo login com a senha nova.
    redefinir_senha(session, dados, limiter=limiter, ip=ip_do_cliente(request))
