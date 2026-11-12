"""Contexto exclusivo da lista de responsáveis: também atende o fluxo de cadastro (R7)."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.db.session import get_session
from app.modules.auth import repository
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, registrar_negacao
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado


def contexto_responsaveis(
    autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
    session: Annotated[Session, Depends(get_session)],
) -> ContextoCondominio:
    if autenticado.condominio_id is None or autenticado.usuario.administrador_plataforma:
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    linha = repository.obter_vinculo_ativo(
        session, autenticado.usuario.id, autenticado.condominio_id
    )
    if linha is None:
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    vinculo, condominio = linha
    if vinculo.perfil != "administracao" or condominio.status == "desativado":
        registrar_negacao(
            usuario_id=autenticado.usuario.id,
            condominio_id=condominio.id,
            perfil=vinculo.perfil,
            permissao="responsaveis:gerir",
        )
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    return ContextoCondominio(
        usuario_id=autenticado.usuario.id,
        condominio_id=condominio.id,
        perfil=vinculo.perfil,
        vinculo_id=vinculo.id,
    )
