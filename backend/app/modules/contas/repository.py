"""Contas são globais; não recebem contexto de condomínio."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.usuarios.models import Usuario


def campo_em_uso(session: Session, campo: str, valor: str) -> bool:
    coluna = {"email": Usuario.email, "telefone": Usuario.telefone, "documento": Usuario.documento}[
        campo
    ]
    return session.scalar(select(Usuario.id).where(coluna == valor).limit(1)) is not None
