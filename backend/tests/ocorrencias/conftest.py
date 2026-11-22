import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from tests.autorizacao.cenario import Predio, montar_predio
from tests.reservas.cenario import definir_aba


@pytest.fixture
def session() -> Generator[Session]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()  # desfaz tudo que o teste gravou
    engine.dispose()


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def predio(session: Session) -> Predio:
    predio = montar_predio(session)
    definir_aba(session, predio.morador_unidade, aba="ocorrencias")
    return predio


@pytest.fixture
def outro_predio(session: Session) -> Predio:
    """Um segundo condomínio completo, para os testes de isolamento."""
    predio = montar_predio(session, "Residencial Horizonte")
    definir_aba(session, predio.morador_unidade, aba="ocorrencias")
    return predio
