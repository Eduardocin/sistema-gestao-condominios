import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.funcionarios.dependencies import contexto_responsaveis
from app.modules.funcionarios.schemas import (
    ContaFuncionariosEntrada,
    ContaFuncionariosSaida,
    DesligamentoEntrada,
    EntradaVazia,
    FuncionarioEntrada,
    FuncionarioNome,
    FuncionarioSaida,
    PaginaFuncionarios,
    PaginaHistoricoFuncionario,
    ResponsavelEntrada,
    ResponsavelSaida,
)
from app.modules.funcionarios.service import ContaFuncionariosService, FuncionariosService

router = APIRouter(prefix="/funcionarios", tags=["funcionarios"])
responsaveis_router = APIRouter(prefix="/responsaveis-administracao", tags=["responsaveis"])
conta_router = APIRouter(prefix="/conta-funcionarios", tags=["conta-funcionarios"])
SessionDep = Annotated[Session, Depends(get_session)]
ResponsaveisContextoDep = Annotated[ContextoCondominio, Depends(contexto_responsaveis)]


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
    # Funcionário vê só os nomes; a Administração vê o resumo, com telefone mascarado.
    resumir = (
        FuncionarioNome.model_validate
        if service.contexto.perfil == "funcionario"
        else FuncionarioSaida.para_listagem
    )
    return PaginaFuncionarios(
        items=[resumir(item) for item in items],
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


@router.get(
    "/{funcionario_id}",
    response_model=FuncionarioSaida,
    dependencies=[Depends(require_permission("funcionarios:ver"))],
)
def detalhe(funcionario_id: uuid.UUID, service: ServiceDep) -> FuncionarioSaida:
    return FuncionarioSaida.model_validate(service.obter(funcionario_id))


@router.put(
    "/{funcionario_id}",
    response_model=FuncionarioSaida,
    dependencies=[Depends(require_permission("funcionarios:editar"))],
)
def editar(
    funcionario_id: uuid.UUID,
    dados: FuncionarioEntrada,
    service: ServiceDep,
    request: Request,
) -> FuncionarioSaida:
    return FuncionarioSaida.model_validate(
        service.editar(funcionario_id, dados, ip=ip_do_cliente(request))
    )


@router.get(
    "/{funcionario_id}/historico",
    response_model=PaginaHistoricoFuncionario,
    dependencies=[Depends(require_permission("funcionarios:ver"))],
)
def historico(
    funcionario_id: uuid.UUID,
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaHistoricoFuncionario:
    items, total = service.historico(funcionario_id, page=page, page_size=page_size)
    return PaginaHistoricoFuncionario(items=items, page=page, page_size=page_size, total=total)


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


@responsaveis_router.put("/{responsavel_id}", response_model=ResponsavelSaida)
def editar_responsavel(
    responsavel_id: uuid.UUID,
    dados: ResponsavelEntrada,
    session: SessionDep,
    contexto: ResponsaveisContextoDep,
    request: Request,
) -> ResponsavelSaida:
    service = FuncionariosService(session, contexto)
    return ResponsavelSaida.model_validate(
        service.editar_responsavel(responsavel_id, dados.nome, ip=ip_do_cliente(request))
    )


@responsaveis_router.post("/{responsavel_id}/desativacao", response_model=ResponsavelSaida)
def desativar_responsavel(
    responsavel_id: uuid.UUID,
    dados: EntradaVazia,
    session: SessionDep,
    contexto: ResponsaveisContextoDep,
    request: Request,
) -> ResponsavelSaida:
    service = FuncionariosService(session, contexto)
    return ResponsavelSaida.model_validate(
        service.desativar_responsavel(responsavel_id, ip=ip_do_cliente(request))
    )


@conta_router.get("", response_model=ContaFuncionariosSaida)
def consultar_conta_funcionarios(
    session: SessionDep,
    contexto: Annotated[
        ContextoCondominio, Depends(require_permission("contas_compartilhadas:ver"))
    ],
) -> ContaFuncionariosSaida:
    return ContaFuncionariosService(session, contexto).obter()


@conta_router.put("", response_model=ContaFuncionariosSaida)
def definir_conta_funcionarios(
    dados: ContaFuncionariosEntrada,
    session: SessionDep,
    contexto: Annotated[
        ContextoCondominio, Depends(require_permission("contas_compartilhadas:editar"))
    ],
    relogio: Annotated[Relogio, Depends(get_relogio)],
    request: Request,
) -> ContaFuncionariosSaida:
    return ContaFuncionariosService(session, contexto, relogio).definir(
        dados, ip=ip_do_cliente(request)
    )
