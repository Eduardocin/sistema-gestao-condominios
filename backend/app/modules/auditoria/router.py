"""Consulta somente de leitura da US-903, exclusiva do ADM da plataforma."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auditoria import service
from app.modules.auditoria.schemas import ConsultaAuditoria, PaginaAuditoria
from app.modules.auth.autorizacao import require_platform_permission

router = APIRouter(
    prefix="/plataforma/auditoria",
    tags=["auditoria"],
    dependencies=[Depends(require_platform_permission("auditoria:ver"))],
)


@router.get(
    "",
    response_model=PaginaAuditoria,
    summary="Consultar a trilha de auditoria",
    responses={
        401: {"description": "Autenticação necessária."},
        403: {"description": "Acesso exclusivo do ADM da plataforma."},
        422: {"description": "Filtros ou cursor inválidos."},
    },
)
def consultar(
    session: Annotated[Session, Depends(get_session)],
    filtros: Annotated[ConsultaAuditoria, Query()],
) -> PaginaAuditoria:
    return service.consultar(session, filtros)
