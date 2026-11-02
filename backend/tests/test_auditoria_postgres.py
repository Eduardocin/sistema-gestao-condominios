import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.auditoria.models import EventoAuditoria, TipoEventoAuditoria
from app.modules.auditoria.service import log

pytestmark = pytest.mark.postgres


@pytest.fixture
def session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        pytest.fail("Estes testes exigem PostgreSQL real")
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


def test_postgres_rejeita_update_e_delete_dos_eventos(session):
    evento = log(
        session,
        tipo_evento=TipoEventoAuditoria.LOGIN,
        recurso="sessao",
        ator="Ana Martins",
    )

    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(
            update(EventoAuditoria)
            .where(EventoAuditoria.id == evento.id)
            .values(ator="Outro responsável")
        )

    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(delete(EventoAuditoria).where(EventoAuditoria.id == evento.id))

    assert (
        session.scalar(select(EventoAuditoria.id).where(EventoAuditoria.id == evento.id))
        == evento.id
    )

    with pytest.raises(DBAPIError), session.begin_nested():
        session.execute(text("TRUNCATE TABLE eventos_auditoria"))

    assert (
        session.scalar(select(EventoAuditoria.id).where(EventoAuditoria.id == evento.id))
        == evento.id
    )


def test_postgres_impede_perfil_compartilhado_sem_responsavel(session):
    with pytest.raises(DBAPIError), session.begin_nested():
        session.add(
            EventoAuditoria(
                tipo_evento=TipoEventoAuditoria.RESERVA.value,
                recurso="reserva",
                perfil="funcionario",
                conta_compartilhada=False,
                nome_responsavel=None,
            )
        )
        session.flush()


def test_postgres_define_data_do_evento_automaticamente(session):
    data_informada = datetime(2000, 1, 1, tzinfo=UTC)
    evento = EventoAuditoria(
        tipo_evento=TipoEventoAuditoria.LOGIN.value,
        recurso="sessao",
        criado_em=data_informada,
    )
    session.add(evento)
    session.flush()
    session.refresh(evento)

    assert evento.criado_em is not None
    assert evento.criado_em.year > 2000
