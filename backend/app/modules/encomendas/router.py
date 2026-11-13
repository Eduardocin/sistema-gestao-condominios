import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.encomendas.schemas import (
    EncomendaSaida,
    PaginaEncomendas,
    PaginaMoradores,
    PaginaUnidades,
    StatusEncomenda,
)
from app.modules.encomendas.service import EncomendasService

router = APIRouter(prefix="/encomendas", tags=["encomendas"])
portaria_router = APIRouter(prefix="/portaria", tags=["portaria"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_service(session: SessionDep, contexto: ContextoDep) -> EncomendasService:
    return EncomendasService(session, contexto)


ServiceDep = Annotated[EncomendasService, Depends(get_service)]


@router.get(
    "",
    response_model=PaginaEncomendas,
    dependencies=[Depends(require_permission("encomendas:ver"))],
)
def listar(
    service: ServiceDep,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    status: StatusEncomenda | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaEncomendas:
    return service.listar(busca=busca, status=status, page=page, page_size=page_size)


@router.get(
    "/{encomenda_id}",
    response_model=EncomendaSaida,
    dependencies=[Depends(require_permission("encomendas:ver"))],
)
def obter(encomenda_id: uuid.UUID, service: ServiceDep) -> EncomendaSaida:
    return service.obter(encomenda_id)


@portaria_router.get(
    "/unidades",
    response_model=PaginaUnidades,
    dependencies=[Depends(require_permission("encomendas:ver"))],
)
def listar_unidades(
    service: ServiceDep,
    busca: Annotated[str | None, Query(max_length=80)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaUnidades:
    return service.listar_unidades(busca=busca, page=page, page_size=page_size)


@portaria_router.get(
    "/unidades/{unidade_id}/moradores",
    response_model=PaginaMoradores,
    dependencies=[Depends(require_permission("encomendas:ver"))],
)
def listar_moradores(
    unidade_id: uuid.UUID,
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaMoradores:
    return service.listar_moradores(unidade_id, page=page, page_size=page_size)
