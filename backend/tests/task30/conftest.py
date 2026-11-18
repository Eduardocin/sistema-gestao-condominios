from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.tempo import get_relogio
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.unidades.models import ChaveAcesso
from app.modules.unidades.service import gerar_codigo
from tests.autorizacao.cenario import montar_predio
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de
from tests.test_contas_perfil_api import client as cliente_postgres
from tests.test_contas_perfil_api import session as sessao_postgres

client = cliente_postgres
session = sessao_postgres
ROTA = "/api/v1/vinculos/chave"


class RelogioTeste:
    def __init__(self):
        self.momento = datetime.now(UTC) + timedelta(minutes=1)

    def __call__(self):
        momento = self.momento
        self.momento += timedelta(seconds=1)
        return momento

    def avancar(self, **periodo):
        self.momento += timedelta(**periodo)


def morador(session):
    usuario = criar_usuario(session)
    usuario.tipo_cadastro = "morador"
    session.flush()
    return usuario


def chave(session, predio, unidade, *, momento=None):
    item = ChaveAcesso(
        condominio_id=predio.condominio.id,
        unidade_id=unidade.id,
        codigo=gerar_codigo(),
        criada_em=momento or datetime.now(UTC) - timedelta(days=1),
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture
def caso(session, client):
    a, b = montar_predio(session, "Prédio A"), montar_predio(session, "Prédio B")
    usuario = morador(session)
    relogio = RelogioTeste()
    chaves = [
        chave(session, a, a.unidade_102),
        chave(session, a, a.unidade_101),
        chave(session, b, b.unidade_102),
    ]
    responsavel = ResponsavelAdministracao(condominio_id=a.condominio.id, nome="Síndico A")
    session.add(responsavel)
    session.commit()
    client.app.dependency_overrides[get_relogio] = lambda: relogio
    return SimpleNamespace(
        a=a,
        b=b,
        usuario=usuario,
        relogio=relogio,
        chaves=chaves,
        headers=cabecalho(token_de(usuario, None)),
        responsavel=responsavel,
    )


def vincular(client, caso, *, chave_=None, headers=None, **campos):
    return client.post(
        ROTA,
        headers=headers or caso.headers,
        json={"chave": chave_ or caso.chaves[0].codigo, **campos},
    )
