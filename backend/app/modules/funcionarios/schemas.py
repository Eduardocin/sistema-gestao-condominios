import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validation import normalizar_email, validar_telefone


class NomeEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=120)

    @field_validator("nome", mode="before")
    @classmethod
    def normalizar_nome(cls, valor: object) -> object:
        return " ".join(valor.split()) if isinstance(valor, str) else valor


class FuncionarioEntrada(NomeEntrada):
    funcao: Literal["porteiro", "seguranca"]
    telefone: str
    email: str = Field(max_length=254)
    foto_arquivo_id: uuid.UUID | None = None
    responsavel_id: uuid.UUID

    _email = field_validator("email")(normalizar_email)
    _telefone = field_validator("telefone")(validar_telefone)


class DesligamentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsavel_id: uuid.UUID


class FuncionarioNome(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str


class FuncionarioSaida(FuncionarioNome):
    funcao: Literal["porteiro", "seguranca"]
    telefone: str | None
    email: str | None
    foto_arquivo_id: uuid.UUID | None
    ativo: bool
    desligado_em: datetime | None


class PaginaFuncionarios(BaseModel):
    # O modelo completo vem antes do resumido para não descartar campos da Administração.
    items: list[FuncionarioSaida | FuncionarioNome]
    page: int
    page_size: int
    total: int


class ResponsavelEntrada(NomeEntrada):
    nome: str = Field(min_length=1, max_length=100)


class ResponsavelSaida(FuncionarioNome):
    ativo: bool
