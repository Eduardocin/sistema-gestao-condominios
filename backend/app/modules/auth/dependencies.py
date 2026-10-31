"""Dependências do FastAPI para identificar quem está chamando a API.

`get_usuario_autenticado` é a base da autorização: outras rotas (e a autorização central da
TASK-19) devem depender dela em vez de ler o token por conta própria. Rotas de condomínio usam
`get_current_context` (alias `ContextoDep`), que soma a ela o vínculo e o condomínio (TASK-18).
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.db.session import get_session
from app.modules.auth import service
from app.modules.usuarios.models import Usuario

# `auto_error=False` porque o erro padrão do FastAPI não segue o nosso envelope.
_esquema_bearer = HTTPBearer(auto_error=False, description="Access token JWT do /auth/login")


@dataclass(frozen=True)
class UsuarioAutenticado:
    usuario: Usuario
    # Condomínio escolhido no token; None em tokens "pré-seleção" e no ADM da plataforma.
    condominio_id: uuid.UUID | None


def get_usuario_autenticado(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UsuarioAutenticado:
    if credenciais is None:
        raise ApiError(
            401,
            "not_authenticated",
            "Autenticação necessária.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    usuario, condominio_id = service.autenticar_access_token(
        session, token=credenciais.credentials, settings=settings
    )
    return UsuarioAutenticado(usuario=usuario, condominio_id=condominio_id)


def get_current_context(
    autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextoCondominio:
    """Porta de entrada de toda rota "do dia a dia" de um condomínio (TASK-18, US-1001).

    Ordem da matriz (seção 5), a primeira falha encerra:
    1. identidade: sem token, token ruim, `sv` velho ou usuário inativo -> 401 (dependência acima);
    2. condomínio: sem `cid`, sem vínculo ativo, ADM da plataforma ou condomínio não ativo -> 403.

    O `condominio_id` do contexto sai do token JÁ validado, e o perfil sai do vínculo no banco
    (R6): o claim `perfil` do token nunca é lido aqui. O contexto é o que os repositories
    recebem para filtrar por condomínio (app/db/repositorio.py).

    Pontos de extensão (fora do escopo da TASK-18, ver convenções da API, seção 2): rotas sem
    `cid` (login, escolha de condomínio, `/auth/me`), rotas `/plataforma/...` e o fluxo de
    cadastro do condomínio não ativo (R7) serão dependências irmãs desta, reaproveitando
    `get_usuario_autenticado`. Não relaxe esta aqui para atender esses casos.
    """
    if autenticado.condominio_id is None:
        raise ApiError(403, "forbidden", "Selecione um condomínio para continuar.")

    vinculo, _ = service.verificar_acesso_ao_condominio(
        session, usuario=autenticado.usuario, condominio_id=autenticado.condominio_id
    )
    return ContextoCondominio(
        usuario_id=autenticado.usuario.id,
        condominio_id=vinculo.condominio_id,
        perfil=vinculo.perfil,
        vinculo_id=vinculo.id,
    )


ContextoDep = Annotated[ContextoCondominio, Depends(get_current_context)]
