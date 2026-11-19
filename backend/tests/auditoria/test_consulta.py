import base64
import json
import uuid
from datetime import UTC, datetime

import pytest

from app.modules.auditoria.models import RegistroAuditoria
from tests.isolamento.cenario import cabecalho, token_de

pytestmark = pytest.mark.postgres
ROTA = "/api/v1/plataforma/auditoria"


def ids(resposta):
    assert resposta.status_code == 200, resposta.text
    return [item["id"] for item in resposta.json()["items"]]


def test_adm_consulta_e_recebe_dados_pertinentes_sanitizados(consulta):
    resposta = consulta.consultar()
    assert ids(resposta) == [evento.id for evento in reversed(consulta.eventos)]
    corpo = resposta.json()
    assert corpo["page_size"] == 20 and corpo["next_cursor"] is None
    evento = corpo["items"][-1]
    assert evento["usuario"] == {
        "id": str(consulta.cenario.a.administracao.id),
        "nome": consulta.cenario.a.administracao.nome,
    }
    assert evento["condominio"] == {
        "id": str(consulta.cenario.a.condominio.id),
        "nome": consulta.cenario.a.condominio.nome,
    }
    assert evento["responsavel_nome"] == "Síndica"
    assert evento["recurso_id"] == str(consulta.cenario.a.unidade_101.id)
    assert evento["ip"] == "203.0.113.9"
    assert evento["antes"] == {"status": "pendente"}
    assert evento["depois"] == {"status": "ativo", "pessoa": {"documento": "***.982.247-**"}}
    assert "SEGREDO_LEGADO" not in resposta.text and "TOKEN_LEGADO" not in resposta.text
    assert "email" not in evento["usuario"]
    # Consultar não altera nem tenta corrigir registros legados imutáveis no banco.
    consulta.session.refresh(consulta.eventos[0])
    assert consulta.eventos[0].depois["senha"] == "SEGREDO_LEGADO"


@pytest.mark.parametrize("perfil", ["morador", "administracao", "funcionario"])
def test_outros_perfis_recebem_403_antes_de_validar_cursor(consulta, perfil):
    resposta = consulta.client.get(
        ROTA, params={"cursor": "invalido"}, headers=consulta.cenario.a.cabecalho_de(perfil)
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


def test_sem_token_recebe_401(consulta):
    assert consulta.client.get(ROTA).status_code == 401


def test_claim_plataforma_nao_substitui_flag_no_banco(consulta):
    token = token_de(consulta.cenario.a.morador, None, perfil="plataforma")
    assert consulta.client.get(ROTA, headers=cabecalho(token)).status_code == 403


@pytest.mark.parametrize(
    "campo,indice", [("condominio_id", 0), ("usuario_id", 0), ("recurso_id", 0)]
)
def test_filtros_por_identificador(consulta, campo, indice):
    valor = getattr(consulta.eventos[indice], campo)
    esperados = [e.id for e in reversed(consulta.eventos) if getattr(e, campo) == valor]
    assert ids(consulta.consultar(**{campo: str(valor)})) == esperados


def test_condominio_b_e_global_nao_sao_excluidos_da_consulta_adm(consulta):
    assert ids(consulta.consultar(condominio_id=str(consulta.cenario.b.condominio.id))) == [
        consulta.eventos[2].id
    ]
    resposta = consulta.consultar(acao="seguranca.")
    assert ids(resposta) == [consulta.eventos[4].id, consulta.eventos[3].id]
    assert all(e["condominio"] is None for e in resposta.json()["items"])
    assert resposta.json()["items"][1]["usuario"] is None


@pytest.mark.parametrize(
    "acao,indices",
    [
        ("condominio.aprovar", [0]),
        ("condominio.", [1, 0]),
        ("permissao_aba.", [2]),
        ("reserva.cancelar", []),
    ],
)
def test_acao_exata_e_prefixo_literal(consulta, acao, indices):
    assert ids(consulta.consultar(acao=acao)) == [consulta.eventos[i].id for i in indices]


@pytest.mark.parametrize(
    "params,indices",
    [
        ({"de": "2026-11-16", "ate": "2026-11-16"}, [2, 1]),
        ({"de": "2026-11-17"}, [4, 3]),
        ({"ate": "2026-11-15"}, [0]),
    ],
)
def test_periodo_inclusivo_no_fuso_do_condominio(consulta, params, indices):
    assert ids(consulta.consultar(**params)) == [consulta.eventos[i].id for i in indices]


def test_combina_todos_os_filtros(consulta):
    resposta = consulta.consultar(
        condominio_id=str(consulta.cenario.a.condominio.id),
        usuario_id=str(consulta.cenario.a.morador.id),
        de="2026-11-16",
        ate="2026-11-16",
        acao="condominio.rejeitar",
        recurso_id=str(consulta.cenario.a.unidade_101.id),
    )
    assert ids(resposta) == [consulta.eventos[1].id]


@pytest.mark.parametrize("campo", ["condominio_id", "usuario_id", "recurso_id"])
def test_identificador_inexistente_retorna_lista_vazia(consulta, campo):
    resposta = consulta.consultar(**{campo: str(uuid.uuid4())})
    assert ids(resposta) == [] and resposta.json()["next_cursor"] is None


def test_filtro_de_tipo_de_recurso_inexistente(consulta):
    assert ids(consulta.consultar(recurso_tipo="recurso_inexistente")) == []


@pytest.mark.parametrize("page_size", [1, 2, 3, 100])
def test_cursor_sem_repeticao_ou_perda_inclusive_no_empate(consulta, page_size):
    encontrados = []
    cursor = None
    for _ in range(10):
        params = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        resposta = consulta.consultar(**params)
        encontrados.extend(ids(resposta))
        cursor = resposta.json()["next_cursor"]
        if cursor is None:
            break
    assert encontrados == [e.id for e in reversed(consulta.eventos)]
    assert len(encontrados) == len(set(encontrados))
    assert cursor is None


def test_insercao_mais_recente_nao_desloca_paginas_ja_iniciadas(consulta):
    primeira = consulta.consultar(page_size=2)
    novo = RegistroAuditoria(
        acao="reserva.criar",
        recurso_tipo=consulta.tipo,
        criado_em=datetime(2026, 12, 1, tzinfo=UTC),
    )
    consulta.session.add(novo)
    consulta.session.flush()
    segunda = consulta.consultar(page_size=100, cursor=primeira.json()["next_cursor"])
    assert ids(primeira) + ids(segunda) == [e.id for e in reversed(consulta.eventos)]
    assert novo.id not in ids(segunda)


def codificar(valor):
    return base64.urlsafe_b64encode(json.dumps(valor).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "nao-e-json",
        "%%%",
        "a",
        "a" * 513,
        codificar({"criado_em": "2026-11-17", "id": 1}),
        codificar({"criado_em": "2026-11-17T00:00:00Z", "id": True}),
        codificar({"criado_em": "2026-11-17T00:00:00Z", "id": "1"}),
        codificar({"criado_em": "2026-11-17T00:00:00Z", "id": 0}),
        codificar({"criado_em": "2026-11-17T00:00:00Z", "id": 2**63}),
        codificar({"criado_em": "2026-11-17T00:00:00Z", "id": 1, "extra": "rejeitar"}),
        codificar(["2026-11-17T00:00:00Z", 1]),
    ],
)
def test_cursor_invalido_retorna_422_com_envelope_padrao(consulta, cursor):
    resposta = consulta.consultar(cursor=cursor)
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "params",
    [
        {"de": "2026-11-18", "ate": "2026-11-17"},
        {"de": "data_invalida"},
        {"ate": "9999-12-31"},
        {"page_size": 0},
        {"page_size": 101},
        {"acao": "reserva.%"},
        {"acao": "sem_grupo"},
        {"condominio_id": "invalido"},
        {"recurso_tipo": ""},
        {"usuario_id": "invalido"},
        {"campo_extra": "nao_aceitar"},
    ],
)
def test_filtros_invalidos(consulta, params):
    resposta = consulta.consultar(**params)
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_nao_existe_endpoint_de_escrita(consulta, metodo):
    assert getattr(consulta.client, metodo)(ROTA, headers=consulta.headers).status_code == 405
    assert (
        getattr(consulta.client, metodo)(
            f"{ROTA}/{consulta.eventos[0].id}", headers=consulta.headers
        ).status_code
        == 404
    )
    assert len(ids(consulta.consultar())) == 5


def test_openapi_expoe_apenas_get_e_cursor(consulta):
    contrato = consulta.client.get("/openapi.json").json()
    assert set(contrato["paths"][ROTA]) == {"get"}
    parametros = {p["name"] for p in contrato["paths"][ROTA]["get"]["parameters"]}
    assert {"cursor", "page_size", "condominio_id", "usuario_id", "de", "ate", "acao"} <= parametros
    assert "page" not in parametros


def test_data_tem_precedencia_sobre_ordem_de_insercao(consulta):
    inserido_depois = RegistroAuditoria(
        acao="reserva.criar",
        recurso_tipo=consulta.tipo,
        criado_em=datetime(2026, 11, 16, 3, 30, tzinfo=UTC),
    )
    consulta.session.add(inserido_depois)
    consulta.session.flush()
    assert inserido_depois.id > consulta.eventos[-1].id
    assert ids(consulta.consultar()) == [
        consulta.eventos[4].id,
        consulta.eventos[3].id,
        consulta.eventos[2].id,
        inserido_depois.id,
        consulta.eventos[1].id,
        consulta.eventos[0].id,
    ]


def test_sublinhado_no_prefixo_de_acao_e_literal(consulta):
    consulta.session.add(
        RegistroAuditoria(
            acao="permissaoxaba.alterar",
            recurso_tipo=consulta.tipo,
            criado_em=datetime(2026, 12, 1, tzinfo=UTC),
        )
    )
    consulta.session.flush()
    assert ids(consulta.consultar(acao="permissao_aba.")) == [consulta.eventos[2].id]
