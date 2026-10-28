"""Dependências do FastAPI para identificar quem está chamando a API.

`get_usuario_autenticado` é a base da autorização: outras rotas (e a autorização central da
TASK-19) devem depender dela em vez de ler o token por conta própria.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
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
