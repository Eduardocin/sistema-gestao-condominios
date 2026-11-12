import ipaddress
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.db.session import get_session
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.funcionarios.dependencies import contexto_responsaveis
from app.modules.funcionarios.schemas import (
    DesligamentoEntrada,
    FuncionarioEntrada,
    FuncionarioNome,
    FuncionarioSaida,
    PaginaFuncionarios,
    ResponsavelEntrada,
    ResponsavelSaida,
)
from app.modules.funcionarios.service import FuncionariosService

router = APIRouter(prefix="/funcionarios", tags=["funcionarios"])
responsaveis_router = APIRouter(prefix="/responsaveis-administracao", tags=["responsaveis"])
SessionDep = Annotated[Session, Depends(get_session)]
ResponsaveisContextoDep = Annotated[ContextoCondominio, Depends(contexto_responsaveis)]


def ip_do_cliente(request: Request) -> str | None:
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def get_service(session: SessionDep, contexto: ContextoDep) -> FuncionariosService:
    return FuncionariosService(session, contexto)


ServiceDep = Annotated[FuncionariosService, Depends(get_service)]


@router.get(
    "",
    response_model=PaginaFuncionarios,
    dependencies=[Depends(require_permission("funcionarios:ver"))],
)
def listar(
    service: ServiceDep,
    ativo: bool = True,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaFuncionarios:
    items, total = service.listar(ativo=ativo, busca=busca, page=page, page_size=page_size)
    saida = FuncionarioNome if service.contexto.perfil == "funcionario" else FuncionarioSaida
    return PaginaFuncionarios(
        items=[saida.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "",
    response_model=FuncionarioSaida,
    status_code=201,
    dependencies=[Depends(require_permission("funcionarios:criar"))],
)
def cadastrar(dados: FuncionarioEntrada, service: ServiceDep, request: Request) -> FuncionarioSaida:
    return FuncionarioSaida.model_validate(service.cadastrar(dados, ip=ip_do_cliente(request)))


@router.post(
    "/{funcionario_id}/desligamento",
    response_model=FuncionarioSaida,
    dependencies=[Depends(require_permission("funcionarios:desativar"))],
)
def desligar(
    funcionario_id: uuid.UUID, dados: DesligamentoEntrada, service: ServiceDep, request: Request
) -> FuncionarioSaida:
    return FuncionarioSaida.model_validate(
        service.desligar(funcionario_id, dados.responsavel_id, ip=ip_do_cliente(request))
    )


@responsaveis_router.get("", response_model=list[ResponsavelSaida])
def listar_responsaveis(
    session: SessionDep, contexto: ResponsaveisContextoDep, ativo: bool = True
) -> list[ResponsavelSaida]:
    service = FuncionariosService(session, contexto)
    return [
        ResponsavelSaida.model_validate(item) for item in service.listar_responsaveis(ativo=ativo)
    ]


@responsaveis_router.post("", response_model=ResponsavelSaida, status_code=201)
def cadastrar_responsavel(
    dados: ResponsavelEntrada,
    session: SessionDep,
    contexto: ResponsaveisContextoDep,
    request: Request,
) -> ResponsavelSaida:
    service = FuncionariosService(session, contexto)
    return ResponsavelSaida.model_validate(
        service.cadastrar_responsavel(dados.nome, ip=ip_do_cliente(request))
    )
