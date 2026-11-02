import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auditoria.models import EventoAuditoria


def criar(session: Session, evento: EventoAuditoria) -> EventoAuditoria:
    session.add(evento)
    session.flush()
    return evento


def obter_por_id(session: Session, evento_id: uuid.UUID) -> EventoAuditoria | None:
    return session.get(EventoAuditoria, evento_id)


def listar(
    session: Session,
    *,
    usuario_id: uuid.UUID | None = None,
    condominio_id: uuid.UUID | None = None,
    antes_de: datetime | None = None,
    limite: int = 100,
) -> list[EventoAuditoria]:
    if not 1 <= limite <= 500:
        raise ValueError("limite deve estar entre 1 e 500")

    consulta = select(EventoAuditoria)
    if usuario_id is not None:
        consulta = consulta.where(EventoAuditoria.usuario_id == usuario_id)
    if condominio_id is not None:
        consulta = consulta.where(EventoAuditoria.condominio_id == condominio_id)
    if antes_de is not None:
        consulta = consulta.where(EventoAuditoria.criado_em < antes_de)
    consulta = consulta.order_by(EventoAuditoria.criado_em.desc(), EventoAuditoria.id.desc())
    return list(session.scalars(consulta.limit(limite)))
