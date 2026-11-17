"""US-1004: um mecanismo de auditoria para todos os módulos.

Ações de negócio usam a transação do chamador. Segurança usa uma sessão independente e
nunca substitui o erro HTTP original por uma falha de infraestrutura da trilha.
"""

import ipaddress
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ApiError, RecursoNaoEncontrado
from app.db import session as banco
from app.modules.auditoria import repository
from app.modules.auditoria.sanitizacao import sanitizar
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef

logger = logging.getLogger(__name__)


def ip_valido(ip: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def _dados(
    ctx: ContextoAuditoria,
    acao: str,
    recurso_tipo: str | None,
    recurso_id: uuid.UUID | None,
    antes: Mapping[str, Any] | None,
    depois: Mapping[str, Any] | None,
    responsavel_nome: str | None = None,
) -> dict[str, Any]:
    if len(acao) > 60 or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", acao) is None:
        raise ValueError("A ação de auditoria deve seguir grupo.verbo e ter até 60 caracteres.")
    if recurso_tipo is not None and len(recurso_tipo) > 60:
        raise ValueError("Tipo de recurso de auditoria muito longo.")
    if ctx.perfil not in {None, "morador", "administracao", "funcionario", "plataforma"}:
        raise ValueError("Perfil de auditoria inválido.")
    return {
        "usuario_id": ctx.usuario_id,
        "condominio_id": ctx.condominio_id,
        "perfil": ctx.perfil,
        "acao": acao,
        "recurso_tipo": recurso_tipo,
        "recurso_id": recurso_id,
        "responsavel_nome": responsavel_nome,
        "ip": ip_valido(ctx.ip),
        "antes": sanitizar(antes),
        "depois": sanitizar(depois),
    }


def registrar_acao(
    session: Session,
    *,
    ctx: ContextoAuditoria,
    acao: str,
    recurso_tipo: str,
    recurso_id: uuid.UUID | None,
    responsavel: ResponsavelRef | None = None,
    antes: Mapping[str, Any] | None = None,
    depois: Mapping[str, Any] | None = None,
) -> None:
    """Insere e faz flush, sem commit; falhas revertem a operação principal.

    Gerir a própria lista de responsáveis é a exceção explícita da seção 5.2 do contrato.
    Login identifica a conta, antes de haver seleção de pessoa numa conta compartilhada.
    """
    if ctx.usuario_id is None:
        raise ValueError("Uma ação de negócio exige uma conta autenticada.")
    nome = None
    exige_responsavel = ctx.perfil in {"administracao", "funcionario"} and (
        acao not in {"responsaveis.alterar", "seguranca.login"}
    )
    if responsavel is None and exige_responsavel:
        raise ApiError(422, "validation_error", "Informe o responsável pela ação.")
    if responsavel is not None:
        if ctx.condominio_id is None or responsavel.tipo != ctx.perfil:
            raise RecursoNaoEncontrado
        nome = repository.nome_do_responsavel(session, ctx.condominio_id, responsavel)
    repository.inserir(session, _dados(ctx, acao, recurso_tipo, recurso_id, antes, depois, nome))


def registrar_evento_seguranca(
    *,
    acao: str,
    usuario_id: uuid.UUID | None,
    condominio_id: uuid.UUID | None,
    ip: str | None,
    perfil: str | None = None,
    recurso_tipo: str | None = None,
    recurso_id: uuid.UUID | None = None,
    detalhe: Mapping[str, Any] | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Transação própria. Não registra payloads, tokens nem detalhes de exceções no log de falha."""
    try:
        fabrica = session_factory or banco.get_session_factory()
        with fabrica() as session:
            try:
                repository.limitar_espera_seguranca(session)
                usuario, condominio = repository.referencias_visiveis(
                    session, usuario_id, condominio_id
                )
                ctx = ContextoAuditoria(usuario, condominio, perfil, ip)
                repository.inserir(
                    session, _dados(ctx, acao, recurso_tipo, recurso_id, None, detalhe)
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
    except Exception:
        # Exceções de driver/SQL podem carregar parâmetros sensíveis. Não usar exc_info/repr.
        logger.error("Falha ao persistir evento de segurança na auditoria.")
