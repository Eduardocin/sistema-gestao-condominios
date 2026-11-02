import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.condominios import aprovacao_service
from app.modules.condominios.aprovacao_schemas import (
    ChaveGeradaOut,
    ChaveRevogadaOut,
    ChaveValidadaOut,
    CondominioPendenteOut,
    DecisaoCondominioOut,
    RejeitarCondominioRequest,
    StatusSolicitacaoOut,
    ValidarChaveRequest,
)

router = APIRouter(prefix="/condominios", tags=["condominios-aprovacao"])

SessionDep = Annotated[Session, Depends(get_session)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]
TokenSolicitacaoDep = Annotated[
    str, Header(alias="X-Token-Solicitacao", min_length=32, max_length=128)
]


@router.get(
    "/aprovacoes/pendentes",
    response_model=list[CondominioPendenteOut],
    summary="Listar condomínios aguardando aprovação da plataforma",
)
def listar_pendentes(session: SessionDep, autenticado: UsuarioDep) -> list[dict]:
    return aprovacao_service.listar_pendentes(session, administrador=autenticado.usuario)


@router.post(
    "/{condominio_id}/aprovar",
    response_model=ChaveGeradaOut,
    summary="Aprovar condomínio e gerar chave de acesso",
)
def aprovar_condominio(
    condominio_id: uuid.UUID,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return aprovacao_service.aprovar(
        session,
        condominio_id=condominio_id,
        administrador=autenticado.usuario,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/{condominio_id}/rejeitar",
    response_model=DecisaoCondominioOut,
    summary="Rejeitar condomínio com justificativa obrigatória",
)
def rejeitar_condominio(
    condominio_id: uuid.UUID,
    dados: RejeitarCondominioRequest,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return aprovacao_service.rejeitar(
        session,
        condominio_id=condominio_id,
        administrador=autenticado.usuario,
        motivo=dados.motivo,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/{condominio_id}/chaves/regenerar",
    response_model=ChaveGeradaOut,
    summary="Revogar a chave vigente e gerar uma nova",
)
def regenerar_chave(
    condominio_id: uuid.UUID,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return aprovacao_service.regenerar_chave(
        session,
        condominio_id=condominio_id,
        administrador=autenticado.usuario,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/{condominio_id}/chaves/revogar",
    response_model=ChaveRevogadaOut,
    summary="Revogar a chave vigente sem emitir outra",
)
def revogar_chave(
    condominio_id: uuid.UUID,
    session: SessionDep,
    autenticado: UsuarioDep,
    request: Request,
) -> dict:
    return aprovacao_service.revogar_chave(
        session,
        condominio_id=condominio_id,
        administrador=autenticado.usuario,
        ip=request.client.host if request.client else None,
    )


@router.post(
    "/chaves/validar",
    response_model=ChaveValidadaOut,
    summary="Validar uma chave de acesso sem consumi-la",
)
def validar_chave(dados: ValidarChaveRequest, session: SessionDep) -> dict:
    return aprovacao_service.validar_chave(session, codigo=dados.chave_acesso)


@router.get(
    "/solicitacoes/{condominio_id}",
    response_model=StatusSolicitacaoOut,
    summary="Consultar status e motivo da decisão da solicitação",
)
def status_solicitacao(
    condominio_id: uuid.UUID,
    token: TokenSolicitacaoDep,
    session: SessionDep,
) -> dict:
    return aprovacao_service.status_solicitacao(session, condominio_id=condominio_id, token=token)
