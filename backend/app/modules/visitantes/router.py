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
    PaginaDeVisitantes,
    Situacao,
    VisitanteAtualizacao,
    VisitanteEntrada,
    VisitanteSaida,
)
from app.modules.visitantes.service import VisitantesService

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
