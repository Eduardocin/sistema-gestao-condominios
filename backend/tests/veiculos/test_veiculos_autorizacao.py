"""Matriz de perfis, passo 4 (unidade e aba) e isolamento entre condomínios dos veículos."""

import uuid

import pytest

from app.core.permissoes import Perfil
from tests.reservas.cenario import definir_aba
from tests.veiculos.cenario import corpo, criar_veiculo

URL = "/api/v1/veiculos"
PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]
ROTAS = ["criar", "listar", "obter", "editar", "remover"]
#                 Morador Func. Admin. ADM
ESPERADO = {
    "criar": [201, 403, 403, 403],
    "listar": [200, 200, 200, 403],
    "obter": [200, 200, 200, 403],
    "editar": [200, 403, 403, 403],
    "remover": [200, 403, 403, 403],
}


def requisicao(predio, veiculo, rota):
    return {
        "criar": ("POST", URL, corpo(predio, placa="XYZ9K87")),
        "listar": ("GET", f"{URL}?unidade_id={predio.unidade_101.id}", None),
        "obter": ("GET", f"{URL}/{veiculo.id}", None),
        "editar": ("PUT", f"{URL}/{veiculo.id}", corpo(predio)),
        "remover": ("POST", f"{URL}/{veiculo.id}/remocao", {}),
    }[rota]


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_matriz_por_perfil(client, session, predio, rota, indice):
    veiculo = criar_veiculo(session, predio)
    metodo, url, json = requisicao(predio, veiculo, rota)
    resposta = client.request(metodo, url, headers=predio.cabecalho_de(PERFIS[indice]), json=json)
    assert resposta.status_code == ESPERADO[rota][indice], resposta.text
    if resposta.status_code == 403:
        assert resposta.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("rota", ROTAS)
def test_sem_token_e_401(client, session, predio, rota):
    veiculo = criar_veiculo(session, predio)
    metodo, url, json = requisicao(predio, veiculo, rota)
    assert client.request(metodo, url, json=json).status_code == 401


def test_403_de_perfil_vem_antes_de_422_e_404(client, predio):
    funcionario = predio.cabecalho_de(Perfil.FUNCIONARIO)
    assert client.post(URL, headers=funcionario, json={"x": 1}).status_code == 403
    administracao = predio.cabecalho_de(Perfil.ADMINISTRACAO)
    assert client.put(f"{URL}/{uuid.uuid4()}", headers=administracao, json={}).status_code == 403


# --- portaria e Administração: o condomínio inteiro --------------------------------------------


@pytest.mark.parametrize("perfil", [Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO])
def test_portaria_e_administracao_listam_o_condominio_todo(client, session, predio, perfil):
    primeiro = criar_veiculo(session, predio, placa="AAA1A11")
    segundo = criar_veiculo(session, predio, unidade=predio.unidade_102, placa="BBB2B22")
    resposta = client.get(URL, headers=predio.cabecalho_de(perfil))
    assert resposta.status_code == 200
    assert [i["id"] for i in resposta.json()["items"]] == [str(primeiro.id), str(segundo.id)]
    so_102 = client.get(
        f"{URL}?unidade_id={predio.unidade_102.id}", headers=predio.cabecalho_de(perfil)
    )
    assert [i["id"] for i in so_102.json()["items"]] == [str(segundo.id)]
    por_id = client.get(f"{URL}/{segundo.id}", headers=predio.cabecalho_de(perfil))
    assert por_id.status_code == 200


def test_funcionario_nao_depende_da_aba_do_morador(client, session, predio):
    criar_veiculo(session, predio)
    definir_aba(session, predio.morador_unidade, aba="veiculos", com_acesso=False)
    resposta = client.get(URL, headers=predio.cabecalho_de(Perfil.FUNCIONARIO))
    assert resposta.status_code == 200 and resposta.json()["total"] == 1


# --- unidade e aba do Morador (passo 4) --------------------------------------------------------


def test_criar_em_unidade_alheia_e_404(client, predio):
    resposta = client.post(
        URL, headers=predio.cabecalho_de(Perfil.MORADOR), json=corpo(predio, predio.unidade_102)
    )
    assert resposta.status_code == 404


def test_listar_unidade_alheia_e_404(client, predio):
    resposta = client.get(
        f"{URL}?unidade_id={predio.unidade_102.id}", headers=predio.cabecalho_de(Perfil.MORADOR)
    )
    assert resposta.status_code == 404


def test_veiculo_de_outra_unidade_e_404_em_todas_as_rotas(client, session, predio):
    alheio = criar_veiculo(session, predio, unidade=predio.unidade_102)
    morador = predio.cabecalho_de(Perfil.MORADOR)
    base = f"{URL}/{alheio.id}"
    assert client.get(base, headers=morador).status_code == 404
    assert client.put(base, headers=morador, json=corpo(predio)).status_code == 404
    assert client.post(f"{base}/remocao", headers=morador, json={}).status_code == 404


@pytest.mark.parametrize("rota", ROTAS)
def test_aba_sem_acesso_e_403(client, session, predio, rota):
    veiculo = criar_veiculo(session, predio)
    definir_aba(session, predio.morador_unidade, aba="veiculos", com_acesso=False)
    metodo, url, json = requisicao(predio, veiculo, rota)
    resposta = client.request(metodo, url, headers=predio.cabecalho_de(Perfil.MORADOR), json=json)
    assert resposta.status_code == 403, resposta.text
    assert resposta.json()["error"]["code"] == "forbidden"


def test_aba_de_outro_recurso_nao_libera_veiculos(client, session, predio):
    definir_aba(session, predio.morador_unidade, aba="veiculos", com_acesso=False)
    definir_aba(session, predio.morador_unidade, aba="visitantes")
    resposta = client.get(
        f"{URL}?unidade_id={predio.unidade_101.id}", headers=predio.cabecalho_de(Perfil.MORADOR)
    )
    assert resposta.status_code == 403


# --- isolamento entre condomínios -------------------------------------------------------------


@pytest.mark.parametrize("perfil", [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO])
def test_veiculo_de_outro_condominio_e_404(client, session, predio, outro_predio, perfil):
    alheio = criar_veiculo(session, outro_predio)
    headers = predio.cabecalho_de(perfil)
    assert client.get(f"{URL}/{alheio.id}", headers=headers).status_code == 404
    if perfil == Perfil.MORADOR:
        assert (
            client.put(f"{URL}/{alheio.id}", headers=headers, json=corpo(predio)).status_code == 404
        )
        assert (
            client.post(f"{URL}/{alheio.id}/remocao", headers=headers, json={}).status_code == 404
        )


@pytest.mark.parametrize("perfil", [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO])
def test_lista_nunca_traz_veiculo_de_outro_condominio(
    client, session, predio, outro_predio, perfil
):
    criar_veiculo(session, outro_predio, placa="ZZZ9Z99")
    meu = criar_veiculo(session, predio, placa="AAA1A11")
    url = f"{URL}?unidade_id={predio.unidade_101.id}"
    resposta = client.get(url, headers=predio.cabecalho_de(perfil))
    assert [i["id"] for i in resposta.json()["items"]] == [str(meu.id)]
    assert "ZZZ9Z99" not in resposta.text


@pytest.mark.parametrize("perfil", [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO])
def test_unidade_de_outro_condominio_e_404(client, predio, outro_predio, perfil):
    resposta = client.get(
        f"{URL}?unidade_id={outro_predio.unidade_101.id}", headers=predio.cabecalho_de(perfil)
    )
    assert resposta.status_code == 404


def test_corpo_nao_aceita_condominio_id(client, predio):
    resposta = client.post(
        URL,
        headers=predio.cabecalho_de(Perfil.MORADOR),
        json=corpo(predio, condominio_id=str(uuid.uuid4())),
    )
    assert resposta.status_code == 422
