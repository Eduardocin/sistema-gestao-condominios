"""Rotas de `/api/v1/visitantes` (convivencia.md, §6.2).

A ordem da matriz está nas dependências: `require_permission` (perfil, 403) roda antes de o corpo
ser validado (422) e do service. A unidade e a aba (passo 4) ficam no service, porque aqui o
`unidade_id` vem da query, do corpo ou do próprio cadastro. Só traduzimos HTTP.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.visitantes.schemas import (
    PaginaDeVeiculos,
    PaginaDeVisitantes,
    Situacao,
    VeiculoAtualizacao,
    VeiculoEntrada,
    VeiculoSaida,
    VisitanteAtualizacao,
    VisitanteEntrada,
    VisitanteSaida,
)
from app.modules.visitantes.service import VeiculosService, VisitantesService

router = APIRouter(prefix="/visitantes", tags=["visitantes"])


def so_morador(permissao: str) -> Callable[..., None]:
    """Perfil da matriz (403) e, além dele, só o Morador.

    A matriz também dá `visitantes` ao Funcionário (consulta, avulso, entrada e saída) e à
    Administração (ver), mas essas rotas são do Morador (US-501); a consulta da portaria é outro
    contrato (portaria.md). Roda antes da validação do corpo.
    """

    def verificar(
        contexto: Annotated[ContextoCondominio, Depends(require_permission(permissao))],
    ) -> None:
        if contexto.perfil != Perfil.MORADOR:
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)

    return verificar


def get_service(
    session: Annotated[Session, Depends(get_session)],
    contexto: ContextoDep,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> VisitantesService:
    # O contexto vem do token + banco, nunca do cliente.
    return VisitantesService(session, contexto, relogio)


ServiceDep = Annotated[VisitantesService, Depends(get_service)]

_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil sem permissão ou aba Visitantes Sem Acesso (`forbidden`)."},
    404: {
        "description": "Visitante ou unidade inexistente, de outra unidade ou de outro condomínio."
    },
}


@router.get(
    "",
    response_model=PaginaDeVisitantes,
    summary="Lista os visitantes de uma unidade (Morador)",
    dependencies=[Depends(so_morador("visitantes:ver"))],
    responses=_ERROS,
)
def listar_visitantes(
    service: ServiceDep,
    unidade_id: uuid.UUID,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    situacao: Situacao | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeVisitantes:
    return service.listar(
        unidade_id=unidade_id, busca=busca, situacao=situacao, page=page, page_size=page_size
    )


@router.get(
    "/{visitante_id}",
    response_model=VisitanteSaida,
    summary="Detalha um visitante (Morador)",
    dependencies=[Depends(so_morador("visitantes:ver"))],
    responses=_ERROS,
)
def obter_visitante(visitante_id: uuid.UUID, service: ServiceDep) -> VisitanteSaida:
    return service.obter(visitante_id)


@router.post(
    "",
    response_model=VisitanteSaida,
    status_code=201,
    summary="Cadastra um visitante (Morador)",
    dependencies=[Depends(so_morador("visitantes:criar"))],
    responses={**_ERROS, 422: {"description": "Entrada inválida (CPF, período, tamanhos)."}},
)
def criar_visitante(
    dados: VisitanteEntrada, service: ServiceDep, request: Request, response: Response
) -> VisitanteSaida:
    visitante = service.criar(dados)
    response.headers["Location"] = request.url_for(
        "obter_visitante", visitante_id=visitante.id
    ).path
    return visitante


@router.put(
    "/{visitante_id}",
    response_model=VisitanteSaida,
    summary="Edita um visitante ainda não utilizado (Morador)",
    dependencies=[Depends(so_morador("visitantes:editar"))],
    responses={
        **_ERROS,
        409: {
            "description": (
                "Visitante cancelado (`visitante_cancelado`) ou com visita registrada "
                "(`visitante_ja_utilizado`)."
            )
        },
        422: {"description": "Entrada inválida ou tentativa de trocar a unidade."},
    },
)
def atualizar_visitante(
    visitante_id: uuid.UUID, dados: VisitanteAtualizacao, service: ServiceDep
) -> VisitanteSaida:
    return service.atualizar(visitante_id, dados)


@router.post(
    "/{visitante_id}/cancelamento",
    response_model=VisitanteSaida,
    summary="Cancela o cadastro de um visitante (Morador)",
    dependencies=[Depends(so_morador("visitantes:desativar"))],
    responses={
        **_ERROS,
        409: {
            "description": (
                "Já cancelado (`visitante_ja_cancelado`) ou no condomínio (`visita_em_andamento`)."
            )
        },
    },
)
def cancelar_visitante(visitante_id: uuid.UUID, service: ServiceDep) -> VisitanteSaida:
    return service.cancelar(visitante_id)


# --- veículos (US-502, convivencia.md §6.3) ---------------------------------------------------
# A matriz já separa os perfis: Morador faz tudo na própria unidade (aba Veículos), Funcionário e
# Administração só consultam o condomínio.

veiculos_router = APIRouter(prefix="/veiculos", tags=["veiculos"])


def get_veiculos_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> VeiculosService:
    return VeiculosService(session, contexto)


VeiculosServiceDep = Annotated[VeiculosService, Depends(get_veiculos_service)]

_ERROS_VEICULOS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil sem permissão ou aba Veículos Sem Acesso (`forbidden`)."},
    404: {"description": "Veículo ou unidade inexistente, de outra unidade ou condomínio."},
}


@veiculos_router.get(
    "",
    response_model=PaginaDeVeiculos,
    summary="Lista veículos ativos da unidade (Morador) ou do condomínio (portaria, Administração)",
    dependencies=[Depends(require_permission("veiculos:ver"))],
    responses=_ERROS_VEICULOS,
)
def listar_veiculos(
    service: VeiculosServiceDep,
    # Morador: obrigatório. Funcionário e Administração: filtro opcional.
    unidade_id: uuid.UUID | None = None,
    busca: Annotated[str | None, Query(max_length=40)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeVeiculos:
    return service.listar(unidade_id=unidade_id, busca=busca, page=page, page_size=page_size)


@veiculos_router.get(
    "/{veiculo_id}",
    response_model=VeiculoSaida,
    summary="Detalha um veículo",
    dependencies=[Depends(require_permission("veiculos:ver"))],
    responses=_ERROS_VEICULOS,
)
def obter_veiculo(veiculo_id: uuid.UUID, service: VeiculosServiceDep) -> VeiculoSaida:
    return service.obter(veiculo_id)


@veiculos_router.post(
    "",
    response_model=VeiculoSaida,
    status_code=201,
    summary="Cadastra um veículo (Morador)",
    dependencies=[Depends(require_permission("veiculos:criar"))],
    responses={
        **_ERROS_VEICULOS,
        409: {"description": "Placa ativa repetida na unidade (`placa_ja_cadastrada_na_unidade`)."},
        422: {"description": "Entrada inválida (placa fora do formato, tamanhos)."},
    },
)
def criar_veiculo(
    dados: VeiculoEntrada, service: VeiculosServiceDep, request: Request, response: Response
) -> VeiculoSaida:
    veiculo = service.criar(dados)
    response.headers["Location"] = request.url_for("obter_veiculo", veiculo_id=veiculo.id).path
    return veiculo


@veiculos_router.put(
    "/{veiculo_id}",
    response_model=VeiculoSaida,
    summary="Edita um veículo ativo (Morador)",
    dependencies=[Depends(require_permission("veiculos:editar"))],
    responses={
        **_ERROS_VEICULOS,
        409: {
            "description": (
                "Veículo removido (`veiculo_removido`) ou placa repetida na unidade "
                "(`placa_ja_cadastrada_na_unidade`)."
            )
        },
        422: {"description": "Entrada inválida ou tentativa de trocar a unidade."},
    },
)
def atualizar_veiculo(
    veiculo_id: uuid.UUID, dados: VeiculoAtualizacao, service: VeiculosServiceDep
) -> VeiculoSaida:
    return service.atualizar(veiculo_id, dados)


@veiculos_router.post(
    "/{veiculo_id}/remocao",
    response_model=VeiculoSaida,
    summary="Remove (desativa) um veículo (Morador)",
    dependencies=[Depends(require_permission("veiculos:desativar"))],
    responses={
        **_ERROS_VEICULOS,
        409: {"description": "Veículo já removido (`veiculo_ja_removido`)."},
    },
)
def remover_veiculo(veiculo_id: uuid.UUID, service: VeiculosServiceDep) -> VeiculoSaida:
    return service.remover(veiculo_id)
