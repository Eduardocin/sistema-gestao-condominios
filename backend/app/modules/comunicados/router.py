"""Rotas de comunicados: `/plataforma/comunicados` (ADM) e `/comunicados` (Administração)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission, require_platform_permission
from app.modules.comunicados.schemas import (
    ComunicadoComDestinatarios,
    ComunicadoEntrada,
    ComunicadoSaida,
    ConsultaDeComunicados,
    PaginaDeComunicados,
    PaginaDeComunicadosDaAdministracao,
)
from app.modules.comunicados.service import ComunicadosDaAdministracao, ComunicadosDaPlataforma

router = APIRouter(prefix="/comunicados", tags=["comunicados"])
plataforma_router = APIRouter(prefix="/plataforma/comunicados", tags=["comunicados"])

SessionDep = Annotated[Session, Depends(get_session)]
VerComoPlataforma = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("comunicados:ver"))
]
EnviarComoPlataforma = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("comunicados:criar"))
]
VerComoAdministracao = Annotated[ContextoCondominio, Depends(require_permission("comunicados:ver"))]

_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Autenticação necessária."},
    403: {"description": "Perfil sem permissão (`forbidden`)."},
}


@plataforma_router.post(
    "",
    response_model=ComunicadoSaida,
    status_code=201,
    summary="Enviar um comunicado a todas as Administrações (ADM)",
    responses={**_ERROS, 422: {"description": "Entrada inválida."}},
)
def enviar(
    dados: ComunicadoEntrada,
    contexto: EnviarComoPlataforma,
    session: SessionDep,
    request: Request,
) -> ComunicadoSaida:
    return ComunicadosDaPlataforma(session, contexto, ip=ip_do_cliente(request)).enviar(dados)


@plataforma_router.get(
    "",
    response_model=PaginaDeComunicados,
    summary="Listar os comunicados enviados (ADM)",
    responses=_ERROS,
)
def listar(
    contexto: VerComoPlataforma,
    session: SessionDep,
    consulta: Annotated[ConsultaDeComunicados, Query()],
) -> PaginaDeComunicados:
    return ComunicadosDaPlataforma(session, contexto).listar(consulta)


@plataforma_router.get(
    "/{comunicado_id}",
    response_model=ComunicadoComDestinatarios,
    summary="Consultar um comunicado com os condomínios destinatários (ADM)",
    responses={**_ERROS, 404: {"description": "Comunicado inexistente."}},
)
def obter(
    comunicado_id: uuid.UUID, contexto: VerComoPlataforma, session: SessionDep
) -> ComunicadoComDestinatarios:
    return ComunicadosDaPlataforma(session, contexto).obter(comunicado_id)


@router.get(
    "",
    response_model=PaginaDeComunicadosDaAdministracao,
    summary="Comunicados enviados ao seu condomínio (Administração)",
    responses=_ERROS,
)
def listar_da_administracao(
    contexto: VerComoAdministracao,
    session: SessionDep,
    consulta: Annotated[ConsultaDeComunicados, Query()],
) -> PaginaDeComunicadosDaAdministracao:
    return ComunicadosDaAdministracao(session, contexto).listar(consulta)
