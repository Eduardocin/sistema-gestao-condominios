from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.auth.presentation import resposta_de_sessao
from app.modules.auth.schemas import LoginResponse
from app.modules.contas.schemas import (
    CadastroAdministracao,
    CadastroMorador,
    ContaSaida,
    EdicaoConta,
)
from app.modules.contas.service import cadastrar, editar_propria_conta

router = APIRouter(prefix="/contas", tags=["contas"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]


@router.post("/morador", response_model=LoginResponse, status_code=201)
def cadastrar_morador(
    dados: CadastroMorador, session: SessionDep, settings: SettingsDep, request: Request
) -> LoginResponse:
    return resposta_de_sessao(
        cadastrar(session, dados, "morador", settings, ip=ip_do_cliente(request))
    )


@router.post("/administracao", response_model=LoginResponse, status_code=201)
def cadastrar_administracao(
    dados: CadastroAdministracao, session: SessionDep, settings: SettingsDep, request: Request
) -> LoginResponse:
    return resposta_de_sessao(
        cadastrar(session, dados, "administracao", settings, ip=ip_do_cliente(request))
    )


@router.get("/me", response_model=ContaSaida)
def consultar_propria_conta(autenticado: UsuarioDep) -> ContaSaida:
    return ContaSaida.model_validate(autenticado.usuario)


@router.put("/me", response_model=ContaSaida)
def editar_conta(
    dados: EdicaoConta, autenticado: UsuarioDep, session: SessionDep, request: Request
) -> ContaSaida:
    return editar_propria_conta(session, autenticado.usuario, dados, ip=ip_do_cliente(request))
