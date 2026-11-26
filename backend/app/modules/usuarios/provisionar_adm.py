"""Cria a conta do ADM da plataforma (README: "primeiro ADM").

O cadastro público nunca concede esse papel, então a primeira conta só nasce aqui, por quem tem
acesso ao servidor. Uso, de dentro do container da API:

    python -m app.modules.usuarios.provisionar_adm --nome "Fulano" --email fulano@exemplo.com

A senha vem de `ADM_SENHA` ou de um prompt sem eco. Nunca de argumento de linha de comando, que
ficaria no histórico do shell. E-mail já cadastrado é recusado: este comando não promove contas
existentes, para não dar poder de plataforma a quem se cadastrou como morador ou Administração.
"""

import argparse
import getpass
import os
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.validation import normalizar_email
from app.db.session import get_session_factory
from app.modules.auth.security import hash_senha
from app.modules.contas.schemas import Senha, conferir_senha
from app.modules.usuarios.models import Usuario


class ErroDeProvisionamento(Exception):
    """Entrada inválida ou conta já existente; a mensagem é segura para mostrar."""


def provisionar(session: Session, *, nome: str, email: str, senha: str) -> Usuario:
    nome = " ".join(nome.split())
    if not 3 <= len(nome) <= 150:
        raise ErroDeProvisionamento("Informe um nome de 3 a 150 caracteres.")
    try:
        email = normalizar_email(email)
    except ValueError:
        raise ErroDeProvisionamento("Informe um e-mail válido.") from None
    try:
        TypeAdapter(Senha).validate_python(senha)
        conferir_senha(senha, email)
    except (ValueError, ValidationError):
        raise ErroDeProvisionamento(
            "Senha inválida: use 8 a 128 caracteres, com letra e número, diferente do e-mail."
        ) from None
    if session.scalar(select(Usuario.id).where(Usuario.email == email)) is not None:
        raise ErroDeProvisionamento(
            "Já existe uma conta com esse e-mail. Este comando só cria contas novas."
        )
    usuario = Usuario(
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        administrador_plataforma=True,
    )
    session.add(usuario)
    session.commit()
    return usuario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria a conta do ADM da plataforma.")
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    senha = os.environ.get("ADM_SENHA") or getpass.getpass("Senha do ADM: ")
    try:
        with get_session_factory()() as session:
            usuario = provisionar(session, nome=args.nome, email=args.email, senha=senha)
    except ErroDeProvisionamento as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"ADM da plataforma criado: {usuario.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
