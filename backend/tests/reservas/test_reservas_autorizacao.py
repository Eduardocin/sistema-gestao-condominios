"""Reservas: matriz por perfil, 401, unidade alheia, aba Sem Acesso e isolamento entre prédios."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from app.core.permissoes import Perfil
from app.modules.reservas.models import AreaComum, Reserva
from tests.autorizacao.cenario import Predio
from tests.reservas.cenario import (
    AGORA,
    DIA,
    criar_area,
    criar_reserva,
    criar_responsavel,
    definir_aba,
    novo_morador,
    pedido,
)

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]
DEPOIS = DIA + timedelta(days=1)


@pytest.fixture(autouse=True)
def congelar(relogio):
    relogio.momento = AGORA


@dataclass
class Cena:
    predio: Predio
    area: AreaComum
    da_101: Reserva  # reserva da unidade do morador
    da_102: Reserva  # reserva do vizinho, outra unidade
    responsavel_id: uuid.UUID
    vizinho: dict[str, str]  # cabeçalho do morador da 102


@pytest.fixture
def cena(session, predio) -> Cena:
    definir_aba(session, predio.morador_unidade)  # o morador da 101 está Com Acesso
    _, _, vizinho = novo_morador(session, predio, predio.unidade_102, nome="Vizinho Secreto")
    area = criar_area(session, predio)
    return Cena(
        predio=predio,
        area=area,
        da_101=criar_reserva(session, predio, area, data=DIA, hora=18),
        da_102=criar_reserva(session, predio, area, data=DIA, hora=19, unidade=predio.unidade_102),
        responsavel_id=criar_responsavel(session, predio).id,
        vizinho=vizinho,
    )


def requisicao(cena: Cena, rota: str, perfil: str) -> tuple[str, str, Any]:
    """(método, URL, corpo) de cada rota, já preenchidos para o perfil."""
    p, area, u101 = cena.predio, cena.area, cena.predio.unidade_101.id
    cancelamento: dict[str, Any] = (
        {"motivo": "Manutenção", "responsavel_id": str(cena.responsavel_id)}
        if perfil == Perfil.ADMINISTRACAO
        else {}
    )
    return {
        "agenda": (
            "GET",
            f"/api/v1/areas-comuns/{area.id}/agenda?unidade_id={u101}&data={DIA}",
            None,
        ),
        "calendario": (
            "GET",
            f"/api/v1/areas-comuns/{area.id}/calendario?unidade_id={u101}&mes=2030-06",
            None,
        ),
        # Outro dia: a 101 já reservou esta área em DIA (cena.da_101).
        "criar": ("POST", "/api/v1/reservas", pedido(area, p.unidade_101, DEPOIS, "10:00")),
        "listar": ("GET", f"/api/v1/reservas?unidade_id={u101}", None),
        "obter": ("GET", f"/api/v1/reservas/{cena.da_101.id}", None),
        "cancelar": ("POST", f"/api/v1/reservas/{cena.da_101.id}/cancelamento", cancelamento),
    }[rota]


ROTAS = ["agenda", "calendario", "criar", "listar", "obter", "cancelar"]
ESPERADO = {
    #             Morador Func.  Admin. ADM
    "agenda": [200, 403, 403, 403],
    "calendario": [200, 403, 403, 403],
    "criar": [201, 403, 403, 403],
    "listar": [200, 403, 200, 403],
    "obter": [200, 403, 200, 403],
    "cancelar": [200, 403, 200, 403],
}


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_matriz_por_perfil(client, cena, rota, indice):
    perfil = PERFIS[indice]
    metodo, url, corpo = requisicao(cena, rota, perfil)
    resposta = client.request(metodo, url, headers=cena.predio.cabecalho_de(perfil), json=corpo)
    assert resposta.status_code == ESPERADO[rota][indice], resposta.text
    if resposta.status_code == 403:
        assert resposta.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("rota", ROTAS)
def test_sem_token_e_401(client, cena, rota):
    metodo, url, corpo = requisicao(cena, rota, Perfil.MORADOR)
    assert client.request(metodo, url, json=corpo).status_code == 401


@pytest.mark.parametrize("perfil", [Perfil.FUNCIONARIO, Perfil.PLATAFORMA, Perfil.ADMINISTRACAO])
def test_403_de_perfil_vem_antes_de_422_e_404(client, cena, perfil):
    cab = cena.predio.cabecalho_de(perfil)
    # Administração não cria reserva nem vê agenda: 403 mesmo com corpo e IDs inválidos.
    assert client.post("/api/v1/reservas", headers=cab, json={"x": 1}).status_code == 403
    url = f"/api/v1/areas-comuns/{uuid.uuid4()}/agenda?unidade_id=nao-uuid&data=ontem"
    assert client.get(url, headers=cab).status_code == 403


# --- unidade e aba do Morador (passo 4) --------------------------------------------------------


def rota_com_a_unidade_102(cena: Cena, rota: str) -> tuple[str, str, Any]:
    """A mesma rota, mas apontando para a unidade (ou reserva) do vizinho."""
    area, u102 = cena.area, cena.predio.unidade_102
    return {
        "agenda": (
            "GET",
            f"/api/v1/areas-comuns/{area.id}/agenda?unidade_id={u102.id}&data={DIA}",
            None,
        ),
        "calendario": (
            "GET",
            f"/api/v1/areas-comuns/{area.id}/calendario?unidade_id={u102.id}&mes=2030-06",
            None,
        ),
        "criar": ("POST", "/api/v1/reservas", pedido(area, u102, DIA, "10:00")),
        "listar": ("GET", f"/api/v1/reservas?unidade_id={u102.id}", None),
        "obter": ("GET", f"/api/v1/reservas/{cena.da_102.id}", None),
        "cancelar": ("POST", f"/api/v1/reservas/{cena.da_102.id}/cancelamento", {}),
    }[rota]


@pytest.mark.parametrize("rota", ROTAS)
def test_unidade_de_outro_morador_e_404(client, session, cena, rota):
    metodo, url, corpo = rota_com_a_unidade_102(cena, rota)
    resposta = client.request(
        metodo, url, headers=cena.predio.cabecalho_de(Perfil.MORADOR), json=corpo
    )
    assert resposta.status_code == 404, resposta.text
    session.refresh(cena.da_102)
    assert cena.da_102.status == "ativa"  # o cancelamento alheio não passou


@pytest.mark.parametrize("rota", ROTAS)
def test_aba_sem_acesso_e_403_mesmo_burlando_a_tela(client, session, cena, rota):
    definir_aba(session, cena.predio.morador_unidade, com_acesso=False)
    metodo, url, corpo = requisicao(cena, rota, Perfil.MORADOR)
    resposta = client.request(
        metodo, url, headers=cena.predio.cabecalho_de(Perfil.MORADOR), json=corpo
    )
    assert resposta.status_code == 403, resposta.text
    session.refresh(cena.da_101)
    assert cena.da_101.status == "ativa"


@pytest.mark.parametrize("rota", ROTAS)
def test_aba_de_outra_unidade_nao_vale(client, session, cena, rota):
    """Aba Com Acesso em outra aba (Visitantes) não libera Reservas: negar por padrão."""
    definir_aba(session, cena.predio.morador_unidade, com_acesso=False)
    definir_aba(session, cena.predio.morador_unidade, aba="visitantes", com_acesso=True)
    metodo, url, corpo = requisicao(cena, rota, Perfil.MORADOR)
    resposta = client.request(
        metodo, url, headers=cena.predio.cabecalho_de(Perfil.MORADOR), json=corpo
    )
    assert resposta.status_code == 403


def test_a_mudanca_da_aba_vale_na_proxima_requisicao(client, session, cena):
    cab = cena.predio.cabecalho_de(Perfil.MORADOR)
    url = f"/api/v1/reservas?unidade_id={cena.predio.unidade_101.id}"
    assert client.get(url, headers=cab).status_code == 200
    definir_aba(session, cena.predio.morador_unidade, com_acesso=False)
    assert client.get(url, headers=cab).status_code == 403


def test_unidade_inexistente_e_404(client, cena):
    resposta = client.get(
        f"/api/v1/reservas?unidade_id={uuid.uuid4()}",
        headers=cena.predio.cabecalho_de(Perfil.MORADOR),
    )
    assert resposta.status_code == 404


# --- isolamento entre condomínios --------------------------------------------------------------


def test_administracao_de_outro_condominio_recebe_404(client, session, cena, outro_predio):
    intruso = outro_predio.cabecalho_de(Perfil.ADMINISTRACAO)
    responsavel_dele = criar_responsavel(session, outro_predio)
    base = f"/api/v1/reservas/{cena.da_101.id}"

    assert client.get(base, headers=intruso).status_code == 404
    cancelar = client.post(
        f"{base}/cancelamento",
        headers=intruso,
        json={"motivo": "Teste", "responsavel_id": str(responsavel_dele.id)},
    )
    assert cancelar.status_code == 404
    assert client.get("/api/v1/reservas", headers=intruso).json()["total"] == 0
    # Filtrar por unidade de outro prédio não abre nada: lista vazia.
    filtrada = client.get(
        f"/api/v1/reservas?unidade_id={cena.predio.unidade_101.id}", headers=intruso
    ).json()
    assert filtrada["total"] == 0
    session.refresh(cena.da_101)
    assert cena.da_101.status == "ativa"


def test_morador_de_outro_condominio_nao_reserva_area_alheia(client, session, cena, outro_predio):
    definir_aba(session, outro_predio.morador_unidade)
    cab = outro_predio.cabecalho_de(Perfil.MORADOR)
    # A unidade é dele, mas a área é do outro prédio: 404 da área.
    resposta = client.post(
        "/api/v1/reservas", headers=cab, json=pedido(cena.area, outro_predio.unidade_101)
    )
    assert resposta.status_code == 404
    agenda = client.get(
        f"/api/v1/areas-comuns/{cena.area.id}/agenda"
        f"?unidade_id={outro_predio.unidade_101.id}&data={DIA}",
        headers=cab,
    )
    assert agenda.status_code == 404
    # E a unidade do outro prédio, para ele, não existe.
    resposta = client.get(f"/api/v1/reservas?unidade_id={cena.predio.unidade_101.id}", headers=cab)
    assert resposta.status_code == 404
    assert client.get(f"/api/v1/reservas/{cena.da_101.id}", headers=cab).status_code == 404


def test_responsavel_de_outro_condominio_e_404(client, session, cena, outro_predio):
    responsavel_alheio = criar_responsavel(session, outro_predio)
    resposta = client.post(
        f"/api/v1/reservas/{cena.da_101.id}/cancelamento",
        headers=cena.predio.cabecalho_de(Perfil.ADMINISTRACAO),
        json={"motivo": "Manutenção", "responsavel_id": str(responsavel_alheio.id)},
    )
    assert resposta.status_code == 404
    session.refresh(cena.da_101)
    assert cena.da_101.status == "ativa"


def test_condominio_id_no_corpo_e_rejeitado(client, cena, outro_predio):
    corpo = pedido(cena.area, cena.predio.unidade_101) | {
        "condominio_id": str(outro_predio.condominio.id)
    }
    resposta = client.post(
        "/api/v1/reservas", headers=cena.predio.cabecalho_de(Perfil.MORADOR), json=corpo
    )
    assert resposta.status_code == 422
