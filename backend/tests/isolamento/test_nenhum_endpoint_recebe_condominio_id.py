"""Prova estrutural da R1: nenhum endpoint declara `condominio_id` como entrada do cliente.

Varre o `openapi.json` (parâmetros de URL, query, cabeçalho e cookie, e campos do corpo). O que
um endpoint lê "por fora" do OpenAPI (ex.: `request.headers`) é coberto pelos testes de
comportamento de `test_isolamento_api.py`, que mandam o campo e conferem que nada muda.
"""

import re
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Header
from pydantic import BaseModel

from app.main import app as app_real
from tests.isolamento.cenario import montar_app

# Pega condominio_id, condominio-id, X-Condominio-Id, condominioId e o cid do token.
PADRAO = re.compile(r"condominio[_-]?id|^cid$", re.IGNORECASE)

# EXATAMENTE duas exceções. Qualquer outra rota que receba um condomínio do cliente é bug.
EXCECOES = [
    # É a rota que COLOCA o cid no token (convenções, seção 2): confirma o vínculo ativo no banco
    # (404 se não houver) antes de emitir o token. Não é rota "do dia a dia".
    ("POST", "/api/v1/auth/selecionar-condominio"),
    # R9: as rotas da plataforma são as únicas com um ID de condomínio na URL, e exigem
    # `administrador_plataforma`. Ainda não existem; o prefixo reserva o espaço.
    ("*", "/api/v1/plataforma/"),
]

METODOS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _excecao(metodo: str, caminho: str) -> bool:
    for metodo_ok, rota in EXCECOES:
        if metodo_ok not in ("*", metodo.upper()):
            continue
        if rota.endswith("/") and caminho.startswith(rota):
            return True
        if caminho == rota:
            return True
    return False


def _propriedades(esquema: Any, componentes: dict[str, Any], vistos: frozenset[str]) -> set[str]:
    """Nomes de todos os campos de um esquema do corpo, seguindo $ref, listas e uniões."""
    if not isinstance(esquema, dict):
        return set()
    nomes: set[str] = set()
    referencia = esquema.get("$ref")
    if isinstance(referencia, str):
        nome = referencia.rsplit("/", 1)[-1]
        if nome not in vistos:  # protege contra esquemas que apontam para si mesmos
            nomes |= _propriedades(componentes.get(nome), componentes, vistos | {nome})
    for campo, subesquema in esquema.get("properties", {}).items():
        nomes.add(campo)
        nomes |= _propriedades(subesquema, componentes, vistos)
    for chave in ("items", "additionalProperties"):
        nomes |= _propriedades(esquema.get(chave), componentes, vistos)
    for chave in ("allOf", "anyOf", "oneOf"):
        for subesquema in esquema.get(chave, []):
            nomes |= _propriedades(subesquema, componentes, vistos)
    return nomes


def entradas_com_condominio(app: FastAPI) -> list[tuple[str, str, str]]:
    """(método, caminho, nome do campo) de toda entrada que parece um condomínio."""
    documento = app.openapi()
    componentes = documento.get("components", {}).get("schemas", {})
    achados = []
    for caminho, operacoes in documento["paths"].items():
        for metodo, operacao in operacoes.items():
            if metodo not in METODOS:
                continue
            nomes = {
                p["name"] for p in operacao.get("parameters", []) + operacoes.get("parameters", [])
            }
            for conteudo in operacao.get("requestBody", {}).get("content", {}).values():
                nomes |= _propriedades(conteudo.get("schema"), componentes, frozenset())
            achados += [(metodo.upper(), caminho, n) for n in sorted(nomes) if PADRAO.search(n)]
    return achados


def sem_excecoes(achados: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    return [(m, c, n) for m, c, n in achados if not _excecao(m, c)]


# --- a regra ---------------------------------------------------------------------------------


def test_a_api_real_so_tem_as_excecoes_conhecidas():
    assert sem_excecoes(entradas_com_condominio(app_real)) == []


def test_a_api_com_as_rotas_de_exemplo_tambem_esta_limpa():
    assert sem_excecoes(entradas_com_condominio(montar_app())) == []


def test_a_lista_de_excecoes_tem_exatamente_duas_entradas():
    assert len(EXCECOES) == 2


def test_a_excecao_do_selecionar_condominio_ainda_e_necessaria():
    # Se um dia esta rota deixar de receber o campo, a exceção sobra e deve ser removida.
    achados = entradas_com_condominio(app_real)
    assert ("POST", "/api/v1/auth/selecionar-condominio", "condominio_id") in achados


# --- o detector funciona (senão a regra acima passaria por não enxergar nada) -----------------


class CorpoComCondominio(BaseModel):
    nome: str
    condominio_id: str


class Aninhado(BaseModel):
    interno: CorpoComCondominio


def _app_com_rota_ruim(adicionar) -> FastAPI:
    rotas = APIRouter()
    adicionar(rotas)
    app = FastAPI()
    app.include_router(rotas, prefix="/api/v1")
    return app


def _rota_na_query(rotas: APIRouter) -> None:
    @rotas.get("/ruim")
    def ruim(condominio_id: str) -> None: ...


def _rota_no_corpo(rotas: APIRouter) -> None:
    @rotas.post("/ruim")
    def ruim(dados: CorpoComCondominio) -> None: ...


def _rota_no_corpo_aninhado(rotas: APIRouter) -> None:
    @rotas.post("/ruim")
    def ruim(dados: list[Aninhado]) -> None: ...


def _rota_no_cabecalho(rotas: APIRouter) -> None:
    @rotas.get("/ruim")
    def ruim(x_condominio_id: str = Header()) -> None: ...


def _rota_na_url(rotas: APIRouter) -> None:
    @rotas.get("/ruim/{condominio_id}")
    def ruim(condominio_id: str) -> None: ...


@pytest.mark.parametrize(
    "adicionar",
    [_rota_na_query, _rota_no_corpo, _rota_no_corpo_aninhado, _rota_no_cabecalho, _rota_na_url],
)
def test_o_detector_pega_condominio_id_em_qualquer_lugar(adicionar):
    app = _app_com_rota_ruim(adicionar)

    assert sem_excecoes(entradas_com_condominio(app)) != []


def test_a_excecao_da_plataforma_so_vale_sob_o_prefixo():
    assert _excecao("GET", "/api/v1/plataforma/condominios/123")
    assert not _excecao("GET", "/api/v1/outra-rota/plataforma/")
    assert not _excecao("GET", "/api/v1/auth/selecionar-condominio")  # método errado
