import logging
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core import permissoes
from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auth import repository
from app.modules.auth.dependencies import (
    ContextoDep,
    UsuarioAutenticado,
    get_usuario_autenticado,
)

# Mensagem única de 403: não diz qual recurso, perfil ou regra barrou
MENSAGEM_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."

logger = logging.getLogger("seguranca")


def registrar_negacao(
    *,
    usuario_id: uuid.UUID,
    condominio_id: uuid.UUID | None,
    perfil: str | None,
    permissao: str,
) -> None:
    """Deixa registrado que alguém foi barrado
    Por enquanto vai para o log. Quando a trilha de auditoria existir, é só trocar o
    corpo desta função para gravar lá: nenhuma rota precisa mudar. Só entram IDs, nunca token,
    senha ou dados pessoais.
    """
    logger.warning(
        "seguranca.acesso_negado usuario=%s condominio=%s perfil=%s permissao=%s",
        usuario_id,
        condominio_id,
        perfil,
        permissao,
    )


def require_permission(permissao: str) -> Callable[[ContextoCondominio], ContextoCondominio]:
    # Conferimos o nome agora, na hora de declarar a rota: erro de digitação derruba o import.
    recurso, acao = permissoes.interpretar(permissao)

    def verificar(contexto: ContextoDep) -> ContextoCondominio:
        # `ContextoDep` já cuidou de identidade (401) e condomínio (403). Falta o perfil.
        if not permissoes.pode(contexto.perfil, recurso, acao):
            registrar_negacao(
                usuario_id=contexto.usuario_id,
                condominio_id=contexto.condominio_id,
                perfil=contexto.perfil,
                permissao=permissao,
            )
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        return contexto

    return verificar


def require_platform_permission(
    permissao: str,
) -> Callable[[UsuarioAutenticado], ContextoPlataforma]:
    """Como `require_permission`, mas para as rotas `/plataforma/...` do ADM (R8 e R9).

    O ADM não tem condomínio nem vínculo: basta estar autenticado, ser
    `administrador_plataforma` e a matriz liberar a ação para a coluna "ADM".
    """
    recurso, acao = permissoes.interpretar(permissao)

    def verificar(
        autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
    ) -> ContextoPlataforma:
        usuario = autenticado.usuario
        if not usuario.administrador_plataforma or not permissoes.pode(
            permissoes.Perfil.PLATAFORMA, recurso, acao
        ):
            registrar_negacao(
                usuario_id=usuario.id,
                condominio_id=autenticado.condominio_id,
                perfil=permissoes.Perfil.PLATAFORMA if usuario.administrador_plataforma else None,
                permissao=permissao,
            )
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        return ContextoPlataforma(usuario_id=usuario.id)

    return verificar


def garantir_acesso_a_unidade(
    session: Session, contexto: ContextoCondominio, unidade_id: uuid.UUID
) -> None:
    """a unidade que veio na requisição pode ser usada por quem está pedindo?
    Chame no service sempre que uma rota receber `unidade_id` (na URL, na query ou no corpo)
    - Morador: só as unidades ligadas ao vínculo dele
    - Funcionário e Administração: qualquer unidade, desde que seja do condomínio do contexto
    Se não puder, responde 404 igual a "não existe" (R4), sem confirmar que a unidade existe
    """
    if contexto.perfil == permissoes.Perfil.MORADOR:
        permitidas = repository.listar_unidades_do_vinculo(
            session,
            vinculo_id=contexto.vinculo_id,
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
        )
        if unidade_id not in permitidas:
            raise RecursoNaoEncontrado
        return

    if repository.obter_unidade(session, unidade_id, contexto.condominio_id) is None:
        raise RecursoNaoEncontrado
