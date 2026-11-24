import uuid
from types import SimpleNamespace

import pytest

from app.modules.funcionarios.models import ResponsavelAdministracao
from tests.isolamento.cenario import cabecalho, criar_condominio, criar_usuario, token_de, vincular
from tests.test_contas_perfil_api import client as client
from tests.test_contas_perfil_api import session as session

CONTA = "/api/v1/conta-funcionarios"
RESPONSAVEIS = "/api/v1/responsaveis-administracao"
SENHA = "SenhaPortaria210"
ACAO = "conta_compartilhada.trocar_acesso"


def predio(session, nome):
    condominio = criar_condominio(session, nome)
    administracao = criar_usuario(session)
    vincular(session, administracao, condominio, perfil="administracao")
    responsavel = ResponsavelAdministracao(condominio_id=condominio.id, nome="Síndica Original")
    session.add(responsavel)
    session.flush()
    return SimpleNamespace(
        condominio=condominio,
        administracao=administracao,
        responsavel=responsavel,
        headers=cabecalho(token_de(administracao, condominio.id, perfil="administracao")),
    )


@pytest.fixture
def caso(session):
    caso = SimpleNamespace(a=predio(session, "US-210 A"), b=predio(session, "US-210 B"))
    # Confirma o savepoint da preparação; 4xx fazem rollback da transação da requisição.
    # A transação externa da fixture continua garantindo a limpeza ao terminar o teste.
    session.commit()
    return caso


def dados(caso, *, lado="a", **campos):
    p = getattr(caso, lado)
    return {
        "login": f"portaria-{p.condominio.id.hex}@example.test",
        "senha": SENHA,
        "responsavel_id": str(p.responsavel.id),
        **campos,
    }


def email_novo():
    return f"{uuid.uuid4().hex}@example.test"
