"""Sanitização recursiva, sem alterar o objeto recebido nem serializar objetos por repr."""

import math
import re
import uuid
from collections.abc import Mapping
from datetime import date, datetime, time
from enum import Enum
from typing import Any
from unicodedata import normalize

CAMPOS_SECRETOS = frozenset(
    {
        "senha",
        "senha_hash",
        "senha_atual",
        "senha_nova",
        "password",
        "password_hash",
        "token",
        "token_hash",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set_cookie",
        "codigo",
        "chave",
        "chave_acesso",
        "secret",
        "secret_key",
        "jwt_secret_key",
        "api_key",
        "access_key",
        "storage_access_key",
        "storage_secret_key",
        "private_key",
        "database_url",
        "connection_string",
        "credenciais",
    }
)
CAMPOS_DOCUMENTO = frozenset({"documento", "cpf", "cnpj"})
OMITIDO = "[omitido]"


def _nome(campo: str) -> str:
    campo = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", campo)
    campo = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", campo)
    return re.sub(
        r"[^a-z0-9]+", "_", normalize("NFKD", campo).encode("ascii", "ignore").decode().lower()
    ).strip("_")


def _documento(valor: Any) -> str:
    if not isinstance(valor, (str, int)) or isinstance(valor, bool):
        return OMITIDO
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    if len(digitos) == 14:
        return f"**.***.{digitos[5:8]}/{digitos[8:12]}-**"
    return OMITIDO


def _sanitizar(valor: Any, profundidade: int = 0) -> Any:
    if profundidade > 20:
        return OMITIDO
    if isinstance(valor, Mapping):
        resultado = {}
        for chave, item in valor.items():
            if not isinstance(chave, str):
                continue
            nome = _nome(chave)
            if (
                nome in CAMPOS_SECRETOS
                or nome.startswith(("senha_", "password_", "token_", "codigo_"))
                or any(
                    nome.endswith(f"_{sufixo}")
                    for sufixo in (
                        "senha",
                        "senha_hash",
                        "password",
                        "token",
                        "token_hash",
                        "secret",
                        "secret_key",
                    )
                )
            ):
                continue
            resultado[chave] = (
                _documento(item) if nome in CAMPOS_DOCUMENTO else _sanitizar(item, profundidade + 1)
            )
        return resultado
    if isinstance(valor, (list, tuple)):
        return [_sanitizar(item, profundidade + 1) for item in valor]
    if isinstance(valor, Enum):
        return _sanitizar(valor.value, profundidade + 1)
    if isinstance(valor, (uuid.UUID, datetime, date, time)):
        return str(valor) if isinstance(valor, uuid.UUID) else valor.isoformat()
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return OMITIDO


def sanitizar(dados: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return _sanitizar(dados) if dados is not None else None
