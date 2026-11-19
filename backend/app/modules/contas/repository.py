"""Contas são globais; a edição recebe exclusivamente o ID da identidade autenticada."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.usuarios.models import Usuario


def campo_em_uso(
    session: Session, campo: str, valor: str, *, exceto_usuario_id: uuid.UUID | None = None
) -> bool:
    coluna = {"email": Usuario.email, "telefone": Usuario.telefone, "documento": Usuario.documento}[
        campo
    ]
    consulta = select(Usuario.id).where(coluna == valor)
    if exceto_usuario_id is not None:
        consulta = consulta.where(Usuario.id != exceto_usuario_id)
    return session.scalar(consulta.limit(1)) is not None


def bloquear_conta(session: Session, usuario_id: uuid.UUID) -> Usuario:
    usuario = session.scalar(
        select(Usuario)
        .where(Usuario.id == usuario_id, Usuario.ativo.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None:
        raise ApiError(
            401,
            "not_authenticated",
            "Sessão inválida ou expirada. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def atualizar_conta(
    session: Session, usuario: Usuario, *, nome: str, email: str, telefone: str
) -> None:
    usuario.nome = nome
    usuario.email = email
    usuario.telefone = telefone
    session.flush()
