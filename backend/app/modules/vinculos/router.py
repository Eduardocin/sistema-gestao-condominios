import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.usuarios.models import Usuario
from app.modules.vinculos import schemas, service

router = APIRouter(tags=["vinculos-morador"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_conta_morador(
    autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
) -> Usuario:
    service.exigir_conta_morador(autenticado.usuario)
    return autenticado.usuario


def get_contexto_morador(
    contexto: Annotated[ContextoCondominio, Depends(require_permission("proprietarios:ver"))],
) -> ContextoCondominio:
    if contexto.perfil != "morador":
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")
    return contexto


MoradorDep = Annotated[Usuario, Depends(get_conta_morador)]
ContextoMorador = Annotated[ContextoCondominio, Depends(get_contexto_morador)]


@router.post("/vinculos/chave", status_code=201, response_model=schemas.VinculoSaida)
def vincular(
    dados: schemas.VinculoEntrada,
    usuario: MoradorDep,
    session: SessionDep,
    request: Request,
    response: Response,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.VinculoSaida:
    saida = service.vincular(session, usuario, dados, ip=ip_do_cliente(request), relogio=relogio)
    response.headers["Location"] = f"/api/v1/minhas-unidades/{saida.unidade.id}"
    return saida


@router.get("/minhas-unidades", response_model=schemas.PaginaMinhasUnidades)
def listar(
    contexto: ContextoMorador,
    session: SessionDep,
    filtros: Annotated[schemas.FiltrosMinhasUnidades, Query()],
) -> schemas.PaginaMinhasUnidades:
    return service.MinhasUnidadesService(session, contexto).listar(filtros)


@router.get("/minhas-unidades/{unidade_id}", response_model=schemas.MinhaUnidade)
def detalhe(
    unidade_id: uuid.UUID, contexto: ContextoMorador, session: SessionDep
) -> schemas.MinhaUnidade:
    return service.MinhasUnidadesService(session, contexto).detalhe(unidade_id)
