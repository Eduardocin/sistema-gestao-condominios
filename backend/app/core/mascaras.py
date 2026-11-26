"""Máscaras de dado pessoal para respostas e trilhas (US-1007, TASK-54).

O banco guarda CPF, CNPJ e telefone só com dígitos (modelo de dados, seção 1); a máscara é
aplicada na saída, para quem não precisa do dado completo. Entrada `None` devolve `None`.
"""

import re

# Formatos já mascarados. A auditoria aceita reprocessar um valor mascarado sem estragá-lo.
DOCUMENTO_MASCARADO = re.compile(r"\*{3}\.\d{3}\.\d{3}-\*{2}|\*{2}\.\*{3}\.\d{3}/\d{4}-\*{2}")


def mascarar_documento(valor: str | None) -> str | None:
    """CPF vira `***.456.789-**`; CNPJ vira `**.***.123/0001-**`.

    Aceita o valor com ou sem pontuação. Valor já mascarado volta igual. Qualquer outra coisa
    (tamanho errado) vira só asteriscos, para nunca devolver o texto original.
    """
    if valor is None:
        return None
    if DOCUMENTO_MASCARADO.fullmatch(valor):
        return valor
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    if len(digitos) == 14:
        return f"**.***.{digitos[5:8]}/{digitos[8:12]}-**"
    return "*" * len(valor)


def mascarar_telefone(valor: str | None) -> str | None:
    """Mantém só os 4 últimos dígitos e o tamanho: `11987654321` vira `*******4321`."""
    if valor is None:
        return None
    if len(valor) <= 4:
        return "*" * len(valor)
    return "*" * (len(valor) - 4) + valor[-4:]


def mascarar_email(valor: str | None) -> str | None:
    """`ana@exemplo.com` vira `a***@exemplo.com`. Sem `@` válido, só asteriscos."""
    if valor is None:
        return None
    usuario, arroba, dominio = valor.rpartition("@")
    if not arroba or not usuario or not dominio:
        return "***"
    return f"{usuario[0]}***@{dominio}"
