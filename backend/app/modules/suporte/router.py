"""Rotas de chamados de suporte: `/chamados` (Administração) e `/plataforma/chamados` (ADM).

A permissão (403) roda antes do corpo (422) e do service. O condomínio vem do token, nunca da
requisição; `condominio_id` só aparece como filtro da fila do ADM.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission, require_platform_permission
from app.modules.suporte.schemas import (
    ChamadoEntrada,
    ChamadoSaida,
    ConsultaDaAdministracao,
    ConsultaDaPlataforma,
    EncerramentoEntrada,
    MensagemEntrada,
    MensagemSaida,
    PaginaDeChamados,
)
from app.modules.suporte.service import ChamadosDaAdministracao, ChamadosDaPlataforma

router = APIRouter(prefix="/chamados", tags=["suporte"])
plataforma_router = APIRouter(prefix="/plataforma/chamados", tags=["suporte"])

SessionDep = Annotated[Session, Depends(get_session)]
VerComoAdministracao = Annotated[ContextoCondominio, Depends(require_permission("suporte:ver"))]
AbrirComoAdministracao = Annotated[ContextoCondominio, Depends(require_permission("suporte:criar"))]
VerComoPlataforma = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("suporte:ver"))
]
AtenderComoPlataforma = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("suporte:editar"))
]

_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Autenticação necessária."},
    403: {"description": "Perfil sem permissão (`forbidden`)."},
    404: {"description": "Chamado inexistente ou de outro condomínio."},
}
_ENCERRADO: dict[int | str, dict[str, Any]] = {
    409: {"description": "Chamado encerrado (`chamado_encerrado`)."}
}


# --- Administração ----------------------------------------------------------------------------


@router.post(
    "",
    response_model=ChamadoSaida,
    status_code=201,
    summary="Abrir um chamado de suporte (Administração)",
    responses={**_ERROS, 422: {"description": "Entrada ou anexo inválido."}},
)
def abrir(
    dados: ChamadoEntrada, contexto: AbrirComoAdministracao, session: SessionDep
) -> ChamadoSaida:
    return ChamadosDaAdministracao(session, contexto).abrir(dados)


@router.get(
    "",
    response_model=PaginaDeChamados,
    summary="Listar os chamados do condomínio (Administração)",
    responses=_ERROS,
)
def listar(
    contexto: VerComoAdministracao,
    session: SessionDep,
    consulta: Annotated[ConsultaDaAdministracao, Query()],
) -> PaginaDeChamados:
    return ChamadosDaAdministracao(session, contexto).listar(consulta)


@router.get(
    "/{chamado_id}",
    response_model=ChamadoSaida,
    summary="Consultar um chamado com as mensagens (Administração)",
    responses=_ERROS,
)
def obter(
    chamado_id: uuid.UUID, contexto: VerComoAdministracao, session: SessionDep
) -> ChamadoSaida:
    return ChamadosDaAdministracao(session, contexto).obter(chamado_id)


@router.post(
    "/{chamado_id}/mensagens",
    response_model=MensagemSaida,
    status_code=201,
    summary="Responder um chamado (Administração)",
    responses={**_ERROS, **_ENCERRADO},
)
def responder(
    chamado_id: uuid.UUID,
    dados: MensagemEntrada,
    contexto: AbrirComoAdministracao,
    session: SessionDep,
) -> MensagemSaida:
    return ChamadosDaAdministracao(session, contexto).responder(chamado_id, dados)


# --- ADM da plataforma ------------------------------------------------------------------------


@plataforma_router.get(
    "",
    response_model=PaginaDeChamados,
    summary="Fila de chamados (ADM)",
    responses=_ERROS,
)
def listar_fila(
    contexto: VerComoPlataforma,
    session: SessionDep,
    consulta: Annotated[ConsultaDaPlataforma, Query()],
) -> PaginaDeChamados:
    return ChamadosDaPlataforma(session, contexto).listar(consulta)


@plataforma_router.get(
    "/{chamado_id}",
    response_model=ChamadoSaida,
    summary="Consultar um chamado com as mensagens (ADM)",
    responses=_ERROS,
)
def obter_da_plataforma(
    chamado_id: uuid.UUID, contexto: VerComoPlataforma, session: SessionDep
) -> ChamadoSaida:
    return ChamadosDaPlataforma(session, contexto).obter(chamado_id)


@plataforma_router.post(
    "/{chamado_id}/mensagens",
    response_model=MensagemSaida,
    status_code=201,
    summary="Responder um chamado (ADM)",
    responses={**_ERROS, **_ENCERRADO},
)
def responder_como_plataforma(
    chamado_id: uuid.UUID,
    dados: MensagemEntrada,
    contexto: AtenderComoPlataforma,
    session: SessionDep,
    request: Request,
) -> MensagemSaida:
    return ChamadosDaPlataforma(session, contexto, ip=ip_do_cliente(request)).responder(
        chamado_id, dados
    )


@plataforma_router.post(
    "/{chamado_id}/encerramento",
    response_model=ChamadoSaida,
    summary="Encerrar um chamado (ADM)",
    responses={
        **_ERROS,
        409: {"description": "Já encerrado (`chamado_ja_encerrado`)."},
    },
)
def encerrar(
    chamado_id: uuid.UUID,
    _dados: EncerramentoEntrada,
    contexto: AtenderComoPlataforma,
    session: SessionDep,
    request: Request,
) -> ChamadoSaida:
    return ChamadosDaPlataforma(session, contexto, ip=ip_do_cliente(request)).encerrar(chamado_id)
