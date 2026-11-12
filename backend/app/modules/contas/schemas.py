from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.validation import normalizar_email, validar_documento, validar_telefone


class CadastroConta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=3, max_length=120)
    telefone: str
    email: str = Field(max_length=254)
    senha: str = Field(min_length=8, max_length=128)

    _email = field_validator("email")(normalizar_email)
    _telefone = field_validator("telefone")(validar_telefone)

    @field_validator("nome", mode="before")
    @classmethod
    def normalizar_nome(cls, valor: object) -> object:
        return " ".join(valor.split()) if isinstance(valor, str) else valor

    @model_validator(mode="after")
    def validar_senha(self) -> "CadastroConta":
        if (
            not any(c.isalpha() for c in self.senha)
            or not any(c.isdigit() for c in self.senha)
            or self.senha.strip().lower() == self.email
        ):
            raise ValueError("A senha deve ter letra e número e ser diferente do e-mail.")
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
