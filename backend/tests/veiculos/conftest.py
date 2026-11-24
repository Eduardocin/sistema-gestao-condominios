from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from tests.autorizacao.cenario import Predio, montar_predio
from tests.autorizacao.conftest import session as session
from tests.reservas.cenario import definir_aba


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def predio(session: Session) -> Predio:
    predio = montar_predio(session)
    definir_aba(session, predio.morador_unidade, aba="veiculos")
    return predio


@pytest.fixture
def outro_predio(session: Session) -> Predio:
    """Um segundo condomínio completo, para os testes de isolamento."""
    predio = montar_predio(session, "Residencial Horizonte")
    definir_aba(session, predio.morador_unidade, aba="veiculos")
    return predio
