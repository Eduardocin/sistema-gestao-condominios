"""Ocorrências: matriz por perfil, 401, unidade alheia, aba Sem Acesso e isolamento."""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.core.permissoes import Perfil
from app.modules.ocorrencias.models import Ocorrencia
from tests.autorizacao.cenario import Predio
from tests.ocorrencias.cenario import corpo, criar_ocorrencia, resolucao, resposta
from tests.reservas.cenario import criar_responsavel

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]


@dataclass
class Cena:
    predio: Predio
    ocorrencia: Ocorrencia
    responsavel_id: uuid.UUID


@pytest.fixture
def cena(session, predio) -> Cena:
    return Cena(
        predio=predio,
        ocorrencia=criar_ocorrencia(session, predio),
        responsavel_id=criar_responsavel(session, predio).id,
    )


def requisicao(cena: Cena, rota: str, perfil: str) -> tuple[str, str, Any]:
    p = cena.predio
    return {
        "criar": ("POST", "/api/v1/ocorrencias", corpo(p)),
        "listar": ("GET", f"/api/v1/ocorrencias?unidade_id={p.unidade_101.id}", None),
        "obter": ("GET", f"/api/v1/ocorrencias/{cena.ocorrencia.id}", None),
        "responder": (
            "POST",
            f"/api/v1/ocorrencias/{cena.ocorrencia.id}/respostas",
            resposta(cena.responsavel_id),
        ),
        "resolver": (
            "POST",
            f"/api/v1/ocorrencias/{cena.ocorrencia.id}/resolucao",
            resolucao(cena.responsavel_id),
        ),
    }[rota]


ROTAS = ["criar", "listar", "obter", "responder", "resolver"]
ESPERADO = {
    #             Morador Func.  Admin. ADM
    "criar": [201, 403, 403, 403],
    "listar": [200, 403, 200, 403],
    "obter": [200, 403, 200, 403],
    "responder": [403, 403, 201, 403],
    "resolver": [403, 403, 200, 403],
}


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_matriz_por_perfil(client, cena, rota, indice):
    perfil = PERFIS[indice]
    metodo, url, json = requisicao(cena, rota, perfil)
    resposta_http = client.request(metodo, url, headers=cena.predio.cabecalho_de(perfil), json=json)
    assert resposta_http.status_code == ESPERADO[rota][indice], resposta_http.text
    if resposta_http.status_code == 403:
        assert resposta_http.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("rota", ROTAS)
def test_sem_token_e_401(client, cena, rota):
    metodo, url, json = requisicao(cena, rota, Perfil.MORADOR)
    assert client.request(metodo, url, json=json).status_code == 401


def test_403_de_perfil_vem_antes_de_422_e_404(client, cena):
    # Funcionário não cria ocorrência: 403 mesmo com corpo inválido.
    funcionario = cena.predio.cabecalho_de(Perfil.FUNCIONARIO)
    assert client.post("/api/v1/ocorrencias", headers=funcionario, json={"x": 1}).status_code == 403
    # Morador não responde: 403 sem validar o corpo.
    morador = cena.predio.cabecalho_de(Perfil.MORADOR)
    assert (
        client.post(
            f"/api/v1/ocorrencias/{uuid.uuid4()}/respostas", headers=morador, json={"x": 1}
        ).status_code
        == 403
    )
    # Administração não abre ocorrência.
    administracao = cena.predio.cabecalho_de(Perfil.ADMINISTRACAO)
    assert (
        client.post("/api/v1/ocorrencias", headers=administracao, json={"x": 1}).status_code == 403
    )


# --- unidade e aba do Morador (passo 4) --------------------------------------------------------


def test_criar_em_unidade_alheia_e_404(client, session, cena):
    resposta_http = client.post(
        "/api/v1/ocorrencias",
        headers=cena.predio.cabecalho_de(Perfil.MORADOR),
        json=corpo(cena.predio, cena.predio.unidade_102),
    )
    assert resposta_http.status_code == 404


def test_listar_e_obter_outra_unidade_e_404(client, session, cena):
    vizinha = criar_ocorrencia(session, cena.predio, unidade=cena.predio.unidade_102)
    morador = cena.predio.cabecalho_de(Perfil.MORADOR)
    assert (
        client.get(
            f"/api/v1/ocorrencias?unidade_id={cena.predio.unidade_102.id}", headers=morador
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/ocorrencias/{vizinha.id}", headers=morador).status_code == 404


def test_aba_sem_acesso_e_403_mesmo_burlando_a_tela(client, session, cena):
    from tests.reservas.cenario import definir_aba

    definir_aba(session, cena.predio.morador_unidade, aba="ocorrencias", com_acesso=False)
    morador = cena.predio.cabecalho_de(Perfil.MORADOR)
    assert (
        client.post("/api/v1/ocorrencias", headers=morador, json=corpo(cena.predio)).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/ocorrencias?unidade_id={cena.predio.unidade_101.id}", headers=morador
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/ocorrencias/{cena.ocorrencia.id}", headers=morador).status_code == 403
    )


def test_aba_de_outra_unidade_nao_vale(client, session, cena):
    from tests.reservas.cenario import definir_aba

    definir_aba(session, cena.predio.morador_unidade, aba="ocorrencias", com_acesso=False)
    definir_aba(session, cena.predio.morador_unidade, aba="reservas", com_acesso=True)
    assert (
        client.get(
            f"/api/v1/ocorrencias?unidade_id={cena.predio.unidade_101.id}",
            headers=cena.predio.cabecalho_de(Perfil.MORADOR),
        ).status_code
        == 403
    )


# --- isolamento entre condomínios --------------------------------------------------------------


def test_administracao_de_outro_condominio_nao_ve_nem_trata(client, session, cena, outro_predio):
    intruso = outro_predio.cabecalho_de(Perfil.ADMINISTRACAO)
    responsavel_dele = criar_responsavel(session, outro_predio)
    base = f"/api/v1/ocorrencias/{cena.ocorrencia.id}"

    assert client.get(base, headers=intruso).status_code == 404
    assert client.get("/api/v1/ocorrencias", headers=intruso).json()["total"] == 0
    # Filtrar pela unidade do outro prédio não abre nada.
    filtrada = client.get(
        f"/api/v1/ocorrencias?unidade_id={cena.predio.unidade_101.id}", headers=intruso
    ).json()
    assert filtrada["total"] == 0
    assert (
        client.post(
            f"{base}/respostas", headers=intruso, json=resposta(responsavel_dele.id)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{base}/resolucao", headers=intruso, json=resolucao(responsavel_dele.id)
        ).status_code
        == 404
    )
    session.refresh(cena.ocorrencia)
    assert cena.ocorrencia.status == "em_aberto"


def test_morador_de_outro_condominio_nao_ve_ocorrencia_alheia(client, cena, outro_predio):
    cab = outro_predio.cabecalho_de(Perfil.MORADOR)
    assert client.get(f"/api/v1/ocorrencias/{cena.ocorrencia.id}", headers=cab).status_code == 404
    # A unidade dele é válida, mas a ocorrência do outro prédio não existe para ele.
    assert (
        client.get(
            f"/api/v1/ocorrencias?unidade_id={cena.predio.unidade_101.id}", headers=cab
        ).status_code
        == 404
    )
