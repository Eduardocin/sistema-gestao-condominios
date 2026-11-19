import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.validation import normalizar_email, validar_documento, validar_telefone


class AcaoChave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsavel_id: uuid.UUID


class ProprietarioEntrada(AcaoChave):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    documento: str
    emails: list[str] = Field(default_factory=list, max_length=2)
    whatsapps: list[str] = Field(default_factory=list, max_length=2)
    telefone: str | None = None
    foto_arquivo_id: uuid.UUID | None = None

    _documento = field_validator("documento")(validar_documento)

    @field_validator("emails")
    @classmethod
    def validar_emails(cls, valores: list[str]) -> list[str]:
        return [normalizar_email(valor) for valor in valores]

    @field_validator("whatsapps")
    @classmethod
    def validar_whatsapps(cls, valores: list[str]) -> list[str]:
        return [validar_telefone(valor) for valor in valores]

    @field_validator("telefone")
    @classmethod
    def telefone_opcional(cls, valor: str | None) -> str | None:
        return validar_telefone(valor) if valor is not None else None


class ProprietarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str
    documento: str | None
    emails: list[str]
    whatsapps: list[str]
    telefone: str | None
    foto_arquivo_id: uuid.UUID | None


class ChaveSaida(BaseModel):
    codigo: str
    criada_em: datetime


class RevogacaoSaida(BaseModel):
    revogada_em: datetime


class UnidadeResumo(BaseModel):
    id: uuid.UUID
    identificacao: str
    bloco: str | None
    andar: str | None
    ativo: bool
    tem_proprietario: bool


class MoradorSaida(BaseModel):
    id: uuid.UUID
    nome: str
    parentesco: str | None
    status: str
    vinculado_em: datetime


class UnidadeDetalhe(UnidadeResumo):
    proprietario: ProprietarioSaida | None
    chave: ChaveSaida | None
    moradores: list[MoradorSaida]


class PaginaUnidades(BaseModel):
    items: list[UnidadeResumo]
    page: int
    page_size: int
    total: int


class FiltrosUnidades(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bloco_id: uuid.UUID | None = None
    andar_id: uuid.UUID | None = None
    busca: str | None = Field(default=None, max_length=150)
    sem_proprietario: bool | None = None
    ativo: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
