import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.avisos.schemas import (
    AvisoEntrada,
    AvisoSaida,
    EncerramentoEntrada,
    PaginaDeAvisos,
    SituacaoFiltro,
)
from app.modules.avisos.service import AvisosService

router = APIRouter(prefix="/avisos", tags=["avisos"])


def get_service(
    session: Annotated[Session, Depends(get_session)],
    contexto: ContextoDep,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> AvisosService:
    return AvisosService(session, contexto, relogio)


ServiceDep = Annotated[AvisosService, Depends(get_service)]


@router.get(
    "",
    response_model=PaginaDeAvisos,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_permission("avisos:ver"))],
)
def listar(
    service: ServiceDep,
    situacao: SituacaoFiltro = "vigentes",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeAvisos:
    return service.listar(situacao=situacao, page=page, page_size=page_size)


@router.get(
    "/vigentes",
    response_model=PaginaDeAvisos,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_permission("avisos:ver"))],
)
def listar_vigentes(
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeAvisos:
    return service.listar(situacao="vigentes", page=page, page_size=page_size)


@router.get(
    "/{aviso_id}",
    response_model=AvisoSaida,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_permission("avisos:ver"))],
)
def obter(aviso_id: uuid.UUID, service: ServiceDep) -> AvisoSaida:
    return service.obter(aviso_id)


@router.post(
    "",
    response_model=AvisoSaida,
    response_model_exclude_unset=True,
    status_code=201,
    dependencies=[Depends(require_permission("avisos:criar"))],
)
def publicar(
    dados: AvisoEntrada, service: ServiceDep, request: Request, response: Response
) -> AvisoSaida:
    aviso = service.publicar(dados, ip=ip_do_cliente(request))
    response.headers["Location"] = f"/api/v1/avisos/{aviso.id}"
    return aviso


@router.put(
    "/{aviso_id}",
    response_model=AvisoSaida,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_permission("avisos:editar"))],
)
def editar(
    aviso_id: uuid.UUID, dados: AvisoEntrada, service: ServiceDep, request: Request
) -> AvisoSaida:
    return service.editar(aviso_id, dados, ip=ip_do_cliente(request))


@router.post(
    "/{aviso_id}/encerramento",
    response_model=AvisoSaida,
    response_model_exclude_unset=True,
    dependencies=[Depends(require_permission("avisos:desativar"))],
)
def encerrar(
    aviso_id: uuid.UUID, dados: EncerramentoEntrada, service: ServiceDep, request: Request
) -> AvisoSaida:
    return service.encerrar(aviso_id, dados.responsavel_id, ip=ip_do_cliente(request))
