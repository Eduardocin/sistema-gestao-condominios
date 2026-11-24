import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.visitantes.router import Page, RelogioDep, SessionDep, Size
from app.modules.visitantes.schemas import Entrada, Pagina
from app.modules.visitantes.veiculos_schemas import CadastroVeiculo, EdicaoVeiculo, VeiculoSaida
from app.modules.visitantes.veiculos_service import VeiculosService

router = APIRouter(prefix="/veiculos", tags=["veículos"])


def get_service(session: SessionDep, contexto: ContextoDep, relogio: RelogioDep) -> VeiculosService:
    return VeiculosService(session, contexto, relogio)


Service = Annotated[VeiculosService, Depends(get_service)]


@router.get(
    "", dependencies=[Depends(require_permission("veiculos:ver"))], response_model_exclude_none=True
)
def listar(
    service: Service,
    unidade_id: uuid.UUID | None = None,
    busca: Annotated[str | None, Query(max_length=80)] = None,
    page: Page = 1,
    page_size: Size = 20,
) -> Pagina[VeiculoSaida]:
    return service.pagina(unidade_id, busca, page, page_size)


@router.get(
    "/{veiculo_id}",
    dependencies=[Depends(require_permission("veiculos:ver"))],
    response_model_exclude_none=True,
)
def detalhe(veiculo_id: uuid.UUID, service: Service) -> VeiculoSaida:
    return service.detalhe(veiculo_id)


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_permission("veiculos:criar"))],
    response_model_exclude_none=True,
)
def cadastrar(
    dados: CadastroVeiculo, service: Service, request: Request, response: Response
) -> VeiculoSaida:
    item = service.cadastrar(dados, ip_do_cliente(request))
    response.headers["Location"] = f"/api/v1/veiculos/{item.id}"
    return item


@router.put(
    "/{veiculo_id}",
    dependencies=[Depends(require_permission("veiculos:editar"))],
    response_model_exclude_none=True,
)
def editar(
    veiculo_id: uuid.UUID, dados: EdicaoVeiculo, service: Service, request: Request
) -> VeiculoSaida:
    return service.editar(veiculo_id, dados, ip_do_cliente(request))


@router.post(
    "/{veiculo_id}/remocao",
    dependencies=[Depends(require_permission("veiculos:desativar"))],
    response_model_exclude_none=True,
)
def remover(
    veiculo_id: uuid.UUID, service: Service, request: Request, dados: Entrada | None = None
) -> VeiculoSaida:
    return service.remover(veiculo_id, ip_do_cliente(request))
