from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.tempo import FUSO_CONDOMINIO, get_relogio
from app.db.session import get_session
from app.main import create_app
from tests.autorizacao.cenario import Predio, montar_predio
from tests.autorizacao.conftest import session as session
from tests.reservas.cenario import definir_aba

# "Hoje" dos testes: 15/11/2026, ao meio-dia no fuso do condomínio.
AGORA = datetime(2026, 11, 15, 12, 0, tzinfo=FUSO_CONDOMINIO)


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_relogio] = lambda: lambda: AGORA
    with TestClient(app) as client:
        yield client


@pytest.fixture
def predio(session: Session) -> Predio:
    predio = montar_predio(session)
    definir_aba(session, predio.morador_unidade, aba="visitantes")
    return predio


@pytest.fixture
def outro_predio(session: Session) -> Predio:
    """Um segundo condomínio completo, para os testes de isolamento."""
    predio = montar_predio(session, "Residencial Horizonte")
    definir_aba(session, predio.morador_unidade, aba="visitantes")
    return predio
