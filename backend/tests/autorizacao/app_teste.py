"""Rotas de mentira, só dos testes da autorização central (TASK-19).

Para cada par "recurso:acao" da matriz existe uma rota que não faz nada além de responder 200. Assim
dá para testar a dependência `require_permission` com todos os perfis, sem depender de módulos de
negócio que ainda não existem. Nada disto entra na API real.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.orm import Session

from app.core import permissoes
from app.core.contexto import ContextoCondominio
from app.db.session import get_session
from app.main import create_app
from app.modules.auth.autorizacao import (
    garantir_acesso_a_unidade,
    require_permission,
    require_platform_permission,
)

condominio = APIRouter(prefix="/permissoes-teste")
plataforma = APIRouter(prefix="/plataforma-teste")
unidades = APIRouter(prefix="/unidades-teste")


def _ok() -> dict[str, bool]:
    return {"ok": True}


# Uma rota por combinação, nas duas variantes: /permissoes-teste/<recurso>/<acao>
for _recurso in sorted(permissoes.RECURSOS):
    for _acao in sorted(permissoes.NOMES_DAS_ACOES):
        _permissao = f"{_recurso}:{_acao}"
        condominio.add_api_route(
            f"/{_recurso}/{_acao}",
            _ok,
            methods=["GET"],
            dependencies=[Depends(require_permission(_permissao))],
        )
        plataforma.add_api_route(
            f"/{_recurso}/{_acao}",
            _ok,
            methods=["GET"],
            dependencies=[Depends(require_platform_permission(_permissao))],
        )


@unidades.get("/{unidade_id}")
def ver_unidade(
    unidade_id: uuid.UUID,
    contexto: Annotated[ContextoCondominio, Depends(require_permission("estrutura:ver"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, bool]:
    # É assim que um service usa o passo 4: uma chamada antes de mexer na unidade.
    garantir_acesso_a_unidade(session, contexto, unidade_id)
    return {"ok": True}


def montar_app() -> FastAPI:
    app = create_app()
    for roteador in (condominio, plataforma, unidades):
        app.include_router(roteador, prefix="/api/v1")
    return app
