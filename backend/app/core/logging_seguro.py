"""Logs sem dado pessoal nem segredo (US-1007, TASK-54).

O filtro redige a mensagem já formatada e o traceback. É uma rede de proteção: o código não
deve passar senha, token, documento ou e-mail para o log, mas exceções de bibliotecas (driver
do banco, validação) podem trazer esses valores na mensagem.
"""

import logging
import re
from collections.abc import Iterable

REDIGIDO = "[redigido]"

_CHAVES = r"(?:senha|password|token|secret|authorization|cookie|api_key|access_key)"
_SEM_LETRA = r"(?<![0-9A-Za-z])"  # borda: não pega dígitos no meio de UUIDs ou hashes
_FIM = r"(?![0-9A-Za-z])"

# A ordem importa: primeiro o que é mais específico (JWT, Bearer, chave=valor).
_REGRAS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]*"), "[jwt]"),
    (re.compile(r"(?i)\bbearer\s+[\w\-.~+/=]+"), f"Bearer {REDIGIDO}"),
    # senha=abc, "token": "x", password: y, api_key='z' (inclusive nomes compostos como
    # refresh_token ou STORAGE_SECRET_KEY).
    (
        re.compile(
            r"(?i)([\"']?[\w-]*" + _CHAVES + r"[\w-]*[\"']?\s*[:=]\s*)"
            r"(?:\"[^\"]*\"|\'[^\']*\'|[^,\n;&}\]]*?)"
            r"(?=\s+[A-Za-z_][\w-]*\s*[:=]|\s*[,;&}\]]|$)"
        ),
        r"\1" + REDIGIDO,
    ),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    # CNPJ antes do CPF: 14 dígitos contêm 11.
    (
        re.compile(_SEM_LETRA + r"(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})" + _FIM),
        "[documento]",
    ),
    (re.compile(_SEM_LETRA + r"(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})" + _FIM), "[documento]"),
]


def redigir(texto: str) -> str:
    for padrao, troca in _REGRAS:
        texto = padrao.sub(troca, texto)
    return texto


class FiltroDadosPessoais(logging.Filter):
    """Redige a mensagem formatada, o traceback e o stack. Nunca descarta o registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("uvicorn.access"):
            # O AccessFormatter do uvicorn desempacota `args`: redigimos cada argumento texto
            # sem juntar tudo na mensagem.
            if isinstance(record.args, tuple):
                record.args = tuple(
                    redigir(arg) if isinstance(arg, str) else arg for arg in record.args
                )
        else:
            try:
                mensagem = record.getMessage()
            except Exception:  # args que não batem com a mensagem: o logging já trataria
                mensagem = str(record.msg)
            record.msg = redigir(mensagem)
            record.args = ()
        if record.exc_info and not record.exc_text:
            # Formata agora para poder redigir; o Formatter reaproveita `exc_text`.
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redigir(record.exc_text)
        if record.stack_info:
            record.stack_info = redigir(record.stack_info)
        return True


class FiltroAcessoSemQuery(logging.Filter):
    """No log de acesso do uvicorn, tira a query string do caminho (pode trazer busca por
    e-mail ou CPF). Mantém método, caminho e status."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Formato do uvicorn: (cliente, método, caminho completo, versão HTTP, status).
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str):
                args[2] = args[2].split("?", 1)[0]
            record.args = tuple(args)
        return True


LOGGERS_PROTEGIDOS = ("", "uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy")


def _instalar(alvo: logging.Logger | logging.Handler, filtros: Iterable[logging.Filter]) -> None:
    for filtro in filtros:
        if not any(type(f) is type(filtro) for f in alvo.filters):
            alvo.addFilter(filtro)


def instalar_filtros_de_log(nomes: Iterable[str] = LOGGERS_PROTEGIDOS) -> None:
    """Instala os filtros nos loggers e nos handlers deles. Idempotente.

    No logger vale para o que é registrado nele mesmo; no handler vale também para o que chega
    por propagação dos loggers filhos (ex.: `sqlalchemy.engine.Engine` -> raiz).
    """
    for nome in nomes:
        logger = logging.getLogger(nome)
        # A ordem importa no acesso: primeiro tira a query, depois redige o que sobrou.
        filtros: list[logging.Filter] = (
            [FiltroAcessoSemQuery(), FiltroDadosPessoais()]
            if nome == "uvicorn.access"
            else [FiltroDadosPessoais()]
        )
        _instalar(logger, filtros)
        for handler in logger.handlers:
            _instalar(handler, filtros)
