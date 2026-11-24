import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from tests.auditoria.conftest import cenario as cenario
from tests.us506.conftest import ROTAS

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("rota", ROTAS)
def test_negacoes_persistem_no_fluxo_central_sem_auditar_leituras(cenario, rota):
    # Cenário confirmado: o middleware grava a negação em outra sessão, após o 403.
    with TestClient(create_app()) as client:
        for perfil in ("morador", "funcionario"):
            resposta = client.get(rota, headers=cenario.a.cabecalho_de(perfil))
            assert resposta.status_code == 403
        assert client.get(rota, headers=cenario.a.cabecalho_de("administracao")).status_code == 200
    with cenario.fabrica() as session:
        eventos = list(
            session.scalars(
                select(RegistroAuditoria).where(
                    RegistroAuditoria.condominio_id == cenario.a.condominio.id
                )
            )
        )
    assert len(eventos) == 2
    assert {evento.perfil for evento in eventos} == {"morador", "funcionario"}
    assert all(evento.acao == "seguranca.acesso_negado" for evento in eventos)
