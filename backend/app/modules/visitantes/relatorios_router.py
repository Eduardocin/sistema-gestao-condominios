from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.db.session import get_session
from app.modules.auth.autorizacao import (
    MENSAGEM_SEM_PERMISSAO,
    registrar_negacao,
    require_permission,
)
from app.modules.auth.dependencies import ContextoDep
from app.modules.visitantes import relatorios_schemas as s
from app.modules.visitantes.relatorios_service import RelatoriosService
from app.modules.visitantes.schemas import Pagina

router = APIRouter(prefix="/relatorios", tags=["relatórios"])


def somente_administracao(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> RelatoriosService:
    if contexto.perfil != Perfil.ADMINISTRACAO:
        registrar_negacao(
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
            perfil=contexto.perfil,
            permissao="relatorios:administracao",
        )
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    return RelatoriosService(session, contexto)


Service = Annotated[RelatoriosService, Depends(somente_administracao)]
Filtros = Annotated[s.FiltrosRelatorio, Query()]


@router.get("/visitantes", dependencies=[Depends(require_permission("visitantes:ver"))])
def visitantes(service: Service, filtros: Filtros) -> Pagina[s.VisitaRelatorio]:
    return service.visitantes(filtros)


@router.get("/veiculos", dependencies=[Depends(require_permission("veiculos:ver"))])
def veiculos(service: Service, filtros: Filtros) -> Pagina[s.VeiculoRelatorio]:
    return service.veiculos_cadastrados(filtros)
