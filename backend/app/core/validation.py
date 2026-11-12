"""Normalização e validação compartilhadas pelos formulários de cadastro."""

import re


def normalizar_email(valor: str) -> str:
    valor = valor.strip().lower()
    if len(valor) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",
        valor,
    ):
        raise ValueError("Informe um e-mail válido.")
    return valor


def validar_telefone(valor: str) -> str:
    if not re.fullmatch(r"[0-9]{10,11}", valor):
        raise ValueError("Informe telefone com DDD, com 10 ou 11 dígitos.")
    return valor


def validar_documento(valor: str) -> str:
    if not re.fullmatch(r"[0-9]{11}|[0-9]{14}", valor) or len(set(valor)) == 1:
        raise ValueError("Informe CPF ou CNPJ válido, somente com dígitos.")
    digitos = [int(d) for d in valor]
    pesos = (
        [list(range(10, 1, -1)), list(range(11, 1, -1))]
        if len(valor) == 11
        else [[5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]]
    )
    base = digitos[:-2]
    for indice, peso in enumerate(pesos):
        resto = sum(d * p for d, p in zip(base, peso, strict=True)) % 11
        esperado = 0 if resto < 2 else 11 - resto
        if digitos[-2 + indice] != esperado:
            raise ValueError("Informe CPF ou CNPJ válido.")
        base.append(esperado)
    return valor
