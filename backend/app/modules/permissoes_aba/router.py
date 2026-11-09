"""Rotas das permissões por aba: `/api/v1/unidades/{unidade_id}/moradores/...` (US-304).

A ordem da matriz está nas dependências de cada rota: o perfil primeiro (`require_permission`,
403), depois a unidade e a aba (`require_aba`, 404 e 403). Só então o corpo é validado (422) e
o service roda. Aqui só traduzimos HTTP <-> service.
"""

import ipaddress
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.autorizacao import require_aba, require_permission
from app.modules.auth.dependencies import ContextoDep
from app.modules.permissoes_aba.schemas import (
    AlterarPermissoesEntrada,
    MoradorSaida,
    PaginaDeMoradores,
)
from app.modules.permissoes_aba.service import PermissoesAbaService

router = APIRouter(prefix="/unidades/{unidade_id}/moradores", tags=["permissoes-aba"])


def get_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> PermissoesAbaService:
    return PermissoesAbaService(session, contexto)  # o contexto vem do token + banco, nunca do cliente


ServiceDep = Annotated[PermissoesAbaService, Depends(get_service)]

_ERROS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Token ausente ou inválido (`not_authenticated`)."},
    403: {"description": "Perfil ou aba sem acesso (`forbidden`)."},
    404: {"description": "Unidade ou morador inexistente, ou de outra unidade (`not_found`)."},
}


def ip_do_cliente(request: Request) -> str | None:
    """IP de quem chamou, para a auditoria. Se não for um IP válido, não guardamos nada."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


@router.get(
    "",
    response_model=PaginaDeMoradores,
    summary="Moradores da unidade com as permissões de cada um",
    dependencies=[Depends(require_permission("vinculos:ver")), Depends(require_aba("usuarios"))],
    responses=_ERROS,
)
def listar_moradores(
    unidade_id: uuid.UUID,
    service: ServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginaDeMoradores:
    pagina = service.listar_moradores(unidade_id, page=page, page_size=page_size)
    return PaginaDeMoradores(
        items=[MoradorSaida.model_validate(m) for m in pagina.items],
        page=pagina.page,
        page_size=pagina.page_size,
        total=pagina.total,
    )


@router.put(
    "/{morador_unidade_id}/permissoes",
    response_model=MoradorSaida,
    summary="Mudar Com Acesso/Sem Acesso das abas de um morador da unidade",
    dependencies=[
        Depends(require_permission("permissoes_aba:editar")),
        Depends(require_aba("usuarios")),
    ],
    responses={
        **_ERROS,
        409: {"description": "Seria retirada a aba Usuários do último que a tem (`conflict`)."},
    },
)
def alterar_permissoes(
    unidade_id: uuid.UUID,
    morador_unidade_id: uuid.UUID,
    dados: AlterarPermissoesEntrada,
    service: ServiceDep,
    request: Request,
) -> MoradorSaida:
    # O corpo já foi validado (só as 7 abas, só true/false); o service recebe nomes simples.
    abas: dict[str, bool] = {str(aba): acesso for aba, acesso in dados.abas.items()}
    morador = service.alterar_permissoes(
        unidade_id, morador_unidade_id, abas, ip=ip_do_cliente(request)
    )
    return MoradorSaida.model_validate(morador)
