import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.tempo import get_relogio
from app.db.session import get_session
from app.main import create_app
from tests.autorizacao.cenario import Predio, montar_predio
from tests.reservas.cenario import AGORA, definir_aba
from tests.reservas.conftest import RelogioDeTeste


@pytest.fixture
def session() -> Generator[Session]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    assert engine.dialect.name == "postgresql"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def relogio() -> RelogioDeTeste:
    relogio = RelogioDeTeste()
    relogio.momento = AGORA
    return relogio


@pytest.fixture
def client(session: Session, relogio: RelogioDeTeste) -> Generator[TestClient]:
    def sessao_da_requisicao() -> Generator[Session]:
        try:
            yield session
        except Exception:
            session.rollback()
            raise

    app = create_app()
    app.dependency_overrides[get_session] = sessao_da_requisicao
    app.dependency_overrides[get_relogio] = lambda: relogio
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def predio(session: Session) -> Predio:
    predio = montar_predio(session)
    definir_aba(session, predio.morador_unidade)
    return predio


@pytest.fixture
def outro_predio(session: Session) -> Predio:
    return montar_predio(session, "Outro condomínio")
