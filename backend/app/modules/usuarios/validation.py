import re


def validar_email(email: str) -> str:
    normalizado = email.strip().lower()
    if len(normalizado) > 254 or not re.fullmatch(
        r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
        r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+",
        normalizado,
        re.IGNORECASE,
    ):
        raise ValueError("Informe um e-mail válido.")
    return normalizado


def normalizar_cpf(cpf: str) -> str:
    if not re.fullmatch(r"(?:\d{11}|\d{3}\.\d{3}\.\d{3}-\d{2})", cpf.strip()):
        raise ValueError("Informe um CPF válido.")
    digitos = re.sub(r"\D", "", cpf)
    if len(set(digitos)) == 1:
        raise ValueError("Informe um CPF válido.")

    numeros = [int(digito) for digito in digitos]
    primeiro = (
        sum(numero * peso for numero, peso in zip(numeros[:9], range(10, 1, -1), strict=True)) * 10
    ) % 11
    primeiro = 0 if primeiro == 10 else primeiro
    segundo = (
        sum(numero * peso for numero, peso in zip(numeros[:10], range(11, 1, -1), strict=True)) * 10
    ) % 11
    segundo = 0 if segundo == 10 else segundo
    if numeros[9:] != [primeiro, segundo]:
        raise ValueError("Informe um CPF válido.")
    return digitos


def validar_senha_forte(senha: str) -> str:
    if (
        len(senha) < 12
        or not re.search(r"[a-z]", senha)
        or not re.search(r"[A-Z]", senha)
        or not re.search(r"\d", senha)
        or not re.search(r"[^A-Za-z0-9]", senha)
    ):
        raise ValueError(
            "A senha deve ter ao menos 12 caracteres, com maiúscula, minúscula, número e símbolo."
        )
    return senha
