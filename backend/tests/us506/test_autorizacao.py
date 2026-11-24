import uuid

import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import VinculoCondominio
from tests.us506.conftest import ROTAS, consultar, veiculo, visita

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("perfil", ["administracao", "morador", "funcionario", "plataforma"])
def test_perfil_exclusivo_administracao(client, caso, rota, perfil):
    resposta = client.get(rota, headers=caso.a.cabecalho_de(perfil))
    assert resposta.status_code == (200 if perfil == "administracao" else 403), resposta.text


@pytest.mark.parametrize("rota", ROTAS)
def test_sem_autenticacao(client, rota):
    resposta = client.get(rota)
    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("estado", ["pendente", "rejeitado", "desativado"])
def test_condominio_nao_ativo(client, session, caso, rota, estado):
    caso.a.condominio.status = estado
    caso.a.condominio.motivo_rejeicao = "Cadastro incompleto" if estado == "rejeitado" else None
    session.flush()
    assert client.get(rota, headers=caso.a.cabecalho_de("administracao")).status_code == 403


@pytest.mark.parametrize("rota", ROTAS)
def test_vinculo_revogado(client, session, caso, rota):
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == caso.a.administracao.id,
            VinculoCondominio.condominio_id == caso.a.condominio.id,
        )
    )
    vinculo.ativo = False
    session.flush()
    assert client.get(rota, headers=caso.a.cabecalho_de("administracao")).status_code == 403


@pytest.mark.parametrize("rota", ROTAS)
def test_isolamento_e_identificador_do_cliente(client, session, caso, rota):
    visita_a, _ = visita(session, caso)
    visita_b, visitante_b = visita(session, caso, predio=caso.b)
    carro_a = veiculo(session, caso)
    carro_b = veiculo(session, caso, predio=caso.b)
    esperado = visita_a if rota.endswith("visitantes") else carro_a
    resposta = consultar(client, caso, rota)
    assert resposta["total"] == 1
    assert resposta["items"][0]["id"] == str(esperado.id)
    assert all(
        str(id_) not in str(resposta)
        for id_ in (visita_b.id, visitante_b.id, carro_b.id, caso.b.unidade_101.id, caso.externo.id)
    )
    outro = client.get(rota, headers=caso.b.cabecalho_de("administracao"))
    assert outro.status_code == 200 and outro.json()["total"] == 1
    assert outro.json()["items"][0]["id"] != str(esperado.id)
    # A query é estrita; cabeçalhos livres não substituem o condomínio autenticado.
    assert (
        client.get(
            rota,
            headers=caso.a.cabecalho_de("administracao"),
            params={"condominio_id": str(caso.b.condominio.id)},
        ).status_code
        == 422
    )
    forjado = client.get(
        rota,
        headers={
            **caso.a.cabecalho_de("administracao"),
            "X-Condominio-Id": str(caso.b.condominio.id),
        },
    )
    assert forjado.status_code == 200 and forjado.json() == resposta


@pytest.mark.parametrize("rota", ROTAS)
def test_unidade_alheia_e_inexistente_tem_mesmo_404(client, caso, rota):
    respostas = [
        client.get(
            rota,
            headers=caso.a.cabecalho_de("administracao"),
            params={"unidade_id": str(id_)},
        )
        for id_ in (uuid.uuid4(), caso.b.unidade_101.id)
    ]
    assert [r.status_code for r in respostas] == [404, 404]
    assert respostas[0].json() == respostas[1].json()


def test_leituras_nao_criam_evento_de_sucesso(client, session, caso):
    anterior = session.scalar(select(func.count()).select_from(RegistroAuditoria))
    for rota in ROTAS:
        consultar(client, caso, rota)
    assert session.scalar(select(func.count()).select_from(RegistroAuditoria)) == anterior
