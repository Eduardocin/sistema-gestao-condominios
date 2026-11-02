"""Rotas de cadastro e perfil pessoal de usuários."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    CadastroAdministracaoRequest,
    CadastroFuncionarioRequest,
    CadastroMoradorRequest,
    EditarUsuarioRequest,
    UsuarioOut,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

SessionDep = Annotated[Session, Depends(get_session)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]


@router.post(
    "/moradores",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar conta de morador pendente",
)
def cadastrar_morador(
    dados: CadastroMoradorRequest, session: SessionDep, request: Request
) -> UsuarioOut:
    usuario = service.cadastrar_morador(
        session, dados=dados, ip=request.client.host if request.client else None
    )
    return UsuarioOut.model_validate(usuario)


@router.post(
    "/funcionarios",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar funcionário pendente com chave de acesso",
)
def cadastrar_funcionario(
    dados: CadastroFuncionarioRequest, session: SessionDep, request: Request
) -> UsuarioOut:
    usuario = service.cadastrar_funcionario(
        session, dados=dados, ip=request.client.host if request.client else None
    )
    return UsuarioOut.model_validate(usuario)


@router.post(
    "/administracao",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar conta de administração vinculada a condomínio",
)
def cadastrar_administracao(
    dados: CadastroAdministracaoRequest, session: SessionDep, request: Request
) -> UsuarioOut:
    usuario = service.cadastrar_administracao(
        session, dados=dados, ip=request.client.host if request.client else None
    )
    return UsuarioOut.model_validate(usuario)


@router.get(
    "/me",
    response_model=UsuarioOut,
    summary="Consultar o próprio perfil",
)
def obter_me(autenticado: UsuarioDep) -> UsuarioOut:
    usuario = service.obter_proprio_perfil(autenticado.usuario)
    return UsuarioOut.model_validate(usuario)


@router.patch(
    "/me",
    response_model=UsuarioOut,
    summary="Editar o próprio perfil",
)
def editar_me(
    dados: EditarUsuarioRequest,
    autenticado: UsuarioDep,
    session: SessionDep,
    request: Request,
) -> UsuarioOut:
    usuario = service.editar_proprio_perfil(
        session,
        usuario=autenticado.usuario,
        condominio_id=autenticado.condominio_id,
        dados=dados,
        ip=request.client.host if request.client else None,
    )
    return UsuarioOut.model_validate(usuario)
