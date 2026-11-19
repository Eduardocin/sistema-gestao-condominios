import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_permission
from app.modules.unidades import schemas
from app.modules.unidades.service import UnidadesService

router = APIRouter(prefix="/unidades", tags=["unidades"])
SessionDep = Annotated[Session, Depends(get_session)]
# Ler unidades aqui inclui dados de proprietário e chave: escopo só Administração.
AdministracaoVer = Annotated[ContextoCondominio, Depends(require_permission("chaves_acesso:ver"))]
AdministracaoCriar = Annotated[
    ContextoCondominio, Depends(require_permission("chaves_acesso:criar"))
]
AdministracaoEditar = Annotated[
    ContextoCondominio, Depends(require_permission("chaves_acesso:editar"))
]
AdministracaoRevogar = Annotated[
    ContextoCondominio, Depends(require_permission("chaves_acesso:desativar"))
]
ProprietarioEditar = Annotated[
    ContextoCondominio, Depends(require_permission("proprietarios:editar"))
]


@router.get("", response_model=schemas.PaginaUnidades)
def listar(
    contexto: AdministracaoVer,
    session: SessionDep,
    filtros: Annotated[schemas.FiltrosUnidades, Query()],
) -> schemas.PaginaUnidades:
    return UnidadesService(session, contexto).listar(filtros)


@router.get("/{id}", response_model=schemas.UnidadeDetalhe)
def detalhe(
    id: uuid.UUID, contexto: AdministracaoVer, session: SessionDep
) -> schemas.UnidadeDetalhe:
    return UnidadesService(session, contexto).detalhe(id)


@router.put("/{id}/proprietario", response_model=schemas.ProprietarioSaida)
def proprietario(
    id: uuid.UUID,
    dados: schemas.ProprietarioEntrada,
    contexto: ProprietarioEditar,
    session: SessionDep,
    request: Request,
) -> schemas.ProprietarioSaida:
    return UnidadesService(session, contexto).editar_proprietario(
        id, dados, ip=ip_do_cliente(request)
    )


@router.get("/{id}/chave", response_model=schemas.ChaveSaida)
def chave(id: uuid.UUID, contexto: AdministracaoVer, session: SessionDep) -> schemas.ChaveSaida:
    return UnidadesService(session, contexto).consultar_chave(id)


@router.post("/{id}/chave", status_code=201, response_model=schemas.ChaveSaida)
def gerar(
    id: uuid.UUID,
    dados: schemas.AcaoChave,
    contexto: AdministracaoCriar,
    session: SessionDep,
    request: Request,
    response: Response,
    relogio: Annotated[Relogio, Depends(get_relogio)],
):
    saida = UnidadesService(session, contexto).alterar_chave(
        id, dados.responsavel_id, "gerar", ip=ip_do_cliente(request), relogio=relogio
    )
    response.headers["Location"] = f"/api/v1/unidades/{id}/chave"
    return saida


@router.post("/{id}/chave/regeneracao", response_model=schemas.ChaveSaida)
def regenerar(
    id: uuid.UUID,
    dados: schemas.AcaoChave,
    contexto: AdministracaoEditar,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
):
    return UnidadesService(session, contexto).alterar_chave(
        id, dados.responsavel_id, "regenerar", ip=ip_do_cliente(request), relogio=relogio
    )


@router.post("/{id}/chave/revogacao", response_model=schemas.RevogacaoSaida)
def revogar(
    id: uuid.UUID,
    dados: schemas.AcaoChave,
    contexto: AdministracaoRevogar,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
):
    return UnidadesService(session, contexto).alterar_chave(
        id, dados.responsavel_id, "revogar", ip=ip_do_cliente(request), relogio=relogio
    )
