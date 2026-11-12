"""Resposta de sessão compartilhada pelo login e pelos cadastros de conta."""

from app.modules.auth.schemas import CondominioAcessoOut, LoginResponse, UsuarioOut
from app.modules.auth.service import SessaoEmitida


def resposta_de_sessao(sessao: SessaoEmitida) -> LoginResponse:
    return LoginResponse(
        access_token=sessao.access_token,
        refresh_token=sessao.refresh_token,
        expires_in=sessao.expires_in,
        usuario=UsuarioOut.model_validate(sessao.usuario),
        condominio=(
            CondominioAcessoOut.model_validate(sessao.selecionado) if sessao.selecionado else None
        ),
        condominios=[CondominioAcessoOut.model_validate(a) for a in sessao.acessos],
        requer_selecao=sessao.requer_selecao,
        administrador_plataforma=sessao.usuario.administrador_plataforma,
    )
