"""Rotas de `/api/v1/areas-comuns` e `/api/v1/reservas` (convivencia.md, seções 2 e 4).

A ordem da matriz está nas dependências: `require_permission` (perfil, 403) roda antes de o corpo
ser validado (422) e do service. A unidade e a aba (passo 4) ficam no service, porque aqui o
`unidade_id` vem da query, do corpo ou da própria reserva, não da URL. Só traduzimos HTTP.
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auth.autorizacao import (
    MENSAGEM_SEM_PERMISSAO,
    registrar_negacao,
    require_permission,
)
from app.modules.auth.dependencies import ContextoDep
from app.modules.permissoes_aba.router import ip_do_cliente
from app.modules.reservas.models import AreaComum
from app.modules.reservas.repository import FiltrosAdministracao
from app.modules.reservas.schemas import (
    AcaoVazia,
    AgendaSaida,
    AreaComumEntrada,
    AreaComumSaida,
    CalendarioSaida,
    CancelamentoEntrada,
    PaginaDeAreas,
    PaginaDeReservas,
    ReservaEntrada,
    ReservaSaida,
)
from app.modules.reservas.service import AreasComunsService, ReservasService

areas_router = APIRouter(prefix="/areas-comuns", tags=["areas-comuns"])
reservas_router = APIRouter(prefix="/reservas", tags=["reservas"])

RelogioDep = Annotated[Relogio, Depends(get_relogio)]


def get_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep, relogio: RelogioDep
) -> AreasComunsService:
    # O contexto vem do token + banco, nunca do cliente.
    return AreasComunsService(session, contexto, relogio)


def get_reservas_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep, relogio: RelogioDep
) -> ReservasService:
    return ReservasService(session, contexto, relogio)


ServiceDep = Annotated[AreasComunsService, Depends(get_service)]
ReservasDep = Annotated[ReservasService, Depends(get_reservas_service)]


def somente_morador(
    contexto: Annotated[ContextoCondominio, Depends(require_permission("reservas:ver"))],
) -> ContextoCondominio:
    """Agenda e calendário são telas do Morador: a Administração tem `reservas:ver` na matriz,
    mas para ela essas rotas não existem (403, igual a um perfil sem permissão)."""
    if contexto.perfil != Perfil.MORADOR:
        registrar_negacao(
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
            perfil=contexto.perfil,
            permissao="reservas:agenda",
        )
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    return contexto


_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil sem permissão (`forbidden`)."},
}
_ERRO_404: dict[int | str, dict[str, Any]] = {
    404: {"description": "Área inexistente, de outro condomínio ou desativada para o Morador."}
}


def _saida(area: AreaComum) -> AreaComumSaida:
    return AreaComumSaida.model_validate(area)


@areas_router.get(
    "",
    response_model=PaginaDeAreas,
    summary="Lista as áreas comuns (Morador: só as ativas)",
    dependencies=[Depends(require_permission("areas_comuns:ver"))],
    responses=_ERROS,
)
def listar_areas(
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    # Só vale para a Administração; para o Morador a lista é sempre só de áreas ativas.
    ativa: bool | None = None,
) -> PaginaDeAreas:
    pagina = service.listar(page=page, page_size=page_size, ativa=ativa)
    return PaginaDeAreas(
        items=[_saida(area) for area in pagina.items],
        page=pagina.page,
        page_size=pagina.page_size,
        total=pagina.total,
    )


@areas_router.get(
    "/{area_id}",
    response_model=AreaComumSaida,
    summary="Detalha uma área comum",
    dependencies=[Depends(require_permission("areas_comuns:ver"))],
    responses={**_ERROS, **_ERRO_404},
)
def obter_area(area_id: uuid.UUID, service: ServiceDep) -> AreaComumSaida:
    return _saida(service.obter(area_id))


@areas_router.post(
    "",
    response_model=AreaComumSaida,
    status_code=201,
    summary="Cria uma área comum",
    dependencies=[Depends(require_permission("areas_comuns:criar"))],
    responses={
        **_ERROS,
        409: {"description": "Nome já usado no condomínio (`reason: nome_duplicado`)."},
        422: {"description": "Entrada inválida ou foto inexistente (`reason: foto_invalida`)."},
    },
)
def criar_area(
    dados: AreaComumEntrada, service: ServiceDep, request: Request, response: Response
) -> AreaComumSaida:
    area = service.criar(dados)
    response.headers["Location"] = request.url_for("obter_area", area_id=area.id).path
    return _saida(area)


@areas_router.put(
    "/{area_id}",
    response_model=AreaComumSaida,
    summary="Substitui os campos editáveis de uma área comum",
    dependencies=[Depends(require_permission("areas_comuns:editar"))],
    responses={
        **_ERROS,
        **_ERRO_404,
        409: {
            "description": "Nome duplicado (`nome_duplicado`) ou reservas ativas fora do novo "
            "horário (`reservas_fora_do_horario`)."
        },
        422: {"description": "Entrada inválida ou foto inexistente (`reason: foto_invalida`)."},
    },
)
def editar_area(area_id: uuid.UUID, dados: AreaComumEntrada, service: ServiceDep) -> AreaComumSaida:
    return _saida(service.editar(area_id, dados))


@areas_router.post(
    "/{area_id}/desativacao",
    response_model=AreaComumSaida,
    summary="Desativa a área (reservas já feitas continuam ativas)",
    dependencies=[Depends(require_permission("areas_comuns:desativar"))],
    responses={
        **_ERROS,
        **_ERRO_404,
        409: {"description": "Área já desativada (`reason: area_ja_desativada`)."},
    },
)
def desativar_area(
    area_id: uuid.UUID, service: ServiceDep, dados: AcaoVazia | None = None
) -> AreaComumSaida:
    return _saida(service.desativar(area_id))


@areas_router.post(
    "/{area_id}/reativacao",
    response_model=AreaComumSaida,
    summary="Reativa uma área desativada",
    dependencies=[Depends(require_permission("areas_comuns:editar"))],
    responses={
        **_ERROS,
        **_ERRO_404,
        409: {"description": "Área já ativa (`reason: area_ja_ativa`)."},
    },
)
def reativar_area(
    area_id: uuid.UUID, service: ServiceDep, dados: AcaoVazia | None = None
) -> AreaComumSaida:
    return _saida(service.reativar(area_id))


# --- agenda e calendário (Morador) ------------------------------------------------------------

_ERROS_UNIDADE: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil sem permissão ou aba Reservas Sem Acesso (`forbidden`)."},
    404: {"description": "Unidade alheia, ou área inexistente, desativada ou de outro condomínio."},
}


@areas_router.get(
    "/{area_id}/agenda",
    response_model=AgendaSaida,
    response_model_exclude_unset=True,  # `reserva_id` só aparece em `da_minha_unidade`
    summary="Grade de 1 em 1 hora do dia (Morador)",
    dependencies=[Depends(somente_morador)],
    responses=_ERROS_UNIDADE,
)
def agenda(
    area_id: uuid.UUID, unidade_id: uuid.UUID, data: date, service: ReservasDep
) -> AgendaSaida:
    return service.agenda(area_id, unidade_id, data)


@areas_router.get(
    "/{area_id}/calendario",
    response_model=CalendarioSaida,
    summary="Dias do mês com bloqueio ou com reserva da unidade (Morador)",
    dependencies=[Depends(somente_morador)],
    responses=_ERROS_UNIDADE,
)
def calendario(
    area_id: uuid.UUID,
    unidade_id: uuid.UUID,
    mes: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])],
    service: ReservasDep,
) -> CalendarioSaida:
    return service.calendario(area_id, unidade_id, mes)


# --- reservas ---------------------------------------------------------------------------------


@reservas_router.post(
    "",
    response_model=ReservaSaida,
    response_model_exclude_unset=True,
    status_code=201,
    summary="Reserva um slot de 1 hora (Morador)",
    dependencies=[Depends(require_permission("reservas:criar"))],
    responses={
        **_ERROS_UNIDADE,
        409: {"description": "`area_bloqueada`, `reserva_duplicada_unidade` ou `horario_ocupado`."},
        422: {
            "description": "Entrada inválida, `hora_invalida`, `fora_do_funcionamento` ou "
            "`horario_passado`."
        },
    },
)
def criar_reserva(
    dados: ReservaEntrada, service: ReservasDep, request: Request, response: Response
) -> ReservaSaida:
    reserva = service.criar(dados, ip=ip_do_cliente(request))
    response.headers["Location"] = request.url_for("obter_reserva", reserva_id=reserva.id).path
    return reserva


@reservas_router.get(
    "",
    response_model=PaginaDeReservas,
    response_model_exclude_unset=True,
    summary="Reservas da unidade (Morador) ou do condomínio (Administração)",
    dependencies=[Depends(require_permission("reservas:ver"))],
    responses=_ERROS_UNIDADE,
)
def listar_reservas(
    service: ReservasDep,
    # Morador: obrigatório. Administração: filtro opcional.
    unidade_id: uuid.UUID | None = None,
    # Filtros só da Administração; para o Morador são ignorados.
    area_id: uuid.UUID | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    status: Literal["ativa", "cancelada"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeReservas:
    return service.listar(
        unidade_id=unidade_id,
        filtros=FiltrosAdministracao(
            area_id=area_id, data_de=data_de, data_ate=data_ate, status=status
        ),
        page=page,
        page_size=page_size,
    )


@reservas_router.get(
    "/{reserva_id}",
    response_model=ReservaSaida,
    response_model_exclude_unset=True,
    summary="Detalha uma reserva",
    dependencies=[Depends(require_permission("reservas:ver"))],
    responses=_ERROS_UNIDADE,
)
def obter_reserva(reserva_id: uuid.UUID, service: ReservasDep) -> ReservaSaida:
    return service.obter(reserva_id)


@reservas_router.post(
    "/{reserva_id}/cancelamento",
    response_model=ReservaSaida,
    response_model_exclude_unset=True,
    summary="Cancela uma reserva ativa (Morador: `{}`; Administração: motivo e responsável)",
    dependencies=[Depends(require_permission("reservas:desativar"))],
    responses={
        **_ERROS_UNIDADE,
        409: {"description": "`reserva_ja_cancelada` ou `reserva_encerrada`."},
        422: {"description": "Administração sem `motivo` ou `responsavel_id`, ou corpo inválido."},
    },
)
def cancelar_reserva(
    reserva_id: uuid.UUID,
    service: ReservasDep,
    request: Request,
    dados: CancelamentoEntrada | None = None,
) -> ReservaSaida:
    return service.cancelar(reserva_id, dados or CancelamentoEntrada(), ip=ip_do_cliente(request))


# O agregador /api/v1 inclui só este.
router = APIRouter()
router.include_router(areas_router)
router.include_router(reservas_router)
