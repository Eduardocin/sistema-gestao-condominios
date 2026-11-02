import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.condominios import wizard_service
from app.modules.condominios.wizard_schemas import (
    AreasComunsRequest,
    BlocosRequest,
    DadosGeraisRequest,
    ResponsavelRequest,
    UnidadesRequest,
    WizardConcluidoOut,
    WizardIniciadoOut,
    WizardStatusOut,
)

router = APIRouter(prefix="/condominios/wizard", tags=["condominios-wizard"])

SessionDep = Annotated[Session, Depends(get_session)]
TokenDep = Annotated[str, Header(alias="X-Wizard-Token", min_length=32)]


@router.post(
    "",
    response_model=WizardIniciadoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar cadastro de condomínio",
)
def iniciar_wizard(session: SessionDep) -> WizardIniciadoOut:
    return WizardIniciadoOut.model_validate(wizard_service.iniciar(session))


@router.get(
    "/{rascunho_id}",
    response_model=WizardStatusOut,
    summary="Retomar cadastro de condomínio",
)
def obter_wizard(rascunho_id: uuid.UUID, token: TokenDep, session: SessionDep) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.obter_status(session, rascunho_id=rascunho_id, token=token)
    )


@router.put(
    "/{rascunho_id}/etapas/dados-gerais",
    response_model=WizardStatusOut,
    summary="Salvar dados gerais do condomínio",
)
def salvar_dados_gerais(
    rascunho_id: uuid.UUID,
    dados: DadosGeraisRequest,
    token: TokenDep,
    session: SessionDep,
) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.salvar_dados_gerais(
            session, rascunho_id=rascunho_id, token=token, dados=dados
        )
    )


@router.put(
    "/{rascunho_id}/etapas/blocos",
    response_model=WizardStatusOut,
    summary="Salvar blocos e torres",
)
def salvar_blocos(
    rascunho_id: uuid.UUID,
    dados: BlocosRequest,
    token: TokenDep,
    session: SessionDep,
) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.salvar_blocos(session, rascunho_id=rascunho_id, token=token, dados=dados)
    )


@router.put(
    "/{rascunho_id}/etapas/unidades",
    response_model=WizardStatusOut,
    summary="Configurar geração de unidades",
)
def salvar_unidades(
    rascunho_id: uuid.UUID,
    dados: UnidadesRequest,
    token: TokenDep,
    session: SessionDep,
) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.salvar_unidades(session, rascunho_id=rascunho_id, token=token, dados=dados)
    )


@router.put(
    "/{rascunho_id}/etapas/areas-comuns",
    response_model=WizardStatusOut,
    summary="Salvar áreas comuns",
)
def salvar_areas_comuns(
    rascunho_id: uuid.UUID,
    dados: AreasComunsRequest,
    token: TokenDep,
    session: SessionDep,
) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.salvar_areas_comuns(
            session, rascunho_id=rascunho_id, token=token, dados=dados
        )
    )


@router.put(
    "/{rascunho_id}/etapas/responsavel",
    response_model=WizardStatusOut,
    summary="Salvar dados da Administração responsável",
)
def salvar_responsavel(
    rascunho_id: uuid.UUID,
    dados: ResponsavelRequest,
    token: TokenDep,
    session: SessionDep,
) -> WizardStatusOut:
    return WizardStatusOut.model_validate(
        wizard_service.salvar_responsavel(
            session, rascunho_id=rascunho_id, token=token, dados=dados
        )
    )


@router.post(
    "/{rascunho_id}/finalizar",
    response_model=WizardConcluidoOut,
    summary="Concluir cadastro do condomínio e da Administração",
)
def finalizar_wizard(
    rascunho_id: uuid.UUID,
    token: TokenDep,
    session: SessionDep,
    request: Request,
) -> WizardConcluidoOut:
    resultado = wizard_service.finalizar(
        session,
        rascunho_id=rascunho_id,
        token=token,
        ip=request.client.host if request.client else None,
    )
    return WizardConcluidoOut.model_validate(resultado)
