import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.unidades import service
from app.modules.unidades.schemas import (
    AprovarVinculoUnidadeRequest,
    DecisaoVinculoUnidadeOut,
    RejeitarVinculoUnidadeRequest,
    SolicitacaoCriadaOut,
    SolicitacaoVinculoUnidadeOut,
    SolicitarVinculoUnidadeRequest,
)

router = APIRouter(prefix="/unidades/vinculos", tags=["vinculos-morador-unidade"])

SessionDep = Annotated[Session, Depends(get_session)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]


@router.post(
    "/solicitar",
    response_model=SolicitacaoCriadaOut,
    status_code=201,
    summary="Solicitar vínculo do morador com uma unidade usando chave de acesso",
)
def solicitar_vinculo(
    dados: SolicitarVinculoUnidadeRequest,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return service.solicitar_vinculo(
        session,
        morador=autenticado.usuario,
        dados=dados,
        ip=request.client.host if request.client else None,
    )


@router.get(
    "/pendentes",
    response_model=list[SolicitacaoVinculoUnidadeOut],
    summary="Listar solicitações de vínculo pendentes da Administração",
)
def listar_pendentes(
    session: SessionDep,
    autenticado: UsuarioDep,
) -> list[dict]:
    return service.listar_pendentes(
        session,
        administrador=autenticado.usuario,
        condominio_id=autenticado.condominio_id,
    )


@router.post(
    "/{solicitacao_id}/aprovar",
    response_model=DecisaoVinculoUnidadeOut,
    summary="Aprovar vínculo do morador com a unidade",
)
def aprovar_vinculo(
    solicitacao_id: uuid.UUID,
    dados: AprovarVinculoUnidadeRequest,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return service.aprovar_vinculo(
        session,
        solicitacao_id=solicitacao_id,
        administrador=autenticado.usuario,
        condominio_id=autenticado.condominio_id,
        nome_responsavel=dados.nome_responsavel,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/{solicitacao_id}/rejeitar",
    response_model=DecisaoVinculoUnidadeOut,
    summary="Rejeitar vínculo do morador com a unidade",
)
def rejeitar_vinculo(
    solicitacao_id: uuid.UUID,
    dados: RejeitarVinculoUnidadeRequest,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return service.rejeitar_vinculo(
        session,
        solicitacao_id=solicitacao_id,
        administrador=autenticado.usuario,
        condominio_id=autenticado.condominio_id,
        motivo=dados.motivo,
        nome_responsavel=dados.nome_responsavel,
        ip=request.client.host if request.client else None,
    )
