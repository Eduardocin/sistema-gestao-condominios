import logging
import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core import permissoes
from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.db.session import get_session
from app.modules.auth import repository
from app.modules.auth.dependencies import (
    ContextoDep,
    UsuarioAutenticado,
    get_usuario_autenticado,
)
from app.modules.unidades.models import ABAS_MORADOR

# Mensagem única de 403: não diz qual recurso, perfil, aba ou regra barrou (matriz, seção 6).
MENSAGEM_SEM_PERMISSAO = "Você não tem permissão para realizar esta ação."

logger = logging.getLogger("seguranca")


def registrar_negacao(
    *,
    usuario_id: uuid.UUID,
    condominio_id: uuid.UUID | None,
    perfil: str | None,
    permissao: str,
) -> None:
    """Deixa registrado que alguém foi barrado (evento de segurança da matriz, seção 10).

    Por enquanto vai para o log. Quando a trilha de auditoria (TASK-24) existir, é só trocar o
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
    """Dependência de rota de condomínio: exige que o perfil possa a ação ("recurso:acao").

    Uso (a checagem roda antes do corpo da rota e antes de validar o corpo da requisição):

        @router.post("", dependencies=[Depends(require_permission("encomendas:criar"))])

    ou, se a rota precisar do contexto:

        contexto: Annotated[ContextoCondominio, Depends(require_permission("encomendas:ver"))]
    """
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
    """Passo 4 (R10): a unidade que veio na requisição pode ser usada por quem está pedindo?

    Chame no service sempre que uma rota receber `unidade_id` (na URL, na query ou no corpo).

    - Morador: só as unidades em que ele mora (`moradores_unidade`, vínculo ativo).
    - Funcionário e Administração: qualquer unidade, desde que seja do condomínio do contexto.

    Se não puder, responde 404 igual a "não existe" (R4), sem confirmar que a unidade existe.
    """
    if contexto.perfil == permissoes.Perfil.MORADOR:
        permitidas = repository.listar_unidades_do_morador(
            session, usuario_id=contexto.usuario_id, condominio_id=contexto.condominio_id
        )
        if unidade_id not in permitidas:
            raise RecursoNaoEncontrado
        return

    if repository.obter_unidade(session, unidade_id, contexto.condominio_id) is None:
        raise RecursoNaoEncontrado


def require_aba(aba: str) -> Callable[..., ContextoCondominio]:
    """Passo 4 completo: a unidade é de quem pede e, se for Morador, ele está Com Acesso à aba.

    Uso, junto com `require_permission` (que decide o perfil). A URL da rota PRECISA ter
    `{unidade_id}`, porque a aba é por unidade (um morador pode estar Com Acesso na 101 e Sem
    Acesso na 102):

        @router.post(
            "/unidades/{unidade_id}/visitantes",
            dependencies=[
                Depends(require_permission("visitantes:criar")),  # passo 3: perfil
                Depends(require_aba("visitantes")),                # passo 4: unidade + aba
            ],
        )

    Quem não é Morador (Funcionário, Administração) não tem permissão por aba (matriz, seção 8):
    para eles esta dependência só confere se a unidade é do condomínio. Por isso ela não
    substitui `require_permission`: sem ele, um Funcionário passaria em qualquer rota.
    """
    # Falha ao declarar a rota, não ao primeiro cliente: "visitante" (sem s) derruba o import.
    if aba not in ABAS_MORADOR:
        raise ValueError(f"Aba inválida: {aba!r}. Use uma de {list(ABAS_MORADOR)}.")

    def verificar(
        contexto: ContextoDep,
        unidade_id: uuid.UUID,
        session: Annotated[Session, Depends(get_session)],
    ) -> ContextoCondominio:
        # 4a) A unidade é dele? Se não, 404 (igual a "não existe"), e a aba nem é consultada.
        garantir_acesso_a_unidade(session, contexto, unidade_id)

        # 4b) Só o Morador tem aba. Lemos do banco a cada requisição (R6): mudar a permissão
        # vale na requisição seguinte, mesmo com o mesmo token.
        if contexto.perfil == permissoes.Perfil.MORADOR and not repository.morador_tem_acesso_a_aba(
            session,
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
            unidade_id=unidade_id,
            aba=aba,
        ):
            registrar_negacao(
                usuario_id=contexto.usuario_id,
                condominio_id=contexto.condominio_id,
                perfil=contexto.perfil,
                permissao=f"aba:{aba}",
            )
            raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
        return contexto

    return verificar
