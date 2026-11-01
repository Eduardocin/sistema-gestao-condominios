"""Isolamento entre condomínios pela API (matriz, seção 11, itens 2 e 3).

Sempre com DOIS condomínios: o usuário do A tenta tudo o que pode contra os dados do B.
"""

import uuid

import pytest
from sqlalchemy import text

from tests.isolamento.cenario import criar_item, montar_app

pytestmark = pytest.mark.postgres

ITENS = "/api/v1/itens"
NAO_ENCONTRADO = {"error": {"code": "not_found", "message": "Recurso não encontrado."}}


def nome_no_banco(session, item_id):
    """Lê direto do banco (SQL puro), sem passar pelo ORM nem pelo repositório."""
    return session.scalar(text("SELECT nome FROM itens_teste WHERE id = :id"), {"id": item_id})


def total_no_banco(session, condominio_id):
    return session.scalar(
        text("SELECT count(*) FROM itens_teste WHERE condominio_id = :cid"), {"cid": condominio_id}
    )


# --- o próprio condomínio funciona (senão todo 404 abaixo seria falso positivo) ------------


def test_usuario_acessa_os_proprios_dados(client, a):
    assert client.get(f"{ITENS}/{a.item.id}", headers=a.cabecalho).json()["nome"] == a.item.nome

    editado = client.patch(f"{ITENS}/{a.item.id}", json={"nome": "Novo"}, headers=a.cabecalho)
    assert editado.status_code == 200
    assert editado.json()["nome"] == "Novo"

    assert client.delete(f"{ITENS}/{a.item.id}", headers=a.cabecalho).status_code == 204
    assert client.get(f"{ITENS}/{a.item.id}", headers=a.cabecalho).status_code == 404


def test_criar_grava_o_condominio_do_contexto(client, session, a, b):
    resposta = client.post(ITENS, json={"nome": "Criado pelo A"}, headers=a.cabecalho)

    assert resposta.status_code == 201
    dono = session.scalar(
        text("SELECT condominio_id FROM itens_teste WHERE id = :id"), {"id": resposta.json()["id"]}
    )
    assert dono == a.condominio.id


# --- A contra B ----------------------------------------------------------------------------


def test_ler_item_do_outro_condominio_e_igual_a_item_inexistente(client, a, b):
    do_outro = client.get(f"{ITENS}/{b.item.id}", headers=a.cabecalho)
    inexistente = client.get(f"{ITENS}/{uuid.uuid4()}", headers=a.cabecalho)

    assert do_outro.status_code == inexistente.status_code == 404
    # Mesmo corpo, palavra por palavra: nada denuncia que o item existe em outro prédio (R4).
    assert do_outro.json() == inexistente.json() == NAO_ENCONTRADO
    assert str(b.item.id) not in do_outro.text
    assert b.condominio.nome not in do_outro.text


def test_listar_devolve_so_o_proprio_condominio(client, session, a, b):
    criar_item(session, a.condominio, "Segundo do A")
    criar_item(session, b.condominio, "Segundo do B")

    resposta = client.get(ITENS, headers=a.cabecalho)

    assert resposta.status_code == 200
    assert {i["nome"] for i in resposta.json()} == {a.item.nome, "Segundo do A"}
    assert str(b.item.id) not in resposta.text


def test_editar_item_do_outro_condominio_responde_404_e_nao_altera(client, session, a, b):
    resposta = client.patch(f"{ITENS}/{b.item.id}", json={"nome": "Invadido"}, headers=a.cabecalho)

    assert resposta.status_code == 404
    assert resposta.json() == NAO_ENCONTRADO
    assert nome_no_banco(session, b.item.id) == b.item.nome


def test_apagar_item_do_outro_condominio_responde_404_e_nao_apaga(client, session, a, b):
    resposta = client.delete(f"{ITENS}/{b.item.id}", headers=a.cabecalho)

    assert resposta.status_code == 404
    assert resposta.json() == NAO_ENCONTRADO
    assert nome_no_banco(session, b.item.id) == b.item.nome


def test_o_isolamento_vale_nos_dois_sentidos(client, a, b):
    assert client.get(f"{ITENS}/{a.item.id}", headers=b.cabecalho).status_code == 404
    assert client.get(f"{ITENS}/{b.item.id}", headers=b.cabecalho).status_code == 200


# --- entrada do cliente ignorada (R1) --------------------------------------------------------


@pytest.mark.parametrize("alvo", ["proprio", "outro"])
def test_condominio_id_no_corpo_e_rejeitado_e_nada_e_criado(client, session, a, b, alvo):
    condominio_id = (a if alvo == "proprio" else b).condominio.id

    resposta = client.post(
        ITENS, json={"nome": "Com id", "condominio_id": str(condominio_id)}, headers=a.cabecalho
    )

    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"
    assert total_no_banco(session, a.condominio.id) == 1
    assert total_no_banco(session, b.condominio.id) == 1


def test_condominio_id_no_corpo_tambem_e_rejeitado_na_edicao(client, session, a, b):
    resposta = client.patch(
        f"{ITENS}/{a.item.id}",
        json={"nome": "Mudando de dono", "condominio_id": str(b.condominio.id)},
        headers=a.cabecalho,
    )

    assert resposta.status_code == 422
    assert nome_no_banco(session, a.item.id) == a.item.nome
    assert total_no_banco(session, b.condominio.id) == 1


def test_condominio_id_na_query_nao_muda_o_resultado(client, a, b):
    sem = client.get(ITENS, headers=a.cabecalho)
    com = client.get(ITENS, params={"condominio_id": str(b.condominio.id)}, headers=a.cabecalho)
    do_outro = client.get(
        f"{ITENS}/{b.item.id}", params={"condominio_id": str(b.condominio.id)}, headers=a.cabecalho
    )

    assert com.status_code == 200
    assert com.json() == sem.json()
    assert do_outro.status_code == 404


def test_condominio_id_na_query_do_post_nao_muda_o_dono(client, session, a, b):
    resposta = client.post(
        ITENS,
        json={"nome": "Query esperta"},
        params={"condominio_id": str(b.condominio.id)},
        headers=a.cabecalho,
    )

    assert resposta.status_code == 201
    assert total_no_banco(session, a.condominio.id) == 2
    assert total_no_banco(session, b.condominio.id) == 1


@pytest.mark.parametrize("cabecalho", ["X-Condominio-Id", "X-Cid", "Condominio-Id", "X-Tenant-Id"])
def test_condominio_id_em_cabecalho_nao_muda_o_resultado(client, a, b, cabecalho):
    extra = {**a.cabecalho, cabecalho: str(b.condominio.id)}

    lista = client.get(ITENS, headers=extra)
    do_outro = client.get(f"{ITENS}/{b.item.id}", headers=extra)
    contexto = client.get("/api/v1/diagnostico/contexto", headers=extra)

    assert [i["id"] for i in lista.json()] == [str(a.item.id)]
    assert do_outro.status_code == 404
    assert contexto.json()["condominio_id"] == str(a.condominio.id)


def test_a_api_real_nao_ganhou_rotas_de_teste():
    # A app de produção (módulo app.main) não pode enxergar o módulo de exemplo.
    from app.main import app

    caminhos = set(app.openapi()["paths"])
    assert not any(c.startswith("/api/v1/itens") for c in caminhos)
    assert "/api/v1/diagnostico/contexto" not in caminhos
    # E a app de teste enxerga: a distinção existe de verdade.
    assert "/api/v1/itens" in montar_app().openapi()["paths"]
