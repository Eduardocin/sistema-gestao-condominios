from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.db.session import get_session
from app.modules.auditoria.contexto import identificar_contexto
from app.modules.auth import repository
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.condominios.models import Condominio


def condominio_do_cadastro(
    autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
    session: Annotated[Session, Depends(get_session)],
) -> Condominio:
    # Exceção R7 apenas para esta leitura. Não relaxa o contexto operacional.
    if autenticado.condominio_id is None or autenticado.usuario.administrador_plataforma:
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    linha = repository.obter_vinculo_ativo(
        session, autenticado.usuario.id, autenticado.condominio_id
    )
    if linha is None or linha[0].perfil != "administracao":
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    vinculo, condominio = linha
    identificar_contexto(
        ContextoCondominio(
            usuario_id=autenticado.usuario.id,
            condominio_id=condominio.id,
            perfil=vinculo.perfil,
            vinculo_id=vinculo.id,
        )
    )
    return condominio
