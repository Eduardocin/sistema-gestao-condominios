"""Persistência da trilha: somente inserção, sem commit e sem métodos de alteração/exclusão."""

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import RecursoNaoEncontrado
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auditoria.schemas import ResponsavelRef
from app.modules.condominios.models import Condominio
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.usuarios.models import Usuario


def inserir(session: Session, dados: dict[str, Any]) -> None:
    session.add(RegistroAuditoria(**dados))
    session.flush()


def nome_do_responsavel(
    session: Session, condominio_id: uuid.UUID, responsavel: ResponsavelRef
) -> str:
    modelo = ResponsavelAdministracao if responsavel.tipo == "administracao" else Funcionario
    pessoa = session.scalar(
        select(modelo)
        .where(
            modelo.id == responsavel.id,
            modelo.condominio_id == condominio_id,
            modelo.ativo.is_(True),
        )
        .with_for_update(read=True)
    )
    if not isinstance(pessoa, (ResponsavelAdministracao, Funcionario)):
        raise RecursoNaoEncontrado
    return pessoa.nome


def referencias_visiveis(
    session: Session, usuario_id: uuid.UUID | None, condominio_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Segurança não espera FKs de uma transação que ainda pode sofrer rollback.

    IDs inexistentes ou ainda não confirmados não viram referências inválidas. Isso também
    permite registrar a tentativa de login de uma conta inexistente.
    """
    usuario = (
        session.scalar(select(Usuario.id).where(Usuario.id == usuario_id)) if usuario_id else None
    )
    condominio = (
        session.scalar(select(Condominio.id).where(Condominio.id == condominio_id))
        if condominio_id
        else None
    )
    return usuario, condominio


def limitar_espera_seguranca(session: Session) -> None:
    """Uma tentativa de auditar não espera indefinidamente por locks da requisição original."""
    session.execute(text("SET LOCAL lock_timeout = '500ms'"))
    session.execute(text("SET LOCAL statement_timeout = '2s'"))
