from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.tempo import FUSO_CONDOMINIO
from tests.us506.conftest import MOMENTO, ROTAS, consultar, veiculo, visita

pytestmark = pytest.mark.postgres


def criar(session, caso, rota, momento, numero=0, unidade=None):
    if rota == ROTAS[0]:
        return visita(session, caso, entrada=momento, unidade=unidade)[0]
    return veiculo(session, caso, criado=momento, placa=f"TST1A{numero:02}", unidade=unidade)


@pytest.mark.parametrize("rota", ROTAS)
def test_limites_inclusivos_entrada_ou_cadastro_no_fuso(client, session, caso, rota):
    inicio = datetime(2030, 4, 2, 3, tzinfo=UTC)  # Meia-noite em São Paulo.
    fim = inicio + timedelta(days=2)
    momentos = (
        inicio - timedelta(microseconds=1),
        inicio,
        inicio + timedelta(days=1),
        fim - timedelta(microseconds=1),
        fim,
    )
    registros = [criar(session, caso, rota, momento, i) for i, momento in enumerate(momentos)]
    pagina = consultar(client, caso, rota, de="2030-04-02", ate="2030-04-03")
    assert pagina["total"] == 3
    assert {item["id"] for item in pagina["items"]} == {str(item.id) for item in registros[1:4]}
    assert consultar(client, caso, rota, de="2030-04-02")["total"] == 4
    assert consultar(client, caso, rota, ate="2030-04-03")["total"] == 4
    assert consultar(client, caso, rota, de="2030-04-02", ate="2030-04-02")["total"] == 1


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("dia", ["2018-11-04", "2019-02-16"])
def test_dias_com_transicao_de_horario_verao(client, session, caso, rota, dia):
    data = datetime.fromisoformat(dia).date()
    inicio = datetime.combine(data, datetime.min.time(), FUSO_CONDOMINIO).astimezone(UTC)
    fim = datetime.combine(
        data + timedelta(days=1), datetime.min.time(), FUSO_CONDOMINIO
    ).astimezone(UTC)
    assert (fim - inicio).total_seconds() in (23 * 3600, 25 * 3600)
    for i, momento in enumerate(
        (inicio - timedelta(microseconds=1), inicio, fim - timedelta(microseconds=1), fim)
    ):
        criar(session, caso, rota, momento, i)
    assert consultar(client, caso, rota, de=dia, ate=dia)["total"] == 2


@pytest.mark.parametrize("rota", ROTAS)
def test_filtros_combinados_total_e_paginacao_estavel(client, session, caso, rota):
    itens = [criar(session, caso, rota, MOMENTO, i) for i in range(3)]
    # IDs deliberadamente fora da ordem de inserção para provar o desempate.
    for item, valor in zip(itens, (30, 10, 20), strict=True):
        item.id = UUID(int=valor)
    criar(session, caso, rota, MOMENTO, 3, caso.a.unidade_102)
    criar(session, caso, rota, MOMENTO - timedelta(days=1), 4)
    session.flush()
    params = {
        "unidade_id": str(caso.a.unidade_101.id),
        "de": "2030-04-02",
        "ate": "2030-04-02",
        "page_size": 2,
    }
    primeira = consultar(client, caso, rota, **params)
    segunda = consultar(client, caso, rota, **params, page=2)
    assert primeira["total"] == segunda["total"] == 3
    assert (primeira["page"], primeira["page_size"], segunda["page"]) == (1, 2, 2)
    ids = [item["id"] for item in primeira["items"] + segunda["items"]]
    assert ids == [str(UUID(int=valor)) for valor in (10, 20, 30)]
    assert consultar(client, caso, rota, **params) == primeira
    vazia = consultar(client, caso, rota, **params, page=3)
    assert vazia["items"] == [] and vazia["total"] == 3
    padrao = consultar(client, caso, rota)
    assert padrao["total"] == 5 and padrao["page_size"] == 20
    assert padrao["items"][-1]["id"] not in ids  # Data mais antiga por último.
    assert consultar(client, caso, rota, de="2031-01-01")["total"] == 0


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize(
    "params",
    [
        {"de": "2030-04-03", "ate": "2030-04-02"},
        {"de": "2030-02-30"},
        {"ate": "não é data"},
        {"ate": "9999-12-31"},
        {"de": "9999-12-31"},
        {"unidade_id": "inválido"},
        {"page": 0},
        {"page_size": 0},
        {"page_size": 101},
        {"page": "1.5"},
    ],
)
def test_parametros_invalidos(client, caso, rota, params):
    resposta = client.get(rota, headers=caso.a.cabecalho_de("administracao"), params=params)
    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("rota", ROTAS)
def test_datas_extremas_validas_e_resultado_vazio(client, session, caso, rota):
    criar(session, caso, rota, MOMENTO)
    assert consultar(client, caso, rota, de="0001-01-01", ate="9999-12-30")["total"] == 1
    assert consultar(client, caso, rota, ate="0001-01-01")["items"] == []
    assert consultar(client, caso, rota, de="9999-12-30")["items"] == []


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("page_size", [1, 100])
def test_offset_no_limite_bigint_e_overflow_rejeitado(client, caso, rota, page_size):
    ultima_pagina = (2**63 - 1) // page_size + 1
    pagina = consultar(client, caso, rota, page=ultima_pagina, page_size=page_size)
    assert pagina["items"] == [] and pagina["total"] == 0
    resposta = client.get(
        rota,
        headers=caso.a.cabecalho_de("administracao"),
        params={"page": ultima_pagina + 1, "page_size": page_size},
    )
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"
