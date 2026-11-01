"""O exemplo do guia (docs/architecture.md) é o mesmo código que os testes exercitam.

Os dois lados têm marcadores (`# inicio-exemplo`/`# fim-exemplo` no código e
`<!-- inicio-exemplo -->`/`<!-- fim-exemplo -->` no guia). Comparamos o conteúdo entre eles
ignorando diferenças de espaço em branco, para o teste não quebrar por causa de indentação ou
linhas vazias, só quando o código muda de verdade.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
GUIA = RAIZ / "docs" / "architecture.md"
CODIGO = Path(__file__).resolve().parent / "app_exemplo.py"


def entre_marcadores(texto: str, inicio: str, fim: str) -> str:
    achado = re.search(rf"{re.escape(inicio)}\n(.*?)\n[ \t]*{re.escape(fim)}", texto, re.DOTALL)
    assert achado, f"marcadores {inicio!r} e {fim!r} não encontrados"
    return achado.group(1)


def sem_espacos(texto: str) -> str:
    return " ".join(texto.split())


def sem_cerca_de_codigo(texto: str) -> str:
    return "\n".join(x for x in texto.splitlines() if not x.strip().startswith("```"))


def exemplo_do_codigo() -> str:
    return entre_marcadores(CODIGO.read_text(encoding="utf-8"), "# inicio-exemplo", "# fim-exemplo")


def exemplo_do_guia() -> str:
    bloco = entre_marcadores(
        GUIA.read_text(encoding="utf-8"), "<!-- inicio-exemplo -->", "<!-- fim-exemplo -->"
    )
    return sem_cerca_de_codigo(bloco)


def test_guia_e_codigo_de_teste_tem_o_mesmo_exemplo():
    assert sem_espacos(exemplo_do_guia()) == sem_espacos(exemplo_do_codigo()), (
        "O exemplo de docs/architecture.md difere de tests/isolamento/app_exemplo.py. "
        "Atualize os dois juntos."
    )


def test_a_comparacao_ignora_so_espacos():
    assert sem_espacos("a  =  1\n\n\n  b = 2") == sem_espacos("a = 1\nb = 2")
    assert sem_espacos("a = 1") != sem_espacos("a = 2")


@pytest.mark.parametrize("trecho", ["RepositorioDoCondominio", "ContextoDep", 'extra="forbid"'])
def test_o_exemplo_mostra_as_pecas_do_padrao(trecho):
    assert trecho in exemplo_do_guia()
