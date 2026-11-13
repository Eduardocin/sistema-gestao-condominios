import ipaddress
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.session import get_session
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.encomendas.schemas import (
    ConfirmacaoEntrada,
    EncomendaEntrada,
    EncomendaSaida,
    EntregaEntrada,
    PaginaEncomendas,
    PaginaMoradores,
    PaginaUnidades,
    StatusEncomenda,
)
from app.modules.encomendas.service import EncomendasService
from app.modules.storage.router import get_storage_adapter
from app.modules.storage.types import StorageAdapter, StorageError, StorageValidationError

router = APIRouter(prefix="/encomendas", tags=["encomendas"])
portaria_router = APIRouter(prefix="/portaria", tags=["portaria"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_service(session: SessionDep, contexto: ContextoDep) -> EncomendasService:
    return EncomendasService(session, contexto)


ServiceDep = Annotated[EncomendasService, Depends(get_service)]


def get_recebimento_service(
    session: SessionDep,
    contexto: ContextoDep,
    adapter: Annotated[StorageAdapter, Depends(get_storage_adapter)],
) -> EncomendasService:
    return EncomendasService(session, contexto, adapter)


RecebimentoServiceDep = Annotated[EncomendasService, Depends(get_recebimento_service)]


def ip_do_cliente(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


async def dados_recebimento(
    unidade_id: Annotated[uuid.UUID, Form()],
    destinatario_morador_unidade_id: Annotated[uuid.UUID, Form()],
    descricao: Annotated[str, Form(min_length=1, max_length=200)],
    recebido_por_funcionario_id: Annotated[uuid.UUID, Form()],
    request: Request,
) -> EncomendaEntrada:
    campos_esperados = {
        "unidade_id",
        "destinatario_morador_unidade_id",
        "descricao",
        "recebido_por_funcionario_id",
        "foto",
    }
    form = await request.form()
    if set(form.keys()) - campos_esperados:
        raise ApiError(422, "validation_error", "Dados inválidos.")
    descricao_normalizada = descricao.strip()
    if not descricao_normalizada:
        raise ApiError(422, "validation_error", "Dados inválidos.")
    return EncomendaEntrada(
        unidade_id=unidade_id,
        destinatario_morador_unidade_id=destinatario_morador_unidade_id,
        descricao=descricao_normalizada,
        recebido_por_funcionario_id=recebido_por_funcionario_id,
    )


@router.post(
    "",
    response_model=EncomendaSaida,
    status_code=201,
    dependencies=[Depends(require_permission("encomendas:criar"))],
)
def registrar(
    dados: Annotated[EncomendaEntrada, Depends(dados_recebimento)],
    foto: Annotated[UploadFile, File()],
    service: RecebimentoServiceDep,
    request: Request,
    response: Response,
) -> EncomendaSaida:
    try:
        encomenda = service.registrar(
            dados,
            foto.file,
            foto.filename or "",
            foto.content_type or "application/octet-stream",
            ip=ip_do_cliente(request),
        )
    except StorageValidationError as error:
        raise ApiError(422, "validation_error", str(error)) from None
    except StorageError:
        raise ApiError(
            503, "storage_unavailable", "Armazenamento temporariamente indisponível."
        ) from None

    response.headers["Location"] = f"/api/v1/encomendas/{encomenda.id}"
    return service.obter(encomenda.id)


@router.post(
    "/{encomenda_id}/entrega",
    response_model=EncomendaSaida,
    dependencies=[Depends(require_permission("encomendas:editar"))],
)
def entregar(
    encomenda_id: uuid.UUID,
    dados: EntregaEntrada,
    service: ServiceDep,
    request: Request,
) -> EncomendaSaida:
    encomenda = service.entregar(
        encomenda_id,
        recebedor_morador_unidade_id=dados.recebedor_morador_unidade_id,
        entregue_por_funcionario_id=dados.entregue_por_funcionario_id,
        ip=ip_do_cliente(request),
    )
    return service.obter(encomenda.id)


@router.post(
    "/{encomenda_id}/confirmacao",
    response_model=EncomendaSaida,
    dependencies=[Depends(require_permission("encomendas:editar"))],
)
def confirmar(
    encomenda_id: uuid.UUID,
    _dados: ConfirmacaoEntrada,
    service: ServiceDep,
    request: Request,
) -> EncomendaSaida:
    encomenda = service.confirmar(encomenda_id, ip=ip_do_cliente(request))
    return service.obter(encomenda.id)


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
    somente_confirmaveis: bool = False,
) -> PaginaMoradores:
    return service.listar_moradores(
        unidade_id,
        page=page,
        page_size=page_size,
        somente_confirmaveis=somente_confirmaveis,
    )
