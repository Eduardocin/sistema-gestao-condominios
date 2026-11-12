from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auth.presentation import resposta_de_sessao
from app.modules.auth.schemas import LoginResponse
from app.modules.contas.schemas import CadastroAdministracao, CadastroMorador
from app.modules.contas.service import cadastrar

router = APIRouter(prefix="/contas", tags=["contas"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/morador", response_model=LoginResponse, status_code=201)
def cadastrar_morador(
    dados: CadastroMorador, session: SessionDep, settings: SettingsDep
) -> LoginResponse:
    return resposta_de_sessao(cadastrar(session, dados, "morador", settings))


@router.post("/administracao", response_model=LoginResponse, status_code=201)
def cadastrar_administracao(
    dados: CadastroAdministracao, session: SessionDep, settings: SettingsDep
) -> LoginResponse:
    return resposta_de_sessao(cadastrar(session, dados, "administracao", settings))
