"""Rede de proteção da R3: consulta ao banco só em `repository.py`.

Versão propositalmente simples: lê o código (AST) de todo `service.py` e `router.py` dos módulos
e falha se achar `select(...)` ou uma chamada `session.get/execute/scalar/scalars/query(...)`.
Quem precisa de dados chama o repository, que já filtra por condomínio. O que isto NÃO pega:
SQL escrito de outro jeito (ex.: `text(...)`) ou o filtro esquecido DENTRO de um repository
próprio; para isso valem a revisão de PR e os testes de isolamento de cada módulo.
"""

import ast
from pathlib import Path

import pytest

MODULOS = Path(__file__).resolve().parents[2] / "app" / "modules"
METODOS_DE_SESSAO = {"get", "execute", "scalar", "scalars", "query"}


def violacoes(codigo: str) -> list[str]:
    achados = []
    for no in ast.walk(ast.parse(codigo)):
        if not isinstance(no, ast.Call):
            continue
        funcao = no.func
        if isinstance(funcao, ast.Name) and funcao.id == "select":
            achados.append(f"linha {no.lineno}: select(...)")
        elif (
            isinstance(funcao, ast.Attribute)
            and funcao.attr in METODOS_DE_SESSAO
            and ast.unparse(funcao.value).endswith("session")
        ):
            achados.append(f"linha {no.lineno}: {ast.unparse(funcao)}(...)")
    return achados


def arquivos_de_camada_http_e_regra() -> list[Path]:
    return sorted([*MODULOS.glob("**/service.py"), *MODULOS.glob("**/router.py")])


def test_services_e_routers_nao_consultam_o_banco():
    arquivos = arquivos_de_camada_http_e_regra()
    assert arquivos, "nenhum service.py/router.py encontrado: o caminho do teste está errado?"

    problemas = {
        str(a.relative_to(MODULOS)): v
        for a in arquivos
        if (v := violacoes(a.read_text(encoding="utf-8")))
    }

    assert problemas == {}, (
        "Consulta ao banco fora de repository.py. Mova para o repository do módulo "
        "(que aplica o filtro de condomínio). Ocorrências: " + str(problemas)
    )


# --- o detector funciona -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        "x = select(Item)",
        "item = session.get(Item, item_id)",
        "linhas = session.execute(consulta)",
        "item = session.scalar(consulta)",
        "itens = self.session.scalars(consulta)",
        "itens = session.query(Item)",
    ],
)
def test_o_detector_pega_consultas_diretas(codigo):
    assert violacoes(codigo) != []


@pytest.mark.parametrize(
    "codigo",
    [
        "session.commit()",
        "session.add(item)",
        "item = repositorio.obter(item_id)",
        "texto = 'session.get(Item, 1) e select(Item)'  # só texto",
        "# select(Item)",
    ],
)
def test_o_detector_nao_acusa_codigo_legitimo(codigo):
    assert violacoes(codigo) == []
