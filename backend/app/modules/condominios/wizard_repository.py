import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import RascunhoCondominio
from app.modules.usuarios.models import Usuario


def obter_rascunho(
    session: Session, *, rascunho_id: uuid.UUID, token_hash: str
) -> RascunhoCondominio | None:
    return session.scalar(
        select(RascunhoCondominio).where(
            RascunhoCondominio.id == rascunho_id,
            RascunhoCondominio.token_hash == token_hash,
        )
    )


def obter_email_ou_cpf(session: Session, *, email: str, cpf: str) -> Usuario | None:
    return session.scalar(select(Usuario).where((Usuario.email == email) | (Usuario.cpf == cpf)))
