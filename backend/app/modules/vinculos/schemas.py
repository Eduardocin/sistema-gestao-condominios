import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.unidades.service import ALFABETO_CHAVE


class VinculoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str

    @field_validator("chave")
    @classmethod
    def normalizar_chave(cls, valor: str) -> str:
        if len(valor) > 64:
            raise ValueError("Formato de chave inválido.")
        valor = "".join(valor.split()).replace("-", "").upper()
        if len(valor) != 10 or any(c not in ALFABETO_CHAVE for c in valor):
            raise ValueError("Formato de chave inválido.")
        return valor


class ReferenciaCondominio(BaseModel):
    id: uuid.UUID
    nome: str


class ReferenciaUnidade(BaseModel):
    id: uuid.UUID
    identificacao: str


class VinculoSaida(BaseModel):
    unidade: ReferenciaUnidade
    condominio: ReferenciaCondominio


class DesvinculacaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsavel_id: uuid.UUID | None = None


class DesvinculacaoSaida(BaseModel):
    id: uuid.UUID
    status: Literal["desvinculado"] = "desvinculado"
    desvinculado_em: datetime
    chave_revogada: bool


class ProprietarioPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str
    emails: list[str]
    whatsapps: list[str]
    telefone: str | None
    foto_arquivo_id: uuid.UUID | None


class MinhaUnidade(ReferenciaUnidade):
    condominio: ReferenciaCondominio
    proprietario: ProprietarioPublico | None


class PaginaMinhasUnidades(BaseModel):
    items: list[MinhaUnidade]
    page: int
    page_size: int
    total: int


class FiltrosMinhasUnidades(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20
