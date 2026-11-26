import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import normalizar_email, validar_documento, validar_telefone


class DadosConta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=3, max_length=120)
    telefone: str
    email: str = Field(max_length=254)

    _email = field_validator("email")(normalizar_email)
    _telefone = field_validator("telefone")(validar_telefone)

    @field_validator("nome", mode="before")
    @classmethod
    def normalizar_nome(cls, valor: object) -> object:
        return " ".join(valor.split()) if isinstance(valor, str) else valor


MENSAGEM_SENHA = "A senha deve ter letra e número e ser diferente do e-mail."

# Tamanho da senha (cadastro, troca e redefinição): a mesma regra em todos os lugares.
Senha = Annotated[str, Field(min_length=8, max_length=128)]


def conferir_senha(senha: str, email: str | None = None) -> str:
    """Regra mínima da senha (nucleo.md, 3.1): ao menos uma letra e um dígito e, quando o e-mail
    é conhecido, diferente dele. Única fonte da regra: cadastro, troca e redefinição usam esta."""
    if (
        not any(c.isalpha() for c in senha)
        or not any(c.isdigit() for c in senha)
        or (email is not None and senha.strip().lower() == email.lower())
    ):
        raise ValueError(MENSAGEM_SENHA)
    return senha


def _regra_da_senha(senha: str) -> str:
    # Validador de um argumento: o Pydantic leria um segundo parâmetro como `info`.
    return conferir_senha(senha)


class CadastroConta(DadosConta):
    senha: Senha

    @model_validator(mode="after")
    def validar_senha(self) -> "CadastroConta":
        conferir_senha(self.senha, self.email)
        return self


class CadastroMorador(CadastroConta):
    @field_validator("nome")
    @classmethod
    def nome_completo(cls, valor: str) -> str:
        if len(valor.split()) < 2:
            raise ValueError("Informe o nome completo.")
        return valor


class CadastroAdministracao(CadastroConta):
    documento: str

    _documento = field_validator("documento")(validar_documento)


class EdicaoConta(DadosConta):
    """PUT substitui os três campos editáveis; foto depende de upload global seguro."""


class ContaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: str
    telefone: str | None
    tipo_cadastro: Literal["morador", "administracao"] | None
    documento: str | None
    foto_arquivo_id: uuid.UUID | None


class TrocaSenha(BaseModel):
    """PUT /contas/me/senha. O e-mail da conta só é conhecido no service, que confere o resto."""

    model_config = ConfigDict(extra="forbid")

    # Teto igual ao da senha nova: nenhuma senha válida passa de 128, e o argon2 não recebe
    # entradas enormes.
    senha_atual: str = Field(min_length=1, max_length=128)
    senha_nova: Senha

    _senha_nova = field_validator("senha_nova")(_regra_da_senha)


class RedefinicaoSenha(BaseModel):
    """POST /contas/redefinicao-senha. O token é opaco; o banco guarda só o SHA-256 dele."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    senha_nova: Senha

    _senha_nova = field_validator("senha_nova")(_regra_da_senha)


class SolicitacaoRecuperacaoSenha(BaseModel):
    """POST /contas/recuperacao-senha. A resposta não revela se o e-mail tem conta."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)

    _email = field_validator("email")(normalizar_email)
