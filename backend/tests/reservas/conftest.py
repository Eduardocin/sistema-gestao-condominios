import os
from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.tempo import agora, get_relogio
from app.db.session import get_session
from app.main import create_app
from tests.autorizacao.cenario import Predio, montar_predio


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


class RelogioDeTeste:
    """Relógio trocável: sem `momento`, devolve a hora real (os testes da Fase 1 usam a real)."""

    def __init__(self) -> None:
        self.momento: datetime | None = None

    def __call__(self) -> datetime:
        return self.momento or agora()


@pytest.fixture
def relogio() -> RelogioDeTeste:
    return RelogioDeTeste()


@pytest.fixture
def client(session: Session, relogio: RelogioDeTeste) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_relogio] = lambda: relogio
    with TestClient(app) as client:
        yield client


@pytest.fixture
def predio(session: Session) -> Predio:
    return montar_predio(session)


@pytest.fixture
def outro_predio(session: Session) -> Predio:
    """Um segundo condomínio completo, para os testes de isolamento."""
    return montar_predio(session, "Residencial Horizonte")
