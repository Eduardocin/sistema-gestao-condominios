"""Matriz de perfis, passo 4 (unidade e aba) e isolamento entre condomínios dos visitantes."""

import uuid

import pytest

from app.core.permissoes import Perfil
from tests.reservas.cenario import definir_aba
from tests.visitantes.cenario import corpo, criar_visitante

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]
ROTAS = ["criar", "listar", "obter", "editar", "cancelar"]
#                 Morador Func. Admin. ADM
ESPERADO = {
    "criar": [201, 403, 403, 403],
    "listar": [200, 403, 403, 403],
    "obter": [200, 403, 403, 403],
    "editar": [200, 403, 403, 403],
    "cancelar": [200, 403, 403, 403],
}


def requisicao(predio, visitante, rota):
    base = "/api/v1/visitantes"
    return {
        "criar": ("POST", base, corpo(predio)),
        "listar": ("GET", f"{base}?unidade_id={predio.unidade_101.id}", None),
        "obter": ("GET", f"{base}/{visitante.id}", None),
        "editar": ("PUT", f"{base}/{visitante.id}", corpo(predio)),
        "cancelar": ("POST", f"{base}/{visitante.id}/cancelamento", {}),
    }[rota]


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_matriz_por_perfil(client, session, predio, rota, indice):
    visitante = criar_visitante(session, predio)
    metodo, url, json = requisicao(predio, visitante, rota)
    resposta = client.request(metodo, url, headers=predio.cabecalho_de(PERFIS[indice]), json=json)
    assert resposta.status_code == ESPERADO[rota][indice], resposta.text
    if resposta.status_code == 403:
        assert resposta.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("rota", ROTAS)
def test_sem_token_e_401(client, session, predio, rota):
    visitante = criar_visitante(session, predio)
    metodo, url, json = requisicao(predio, visitante, rota)
    assert client.request(metodo, url, json=json).status_code == 401


def test_403_de_perfil_vem_antes_de_422_e_404(client, predio):
    funcionario = predio.cabecalho_de(Perfil.FUNCIONARIO)
    assert client.post("/api/v1/visitantes", headers=funcionario, json={"x": 1}).status_code == 403
    administracao = predio.cabecalho_de(Perfil.ADMINISTRACAO)
    assert (
        client.put(
            f"/api/v1/visitantes/{uuid.uuid4()}", headers=administracao, json={"x": 1}
        ).status_code
        == 403
    )


# --- unidade e aba do Morador (passo 4) --------------------------------------------------------


def test_criar_em_unidade_alheia_e_404(client, predio):
    resposta = client.post(
        "/api/v1/visitantes",
        headers=predio.cabecalho_de(Perfil.MORADOR),
        json=corpo(predio, predio.unidade_102),
    )
    assert resposta.status_code == 404


def test_listar_unidade_alheia_e_404(client, predio):
    resposta = client.get(
        f"/api/v1/visitantes?unidade_id={predio.unidade_102.id}",
        headers=predio.cabecalho_de(Perfil.MORADOR),
    )
    assert resposta.status_code == 404


def test_visitante_de_outra_unidade_e_404_em_todas_as_rotas(client, session, predio):
    alheio = criar_visitante(session, predio, unidade=predio.unidade_102)
    morador = predio.cabecalho_de(Perfil.MORADOR)
    base = f"/api/v1/visitantes/{alheio.id}"
    assert client.get(base, headers=morador).status_code == 404
    assert client.put(base, headers=morador, json=corpo(predio)).status_code == 404
    assert client.post(f"{base}/cancelamento", headers=morador, json={}).status_code == 404


@pytest.mark.parametrize("rota", ROTAS)
def test_aba_sem_acesso_e_403(client, session, predio, rota):
    visitante = criar_visitante(session, predio)
    definir_aba(session, predio.morador_unidade, aba="visitantes", com_acesso=False)
    metodo, url, json = requisicao(predio, visitante, rota)
    resposta = client.request(metodo, url, headers=predio.cabecalho_de(Perfil.MORADOR), json=json)
    assert resposta.status_code == 403, resposta.text
    assert resposta.json()["error"]["code"] == "forbidden"


def test_aba_de_outro_recurso_nao_libera_visitantes(client, session, predio):
    definir_aba(session, predio.morador_unidade, aba="visitantes", com_acesso=False)
    definir_aba(session, predio.morador_unidade, aba="veiculos")
    resposta = client.get(
        f"/api/v1/visitantes?unidade_id={predio.unidade_101.id}",
        headers=predio.cabecalho_de(Perfil.MORADOR),
    )
    assert resposta.status_code == 403


# --- isolamento entre condomínios -------------------------------------------------------------


def test_visitante_de_outro_condominio_e_404(client, session, predio, outro_predio):
    alheio = criar_visitante(session, outro_predio)
    morador = predio.cabecalho_de(Perfil.MORADOR)
    base = f"/api/v1/visitantes/{alheio.id}"
    assert client.get(base, headers=morador).status_code == 404
    assert client.put(base, headers=morador, json=corpo(predio)).status_code == 404
    assert client.post(f"{base}/cancelamento", headers=morador, json={}).status_code == 404


def test_unidade_de_outro_condominio_e_404(client, predio, outro_predio):
    morador = predio.cabecalho_de(Perfil.MORADOR)
    assert (
        client.get(
            f"/api/v1/visitantes?unidade_id={outro_predio.unidade_101.id}", headers=morador
        ).status_code
        == 404
    )
    assert (
        client.post("/api/v1/visitantes", headers=morador, json=corpo(outro_predio)).status_code
        == 404
    )


def test_corpo_nao_aceita_condominio_id(client, predio):
    resposta = client.post(
        "/api/v1/visitantes",
        headers=predio.cabecalho_de(Perfil.MORADOR),
        json=corpo(predio, condominio_id=str(uuid.uuid4())),
    )
    assert resposta.status_code == 422
