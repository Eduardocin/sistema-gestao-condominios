"""Rotas de `/api/v1/ocorrencias` (convivencia.md, §5).

A ordem da matriz está nas dependências: `require_permission` (perfil, 403) roda antes de o corpo
ser validado (422) e do service. A unidade e a aba (passo 4) ficam no service, porque aqui o
`unidade_id` vem da query, do corpo ou da própria ocorrência. Só traduzimos HTTP.
"""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.ocorrencias.repository import FiltrosOcorrencias
from app.modules.ocorrencias.schemas import (
    ComentarioEntrada,
    InteracaoSaida,
    OcorrenciaEntrada,
    OcorrenciaSaida,
    PaginaDeOcorrencias,
    ReaberturaEntrada,
    ResolucaoEntrada,
    RespostaEntrada,
)
from app.modules.ocorrencias.service import OcorrenciasService

router = APIRouter(prefix="/ocorrencias", tags=["ocorrencias"])


def exigir_morador(
    contexto: Annotated[ContextoCondominio, Depends(require_permission("ocorrencias:editar"))],
) -> None:
    """Comentar e reabrir são só do Morador (US-704).

    A matriz também dá `editar` à Administração (responder e resolver), então a permissão sozinha
    não basta aqui. Roda antes da validação do corpo.
    """
    if contexto.perfil != Perfil.MORADOR:
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)


def exigir_administracao(
    contexto: Annotated[ContextoCondominio, Depends(require_permission("ocorrencias:editar"))],
) -> None:
    """Responder e resolver são só da Administração.

    A matriz dá `editar` ao Morador (comentar e reabrir, US-704), então a permissão sozinha
    não basta aqui. Roda antes da validação do corpo, como o resto da matriz.
    """
    if contexto.perfil != Perfil.ADMINISTRACAO:
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)


def get_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> OcorrenciasService:
    # O contexto vem do token + banco, nunca do cliente.
    return OcorrenciasService(session, contexto)


ServiceDep = Annotated[OcorrenciasService, Depends(get_service)]


_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil sem permissão ou aba Ocorrências Sem Acesso (`forbidden`)."},
    404: {"description": "Ocorrência ou unidade inexistente ou de outro condomínio."},
}


@router.post(
    "",
    response_model=OcorrenciaSaida,
    status_code=201,
    summary="Abre uma ocorrência (Morador)",
    dependencies=[Depends(require_permission("ocorrencias:criar"))],
    responses={
        **_ERROS,
        422: {"description": "Entrada inválida ou anexo inexistente/inválido."},
    },
)
def criar_ocorrencia(
    dados: OcorrenciaEntrada, service: ServiceDep, request: Request, response: Response
) -> OcorrenciaSaida:
    ocorrencia = service.criar(dados)
    response.headers["Location"] = request.url_for(
        "obter_ocorrencia", ocorrencia_id=ocorrencia.id
    ).path
    return ocorrencia


@router.get(
    "",
    response_model=PaginaDeOcorrencias,
    summary="Lista ocorrências da unidade (Morador) ou do condomínio (Administração)",
    dependencies=[Depends(require_permission("ocorrencias:ver"))],
    responses=_ERROS,
)
def listar_ocorrencias(
    service: ServiceDep,
    # Morador: obrigatório. Administração: filtro opcional.
    unidade_id: uuid.UUID | None = None,
    # Filtros só da Administração; para o Morador são ignorados.
    de: date | None = None,
    ate: date | None = None,
    status: Literal["em_aberto", "resolvida"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeOcorrencias:
    return service.listar(
        unidade_id=unidade_id,
        filtros=FiltrosOcorrencias(status=status, de=de, ate=ate),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{ocorrencia_id}",
    response_model=OcorrenciaSaida,
    summary="Detalha uma ocorrência com o histórico",
    dependencies=[Depends(require_permission("ocorrencias:ver"))],
    responses=_ERROS,
)
def obter_ocorrencia(ocorrencia_id: uuid.UUID, service: ServiceDep) -> OcorrenciaSaida:
    return service.obter(ocorrencia_id)


@router.post(
    "/{ocorrencia_id}/respostas",
    response_model=InteracaoSaida,
    status_code=201,
    summary="Responde uma ocorrência (Administração)",
    dependencies=[Depends(exigir_administracao)],
    responses=_ERROS,
)
def responder_ocorrencia(
    ocorrencia_id: uuid.UUID, dados: RespostaEntrada, service: ServiceDep
) -> InteracaoSaida:
    return service.responder(ocorrencia_id, dados)


@router.post(
    "/{ocorrencia_id}/resolucao",
    response_model=OcorrenciaSaida,
    summary="Resolve uma ocorrência em aberto (Administração)",
    dependencies=[Depends(exigir_administracao)],
    responses={
        **_ERROS,
        409: {"description": "Ocorrência já resolvida (`reason: ocorrencia_ja_resolvida`)."},
    },
)
def resolver_ocorrencia(
    ocorrencia_id: uuid.UUID,
    dados: ResolucaoEntrada,
    service: ServiceDep,
    request: Request,
) -> OcorrenciaSaida:
    return service.resolver(ocorrencia_id, dados, ip=ip_do_cliente(request))


@router.post(
    "/{ocorrencia_id}/comentarios",
    response_model=InteracaoSaida,
    status_code=201,
    summary="Comenta uma ocorrência, em qualquer estado (Morador)",
    dependencies=[Depends(exigir_morador)],
    responses={
        **_ERROS,
        422: {"description": "Texto inválido ou anexo inexistente/inválido."},
    },
)
def comentar_ocorrencia(
    ocorrencia_id: uuid.UUID, dados: ComentarioEntrada, service: ServiceDep
) -> InteracaoSaida:
    return service.comentar(ocorrencia_id, dados)


@router.post(
    "/{ocorrencia_id}/reabertura",
    response_model=OcorrenciaSaida,
    summary="Reabre uma ocorrência resolvida (Morador)",
    dependencies=[Depends(exigir_morador)],
    responses={
        **_ERROS,
        409: {"description": "Ocorrência não resolvida (`reason: ocorrencia_nao_resolvida`)."},
    },
)
def reabrir_ocorrencia(
    ocorrencia_id: uuid.UUID,
    dados: ReaberturaEntrada,
    service: ServiceDep,
    request: Request,
) -> OcorrenciaSaida:
    return service.reabrir(ocorrencia_id, dados, ip=ip_do_cliente(request))
