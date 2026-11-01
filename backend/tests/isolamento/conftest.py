import os
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_session
from tests.isolamento import app_exemplo
from tests.isolamento.cenario import Lado, criar_lado, montar_app


@pytest.fixture
def session() -> Generator[Session]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        # A tabela de teste nasce dentro da transação (DDL do PostgreSQL é transacional) e
        # some no rollback do fim: nada de migration nem de sujeira no banco.
        app_exemplo.BaseTeste.metadata.tables["itens_teste"].create(connection)
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def app(session: Session) -> FastAPI:
    app = montar_app()
    app.dependency_overrides[get_session] = lambda: session
    return app


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def a(session: Session) -> Lado:
    return criar_lado(session, "Condomínio A")


@pytest.fixture
def b(session: Session) -> Lado:
    return criar_lado(session, "Condomínio B")
