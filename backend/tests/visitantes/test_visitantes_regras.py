"""Regras de cadastro, consulta, edição e cancelamento dos visitantes (US-501)."""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.core.permissoes import Perfil
from app.modules.visitantes.models import Visitante
from tests.visitantes.cenario import corpo, criar_visitante, registrar_visita

URL = "/api/v1/visitantes"


@pytest.fixture
def morador(predio):
    return predio.cabecalho_de(Perfil.MORADOR)


# --- cadastro ---------------------------------------------------------------------------------


def test_criar_devolve_o_cadastro(client, session, predio, morador):
    resposta = client.post(URL, headers=morador, json=corpo(predio))
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert resposta.headers["Location"] == f"{URL}/{dados['id']}"
    assert dados["unidade"] == {
        "id": str(predio.unidade_101.id),
        "identificacao": predio.unidade_101.identificacao,
    }
    assert dados["nome"] == "Carlos Souza"
    assert dados["cpf"] == "12345678909"
    assert dados["idade"] == 35
    assert dados["avulso"] is False
    assert dados["situacao"] == "vigente"
    assert dados["ja_utilizado"] is False
    assert dados["cancelado_em"] is None
    gravado = session.get(Visitante, uuid.UUID(dados["id"]))
    assert gravado.condominio_id == predio.condominio.id
    assert gravado.cadastrado_por_usuario_id == predio.morador.id


def test_criar_so_com_obrigatorios_e_normaliza_texto(client, predio, morador):
    resposta = client.post(
        URL,
        headers=morador,
        json={
            "unidade_id": str(predio.unidade_101.id),
            "nome": "  Maria Lima  ",
            "observacoes": "   ",
            "entrada_prevista": "2026-11-20",
            "saida_prevista": "2026-11-20",
        },
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["nome"] == "Maria Lima"
    assert dados["cpf"] is None and dados["idade"] is None and dados["observacoes"] is None
    assert dados["situacao"] == "futuro"


@pytest.mark.parametrize(
    "campos",
    [
        {"cpf": "12345678900"},  # dígitos verificadores errados
        {"cpf": "11111111111"},  # repetidos
        {"cpf": "123.456.789-09"},  # com máscara
        {"cpf": "1234567890"},  # 10 dígitos
        {"cpf": "11222333000181"},  # CNPJ válido não vale como CPF
        {"nome": "Jo"},
        {"nome": "   "},
        {"nome": "x" * 121},
        {"idade": -1},
        {"idade": 121},
        {"observacoes": "x" * 301},
        {"entrada_prevista": "2026-11-16", "saida_prevista": "2026-11-15"},
        {"entrada_prevista": "amanhã"},
        {"avulso": True},
        {"cancelado_em": "2026-11-15T10:00:00Z"},
    ],
)
def test_entrada_invalida_e_422(client, predio, morador, campos):
    resposta = client.post(URL, headers=morador, json=corpo(predio, **campos))
    assert resposta.status_code == 422, resposta.text


def test_campos_obrigatorios(client, predio, morador):
    for campo in ("unidade_id", "nome", "entrada_prevista", "saida_prevista"):
        dados = corpo(predio)
        del dados[campo]
        assert client.post(URL, headers=morador, json=dados).status_code == 422, campo


def test_saida_igual_a_entrada_vale(client, predio, morador):
    dados = corpo(predio, entrada_prevista="2026-11-15", saida_prevista="2026-11-15")
    assert client.post(URL, headers=morador, json=dados).status_code == 201


def test_observacoes_com_300_caracteres_vale(client, predio, morador):
    assert (
        client.post(URL, headers=morador, json=corpo(predio, observacoes="x" * 300)).status_code
        == 201
    )


# --- consulta ---------------------------------------------------------------------------------


def test_obter_devolve_o_cadastro(client, session, predio, morador):
    visitante = criar_visitante(session, predio, cpf="12345678909")
    resposta = client.get(f"{URL}/{visitante.id}", headers=morador)
    assert resposta.status_code == 200
    assert resposta.json()["id"] == str(visitante.id)
    assert resposta.json()["cpf"] == "12345678909"  # o Morador vê o que cadastrou


def test_obter_inexistente_e_404(client, morador):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=morador).status_code == 404


def test_listar_exige_unidade(client, morador):
    assert client.get(URL, headers=morador).status_code == 422


def test_listar_so_da_unidade_informada(client, session, predio, morador):
    meu = criar_visitante(session, predio, nome="Meu Visitante")
    criar_visitante(session, predio, unidade=predio.unidade_102, nome="Visitante Alheio")
    resposta = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador)
    assert resposta.status_code == 200
    corpo_json = resposta.json()
    assert [i["id"] for i in corpo_json["items"]] == [str(meu.id)]
    assert corpo_json["total"] == 1 and corpo_json["page"] == 1 and corpo_json["page_size"] == 20
    assert "Visitante Alheio" not in resposta.text


def test_listar_filtra_por_situacao(client, session, predio, morador):
    # "Hoje" é 15/11/2026 (conftest).
    vigente = criar_visitante(session, predio, nome="Vigente", entrada=date(2026, 11, 15))
    ultimo_dia = criar_visitante(
        session, predio, nome="Ultimo Dia", entrada=date(2026, 11, 10), saida=date(2026, 11, 15)
    )
    futuro = criar_visitante(
        session, predio, nome="Futuro", entrada=date(2026, 11, 16), saida=date(2026, 11, 17)
    )
    encerrado = criar_visitante(
        session, predio, nome="Encerrado", entrada=date(2026, 11, 1), saida=date(2026, 11, 14)
    )
    cancelado = criar_visitante(
        session, predio, nome="Cancelado", cancelado_em=datetime(2026, 11, 12, tzinfo=UTC)
    )
    cancelado_futuro = criar_visitante(
        session,
        predio,
        nome="Cancelado Futuro",
        entrada=date(2026, 12, 1),
        saida=date(2026, 12, 2),
        cancelado_em=datetime(2026, 11, 12, tzinfo=UTC),
    )

    def ids(situacao):
        resposta = client.get(
            f"{URL}?unidade_id={predio.unidade_101.id}&situacao={situacao}", headers=morador
        )
        assert resposta.status_code == 200
        return {i["id"] for i in resposta.json()["items"]}

    assert ids("vigentes") == {str(vigente.id), str(ultimo_dia.id)}  # inclusive o último dia
    assert ids("futuros") == {str(futuro.id)}
    assert ids("encerrados") == {str(encerrado.id)}
    assert ids("cancelados") == {str(cancelado.id), str(cancelado_futuro.id)}
    todos = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador).json()
    assert todos["total"] == 6
    situacoes = {i["nome"]: i["situacao"] for i in todos["items"]}
    assert situacoes == {
        "Vigente": "vigente",
        "Ultimo Dia": "vigente",
        "Futuro": "futuro",
        "Encerrado": "encerrado",
        "Cancelado": "cancelado",
        "Cancelado Futuro": "cancelado",
    }


def test_listar_situacao_invalida_e_422(client, predio, morador):
    resposta = client.get(
        f"{URL}?unidade_id={predio.unidade_101.id}&situacao=qualquer", headers=morador
    )
    assert resposta.status_code == 422


def test_listar_busca_por_nome_e_cpf(client, session, predio, morador):
    ana = criar_visitante(session, predio, nome="Ana Paula Ramos", cpf="52998224725")
    criar_visitante(session, predio, nome="Bruno Teixeira")

    def ids(busca):
        resposta = client.get(
            URL,
            params={"unidade_id": str(predio.unidade_101.id), "busca": busca},
            headers=morador,
        )
        assert resposta.status_code == 200, resposta.text
        return [i["id"] for i in resposta.json()["items"]]

    assert ids("paula") == [str(ana.id)]
    assert ids("529982") == [str(ana.id)]
    assert ids("nao existe") == []
    # Curingas do LIKE são texto comum, não padrão.
    assert ids("%") == []
    assert ids("_") == []


def test_listar_pagina(client, session, predio, morador):
    for numero in range(5):
        criar_visitante(
            session,
            predio,
            nome=f"Visitante {numero}",
            entrada=date(2026, 11, 1 + numero),
            saida=date(2026, 11, 20),
        )
    primeira = client.get(
        f"{URL}?unidade_id={predio.unidade_101.id}&page=1&page_size=2", headers=morador
    ).json()
    ultima = client.get(
        f"{URL}?unidade_id={predio.unidade_101.id}&page=3&page_size=2", headers=morador
    ).json()
    assert primeira["total"] == 5 and len(primeira["items"]) == 2
    assert [i["nome"] for i in primeira["items"]] == ["Visitante 4", "Visitante 3"]
    assert [i["nome"] for i in ultima["items"]] == ["Visitante 0"]
    for pagina in ("page=0", "page_size=0", "page_size=101"):
        resposta = client.get(f"{URL}?unidade_id={predio.unidade_101.id}&{pagina}", headers=morador)
        assert resposta.status_code == 422, pagina


def test_ja_utilizado_reflete_a_visita(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    antes = client.get(f"{URL}/{visitante.id}", headers=morador).json()
    registrar_visita(session, predio, visitante)
    depois = client.get(f"{URL}/{visitante.id}", headers=morador).json()
    assert antes["ja_utilizado"] is False and depois["ja_utilizado"] is True


# --- edição -----------------------------------------------------------------------------------


def test_editar_substitui_os_dados(client, session, predio, morador):
    visitante = criar_visitante(session, predio, cpf="12345678909")
    novo = corpo(
        predio,
        nome="Carlos Souza Filho",
        cpf=None,
        idade=None,
        observacoes=None,
        entrada_prevista="2026-11-20",
        saida_prevista="2026-11-22",
    )
    resposta = client.put(f"{URL}/{visitante.id}", headers=morador, json=novo)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["nome"] == "Carlos Souza Filho"
    assert dados["cpf"] is None and dados["idade"] is None and dados["observacoes"] is None
    assert dados["entrada_prevista"] == "2026-11-20" and dados["situacao"] == "futuro"
    assert dados["unidade"]["id"] == str(predio.unidade_101.id)


def test_editar_sem_unidade_no_corpo_vale(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    dados = corpo(predio)
    del dados["unidade_id"]
    assert client.put(f"{URL}/{visitante.id}", headers=morador, json=dados).status_code == 200


def test_editar_nao_troca_de_unidade(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    resposta = client.put(
        f"{URL}/{visitante.id}", headers=morador, json=corpo(predio, predio.unidade_102)
    )
    assert resposta.status_code == 422
    session.refresh(visitante)
    assert visitante.unidade_id == predio.unidade_101.id


def test_editar_com_dados_invalidos_e_422(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    resposta = client.put(
        f"{URL}/{visitante.id}", headers=morador, json=corpo(predio, cpf="12345678900")
    )
    assert resposta.status_code == 422


@pytest.mark.parametrize("encerrada", [False, True], ids=["em_andamento", "ja_saiu"])
def test_editar_depois_de_visita_registrada_e_409(client, session, predio, morador, encerrada):
    visitante = criar_visitante(session, predio, nome="Original")
    registrar_visita(session, predio, visitante, saida_em=datetime.now(UTC) if encerrada else None)
    resposta = client.put(
        f"{URL}/{visitante.id}", headers=morador, json=corpo(predio, nome="Alterado")
    )
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "visitante_ja_utilizado"
    session.refresh(visitante)
    assert visitante.nome == "Original"


def test_editar_cancelado_e_409(client, session, predio, morador):
    visitante = criar_visitante(session, predio, cancelado_em=datetime.now(UTC))
    resposta = client.put(f"{URL}/{visitante.id}", headers=morador, json=corpo(predio))
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "visitante_cancelado"


# --- cancelamento -----------------------------------------------------------------------------


def test_cancelar_marca_o_cadastro(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    resposta = client.post(f"{URL}/{visitante.id}/cancelamento", headers=morador, json={})
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["situacao"] == "cancelado" and dados["cancelado_em"] is not None
    session.refresh(visitante)
    assert visitante.cancelado_em is not None  # nunca apagado


def test_cancelar_duas_vezes_e_409(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    url = f"{URL}/{visitante.id}/cancelamento"
    assert client.post(url, headers=morador, json={}).status_code == 200
    resposta = client.post(url, headers=morador, json={})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "visitante_ja_cancelado"


def test_cancelar_com_visita_em_andamento_e_409(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    registrar_visita(session, predio, visitante)
    resposta = client.post(f"{URL}/{visitante.id}/cancelamento", headers=morador, json={})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "visita_em_andamento"
    session.refresh(visitante)
    assert visitante.cancelado_em is None


def test_cancelar_depois_da_saida_vale(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    registrar_visita(session, predio, visitante, saida_em=datetime.now(UTC))
    resposta = client.post(f"{URL}/{visitante.id}/cancelamento", headers=morador, json={})
    assert resposta.status_code == 200
    assert resposta.json()["ja_utilizado"] is True


def test_cancelamento_ignora_o_corpo(client, session, predio, morador):
    visitante = criar_visitante(session, predio)
    resposta = client.post(
        f"{URL}/{visitante.id}/cancelamento", headers=morador, json={"cancelado_em": "x"}
    )
    # O corpo é ignorado: o contrato manda `{}` e a ação não lê nada dele.
    assert resposta.status_code == 200
