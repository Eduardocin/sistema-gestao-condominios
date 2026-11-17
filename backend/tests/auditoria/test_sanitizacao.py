import copy
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auditoria.sanitizacao import CAMPOS_SECRETOS, OMITIDO, sanitizar


@pytest.mark.parametrize("campo", sorted(CAMPOS_SECRETOS))
def test_remove_cada_segredo_no_topo_e_em_estruturas_aninhadas(campo):
    original = {campo: "segredo", "alteracoes": [{campo: "segredo", "ativo": True}]}
    copia = copy.deepcopy(original)
    assert sanitizar(original) == {"alteracoes": [{"ativo": True}]}
    assert original == copia


@pytest.mark.parametrize(
    "campo",
    [
        "AccessToken",
        "SENHA",
        "token-recuperacao",
        "novaSenha",
        "Authorization",
        "apiKey",
        "chaveAcesso",
        "smtp_password",
    ],
)
def test_normaliza_variacoes_de_nomes_secretos(campo):
    assert sanitizar({campo: "segredo"}) == {}


def test_documentos_sao_mascarados_inclusive_em_listas():
    resultado = sanitizar(
        {
            "pessoas": [
                {"documento": "52998224725"},
                {"CPF": "529.982.247-25"},
                {"cnpj": "11222333000181"},
                {"documento": {"senha": "secreto"}},
            ]
        }
    )
    assert resultado == {
        "pessoas": [
            {"documento": "***.982.247-**"},
            {"CPF": "***.982.247-**"},
            {"cnpj": "**.***.333/0001-**"},
            {"documento": OMITIDO},
        ]
    }


def test_nao_serializa_repr_de_objetos_e_aceita_valores_de_dominio():
    id_ = uuid.uuid4()
    instante = datetime(2026, 11, 17, tzinfo=UTC)
    assert sanitizar(
        {"id": id_, "data": instante, "objeto": SecretStr("segredo"), "valor": float("inf")}
    ) == {
        "id": str(id_),
        "data": instante.isoformat(),
        "objeto": OMITIDO,
        "valor": None,
    }
    dados = {}
    dados["ciclo"] = dados
    assert OMITIDO in str(sanitizar(dados))


@pytest.mark.parametrize(
    "host,esperado",
    [("203.0.113.1", "203.0.113.1"), ("2001:db8::1", "2001:db8::1"), ("testclient", None)],
)
def test_ip_vem_da_conexao_e_ignora_cabecalhos_arbitrarios(host, esperado):
    request = Request(
        {
            "type": "http",
            "client": (host, 1234),
            "headers": [(b"x-forwarded-for", b"198.51.100.10")],
        }
    )
    assert ip_do_cliente(request) == esperado


def test_constante_contem_todos_os_campos_exigidos_pelo_contrato():
    assert {"senha", "senha_hash", "token", "token_hash", "codigo"} <= CAMPOS_SECRETOS
    assert sanitizar({"JWTSecretKey": "segredo"}) == {}


@pytest.mark.parametrize("documento", ["***.982.247-**", "**.***.333/0001-**"])
def test_sanitizacao_de_documento_e_idempotente_para_consulta(documento):
    dados = {"pessoa": {"documento": documento}}
    assert sanitizar(sanitizar(dados)) == dados
