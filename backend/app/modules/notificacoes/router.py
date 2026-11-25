"""Acompanhamento e reenvio da fila de e-mails, exclusivos do ADM da plataforma (US-803)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.autorizacao import require_platform_permission
from app.modules.notificacoes import service
from app.modules.notificacoes.schemas import ConsultaDeEnvios, EnvioSaida, PaginaDeEnvios

router = APIRouter(prefix="/plataforma/envios-email", tags=["envios-email"])

_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Autenticação necessária."},
    403: {"description": "Acesso exclusivo do ADM da plataforma."},
}


@router.get(
    "",
    response_model=PaginaDeEnvios,
    summary="Acompanhar a fila de e-mails",
    dependencies=[Depends(require_platform_permission("envios_email:ver"))],
    responses={**_ERROS, 422: {"description": "Filtros inválidos."}},
)
def listar(
    session: Annotated[Session, Depends(get_session)],
    consulta: Annotated[ConsultaDeEnvios, Query()],
) -> PaginaDeEnvios:
    return service.listar(session, consulta)


@router.post(
    "/{envio_id}/reenvio",
    response_model=EnvioSaida,
    status_code=202,
    summary="Recolocar na fila um e-mail que falhou",
    dependencies=[Depends(require_platform_permission("envios_email:editar"))],
    responses={
        **_ERROS,
        404: {"description": "Envio inexistente."},
        409: {
            "description": "Não falhou (`envio_nao_falhou`) ou é recuperação de senha "
            "(`reenvio_nao_permitido`)."
        },
    },
)
def reenviar(envio_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]) -> EnvioSaida:
    return service.reenviar(session, envio_id)
