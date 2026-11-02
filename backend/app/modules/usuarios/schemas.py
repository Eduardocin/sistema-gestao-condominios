import uuid
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.usuarios.validation import normalizar_cpf, validar_email, validar_senha_forte


class CadastroBase(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: str = Field(min_length=3, max_length=254)
    cpf: str = Field(min_length=11, max_length=14)
    senha: str = Field(min_length=12, max_length=128)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str) -> str:
        nome = " ".join(valor.split())
        if len(nome) < 2:
            raise ValueError("Informe um nome válido.")
        return nome

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, valor: str) -> str:
        return validar_email(valor)

    @field_validator("cpf")
    @classmethod
    def validar_e_normalizar_cpf(cls, valor: str) -> str:
        return normalizar_cpf(valor)

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, valor: str) -> str:
        return validar_senha_forte(valor)


class CadastroMoradorRequest(CadastroBase):
    chave_acesso: str = Field(min_length=20, max_length=128)


class CadastroFuncionarioRequest(CadastroBase):
    chave_acesso: str = Field(min_length=20, max_length=128)
    nome_responsavel: str = Field(min_length=2, max_length=150)

    @field_validator("nome_responsavel")
    @classmethod
    def normalizar_responsavel(cls, valor: str) -> str:
        nome = " ".join(valor.split())
        if len(nome) < 2:
            raise ValueError("Informe o nome da pessoa responsável.")
        return nome


class CadastroAdministracaoRequest(CadastroBase):
    condominio_id: uuid.UUID


class EditarUsuarioRequest(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    cpf: str | None = Field(default=None, min_length=11, max_length=14)
    nome_responsavel: str | None = Field(default=None, max_length=150)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        nome = " ".join(valor.split())
        if len(nome) < 2:
            raise ValueError("Informe um nome válido.")
        return nome

    @field_validator("email")
    @classmethod
    def normalizar_email(cls, valor: str | None) -> str | None:
        return validar_email(valor) if valor is not None else None

    @field_validator("cpf", mode="before")
    @classmethod
    def validar_e_normalizar_cpf(cls, valor: str | None) -> str | None:
        return normalizar_cpf(valor) if valor is not None else None

    @field_validator("nome_responsavel")
    @classmethod
    def normalizar_responsavel(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        nome = " ".join(valor.split())
        return nome or None

    @model_validator(mode="after")
    def exige_campo_editavel(self) -> Self:
        if not self.model_fields_set.intersection({"nome", "email", "cpf"}):
            raise ValueError("Informe ao menos um dado para editar.")
        if any(
            getattr(self, campo) is None
            for campo in self.model_fields_set & {"nome", "email", "cpf"}
        ):
            raise ValueError("Os dados pessoais informados não podem ser nulos.")
        return self


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: str
    cpf: str | None
    status_conta: str
