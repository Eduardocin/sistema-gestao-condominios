"""Rotas de autenticação: `/api/v1/auth/*`. Aqui só traduzimos HTTP ↔ service."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.auth.presentation import resposta_de_sessao
from app.modules.auth.rate_limit import LoginRateLimiter, get_login_rate_limiter
from app.modules.auth.schemas import (
    CondominioAcessoOut,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    SelecionarCondominioRequest,
    UnidadeOut,
    UsuarioOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]

_RESPOSTAS_401: dict[int | str, dict[str, Any]] = {
    401: {"description": "Credenciais ou token inválidos (`not_authenticated`)."}
}


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Entrar com e-mail e senha",
    responses={**_RESPOSTAS_401, 429: {"description": "Muitas tentativas (`too_many_attempts`)."}},
)
def login(
    dados: LoginRequest,
    session: SessionDep,
    settings: SettingsDep,
    limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
) -> LoginResponse:
    sessao = service.login(
        session, email=dados.identificador, senha=dados.senha, limiter=limiter, settings=settings
    )
    return resposta_de_sessao(sessao)


@router.post(
    "/selecionar-condominio",
    response_model=LoginResponse,
    summary="Escolher o condomínio de trabalho",
    responses={
        **_RESPOSTAS_401,
        403: {"description": "Condomínio indisponível para este perfil (`forbidden`)."},
        404: {"description": "Sem vínculo ativo com o condomínio (`not_found`)."},
    },
)
def selecionar_condominio(
    dados: SelecionarCondominioRequest,
    autenticado: UsuarioDep,
    session: SessionDep,
    settings: SettingsDep,
) -> LoginResponse:
    sessao = service.selecionar_condominio(
        session,
        usuario=autenticado.usuario,
        condominio_id=dados.condominio_id,
        settings=settings,
    )
    return resposta_de_sessao(sessao)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Renovar o access token",
    responses=_RESPOSTAS_401,
)
def refresh(dados: RefreshRequest, session: SessionDep, settings: SettingsDep) -> RefreshResponse:
    access_token, expires_in = service.renovar_access_token(
        session, refresh_token=dados.refresh_token, settings=settings
    )
    return RefreshResponse(access_token=access_token, expires_in=expires_in)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Dados de quem está logado",
    responses={**_RESPOSTAS_401, 403: {"description": "Acesso ao condomínio retirado."}},
)
def me(autenticado: UsuarioDep, session: SessionDep) -> MeResponse:
    dados = service.montar_me(
        session, usuario=autenticado.usuario, condominio_id=autenticado.condominio_id
    )
    return MeResponse(
        usuario=UsuarioOut.model_validate(dados.usuario),
        condominio=CondominioAcessoOut.model_validate(dados.acesso) if dados.acesso else None,
        unidades=[UnidadeOut.model_validate(u) for u in dados.unidades],
        administrador_plataforma=dados.usuario.administrador_plataforma,
    )
