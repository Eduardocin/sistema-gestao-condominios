"""Regras de cadastro, consulta, edição e remoção dos veículos (US-502)."""

import uuid

import pytest

from app.core.permissoes import Perfil
from app.modules.visitantes.models import Veiculo
from tests.veiculos.cenario import corpo, criar_veiculo

URL = "/api/v1/veiculos"


@pytest.fixture
def morador(predio):
    return predio.cabecalho_de(Perfil.MORADOR)


# --- cadastro ---------------------------------------------------------------------------------


def test_criar_devolve_o_veiculo(client, session, predio, morador):
    resposta = client.post(URL, headers=morador, json=corpo(predio))
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert resposta.headers["Location"] == f"{URL}/{dados['id']}"
    assert dados["unidade"] == {
        "id": str(predio.unidade_101.id),
        "nome": predio.unidade_101.identificacao,
    }
    assert (dados["placa"], dados["marca"], dados["modelo"], dados["cor"]) == (
        "ABC1D23",
        "Fiat",
        "Argo",
        "Prata",
    )
    assert dados["ativo"] is True
    gravado = session.get(Veiculo, uuid.UUID(dados["id"]))
    assert gravado.condominio_id == predio.condominio.id
    assert gravado.removido_em is None


@pytest.mark.parametrize(
    ("enviada", "gravada"),
    [
        ("abc1d23", "ABC1D23"),  # minúsculas
        ("ABC-1234", "ABC1234"),  # hífen
        (" abc 1d23 ", "ABC1D23"),  # espaços
        ("AbC-1D-23", "ABC1D23"),
    ],
)
def test_placa_e_normalizada(client, predio, morador, enviada, gravada):
    resposta = client.post(URL, headers=morador, json=corpo(predio, placa=enviada))
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["placa"] == gravada


@pytest.mark.parametrize(
    "placa",
    ["", "ABC123", "ABCD123", "AB1D234", "ABC12345", "123ABCD", "ABC1D2", "ÁBC1D23", "ABC*D23"],
)
def test_placa_fora_do_formato_e_422(client, predio, morador, placa):
    resposta = client.post(URL, headers=morador, json=corpo(predio, placa=placa))
    assert resposta.status_code == 422, resposta.text


@pytest.mark.parametrize(
    "campos",
    [
        {"marca": ""},
        {"marca": "   "},
        {"modelo": "x" * 41},
        {"cor": ""},
        {"ativo": False},
        {"removido_em": "2026-11-15T10:00:00Z"},
    ],
)
def test_entrada_invalida_e_422(client, predio, morador, campos):
    resposta = client.post(URL, headers=morador, json=corpo(predio, **campos))
    assert resposta.status_code == 422, resposta.text


def test_campos_obrigatorios(client, predio, morador):
    for campo in ("unidade_id", "placa", "marca", "modelo", "cor"):
        dados = corpo(predio)
        del dados[campo]
        assert client.post(URL, headers=morador, json=dados).status_code == 422, campo


def test_textos_com_40_caracteres_valem(client, predio, morador):
    dados = corpo(predio, marca="m" * 40, modelo="o" * 40, cor="c" * 40)
    assert client.post(URL, headers=morador, json=dados).status_code == 201


def test_placa_repetida_na_mesma_unidade_e_409(client, session, predio, morador):
    criar_veiculo(session, predio, placa="ABC1D23")
    resposta = client.post(URL, headers=morador, json=corpo(predio, placa="abc-1d23"))
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "placa_ja_cadastrada_na_unidade"
    # Nada foi gravado e a sessão continua utilizável depois do conflito.
    lista = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador)
    assert lista.json()["total"] == 1


def test_placa_repetida_em_outra_unidade_e_aceita_sem_revelar(client, session, predio, morador):
    """Regra 14: o cadastro vale, e o Morador não fica sabendo que a placa existe noutra unidade."""
    outra = criar_veiculo(session, predio, unidade=predio.unidade_102, placa="ABC1D23")
    resposta = client.post(URL, headers=morador, json=corpo(predio, placa="ABC1D23"))
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert str(outra.id) not in resposta.text
    assert predio.unidade_102.identificacao not in resposta.text
    assert "placa_duplicada" not in dados
    lista = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador).json()
    assert [i["id"] for i in lista["items"]] == [dados["id"]]


def test_placa_pode_voltar_depois_da_remocao(client, session, predio, morador):
    antigo = criar_veiculo(session, predio, placa="ABC1D23", removido=True)
    resposta = client.post(URL, headers=morador, json=corpo(predio, placa="ABC1D23"))
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["id"] != str(antigo.id)


# --- consulta ---------------------------------------------------------------------------------


def test_listar_exige_unidade_do_morador(client, morador):
    assert client.get(URL, headers=morador).status_code == 422


def test_listar_so_traz_ativos_ordenados_por_placa(client, session, predio, morador):
    b = criar_veiculo(session, predio, placa="BBB2B22")
    a = criar_veiculo(session, predio, placa="AAA1A11")
    criar_veiculo(session, predio, placa="CCC3C33", removido=True)
    criar_veiculo(session, predio, unidade=predio.unidade_102, placa="DDD4D44")
    resposta = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador)
    assert resposta.status_code == 200
    corpo_json = resposta.json()
    assert [i["id"] for i in corpo_json["items"]] == [str(a.id), str(b.id)]
    assert corpo_json["total"] == 2 and corpo_json["page"] == 1 and corpo_json["page_size"] == 20


def test_obter_veiculo_removido_retorna_404(client, session, predio, morador):
    removido = criar_veiculo(session, predio, removido=True)
    resposta = client.get(f"{URL}/{removido.id}", headers=morador)
    assert resposta.status_code == 404


def test_obter_inexistente_e_404(client, morador):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=morador).status_code == 404


def test_busca_por_placa_marca_e_modelo(client, session, predio):
    argo = criar_veiculo(session, predio, placa="ABC1D23", marca="Fiat", modelo="Argo")
    gol = criar_veiculo(session, predio, placa="XYZ9K87", marca="Volkswagen", modelo="Gol")
    funcionario = predio.cabecalho_de(Perfil.FUNCIONARIO)

    def ids(busca):
        resposta = client.get(URL, params={"busca": busca}, headers=funcionario)
        assert resposta.status_code == 200, resposta.text
        return [i["id"] for i in resposta.json()["items"]]

    assert ids("abc1d23") == [str(argo.id)]
    assert ids("ABC-1D") == [str(argo.id)]  # a busca normaliza a placa como o cadastro
    assert ids("xyz") == [str(gol.id)]
    assert ids("volks") == [str(gol.id)]
    assert ids("ARGO") == [str(argo.id)]
    assert ids("nada") == []
    assert ids("%") == [] and ids("_") == []  # curingas do LIKE são texto comum


def test_busca_combina_com_unidade(client, session, predio, morador):
    meu = criar_veiculo(session, predio, placa="AAA1A11", marca="Fiat")
    criar_veiculo(session, predio, unidade=predio.unidade_102, placa="AAA2A22", marca="Fiat")
    resposta = client.get(
        URL, params={"unidade_id": str(predio.unidade_101.id), "busca": "fiat"}, headers=morador
    )
    assert [i["id"] for i in resposta.json()["items"]] == [str(meu.id)]


def test_listar_pagina(client, session, predio, morador):
    for numero in range(5):
        criar_veiculo(session, predio, placa=f"AAA{numero}A00")
    base = f"{URL}?unidade_id={predio.unidade_101.id}"
    primeira = client.get(f"{base}&page=1&page_size=2", headers=morador).json()
    ultima = client.get(f"{base}&page=3&page_size=2", headers=morador).json()
    assert primeira["total"] == 5
    assert [i["placa"] for i in primeira["items"]] == ["AAA0A00", "AAA1A00"]
    assert [i["placa"] for i in ultima["items"]] == ["AAA4A00"]
    for pagina in ("page=0", "page_size=0", "page_size=101"):
        assert client.get(f"{base}&{pagina}", headers=morador).status_code == 422, pagina


# --- edição -----------------------------------------------------------------------------------


def test_editar_substitui_os_dados(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    resposta = client.put(
        f"{URL}/{veiculo.id}",
        headers=morador,
        json=corpo(predio, placa="xyz-9k87", marca="Honda", modelo="Civic", cor="Preto"),
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert (dados["placa"], dados["marca"], dados["modelo"], dados["cor"]) == (
        "XYZ9K87",
        "Honda",
        "Civic",
        "Preto",
    )
    assert dados["id"] == str(veiculo.id) and dados["ativo"] is True


def test_editar_mantendo_a_propria_placa_vale(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio, placa="ABC1D23")
    resposta = client.put(f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio, cor="Azul"))
    assert resposta.status_code == 200 and resposta.json()["cor"] == "Azul"


def test_editar_sem_unidade_no_corpo_vale(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    dados = corpo(predio)
    del dados["unidade_id"]
    assert client.put(f"{URL}/{veiculo.id}", headers=morador, json=dados).status_code == 200


def test_editar_nao_troca_de_unidade(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    resposta = client.put(
        f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio, predio.unidade_102)
    )
    assert resposta.status_code == 422
    session.refresh(veiculo)
    assert veiculo.unidade_id == predio.unidade_101.id


def test_editar_para_placa_de_outro_veiculo_da_unidade_e_409(client, session, predio, morador):
    criar_veiculo(session, predio, placa="AAA1A11")
    veiculo = criar_veiculo(session, predio, placa="BBB2B22")
    resposta = client.put(
        f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio, placa="AAA1A11")
    )
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "placa_ja_cadastrada_na_unidade"
    session.refresh(veiculo)
    assert veiculo.placa == "BBB2B22"
    # A sessão segue utilizável depois do conflito.
    assert client.get(f"{URL}/{veiculo.id}", headers=morador).status_code == 200


def test_editar_para_placa_de_outra_unidade_vale(client, session, predio, morador):
    criar_veiculo(session, predio, unidade=predio.unidade_102, placa="AAA1A11")
    veiculo = criar_veiculo(session, predio, placa="BBB2B22")
    resposta = client.put(
        f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio, placa="AAA1A11")
    )
    assert resposta.status_code == 200


def test_editar_removido_e_404(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio, removido=True)
    resposta = client.put(f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio))
    assert resposta.status_code == 404


def test_editar_com_dados_invalidos_e_422(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    resposta = client.put(f"{URL}/{veiculo.id}", headers=morador, json=corpo(predio, placa="123"))
    assert resposta.status_code == 422


# --- remoção ----------------------------------------------------------------------------------


def test_remover_desativa_sem_apagar(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    resposta = client.post(f"{URL}/{veiculo.id}/remocao", headers=morador, json={})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["ativo"] is False
    session.refresh(veiculo)
    assert veiculo.ativo is False and veiculo.removido_em is not None  # a linha continua lá
    lista = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador)
    assert lista.json()["total"] == 0


def test_remover_duas_vezes_e_409(client, session, predio, morador):
    veiculo = criar_veiculo(session, predio)
    url = f"{URL}/{veiculo.id}/remocao"
    assert client.post(url, headers=morador, json={}).status_code == 200
    resposta = client.post(url, headers=morador, json={})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "veiculo_removido"


def test_cadastrar_de_novo_depois_de_remover_pela_api(client, predio, morador):
    criado = client.post(URL, headers=morador, json=corpo(predio)).json()
    assert client.post(f"{URL}/{criado['id']}/remocao", headers=morador, json={}).status_code == 200
    de_novo = client.post(URL, headers=morador, json=corpo(predio))
    assert de_novo.status_code == 201 and de_novo.json()["id"] != criado["id"]
