"""Contratos de leitura da US-506, sem documentos pessoais ou evidências internas."""

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.modules.visitantes.schemas import Entrada, Movimentacao, Referencia, StatusVisita


class FiltrosRelatorio(Entrada):
    unidade_id: uuid.UUID | None = None
    de: date | None = None
    ate: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def periodo_valido(self) -> Self:
        if self.de == date.max or self.ate == date.max:
            raise ValueError("Informe datas anteriores a 9999-12-31.")
        if self.de is not None and self.ate is not None and self.de > self.ate:
            raise ValueError("A data inicial deve ser anterior ou igual à final.")
        return self


class UnidadeRelatorio(BaseModel):
    id: uuid.UUID
    identificacao: str
    bloco: str | None
    andar: str | None


class VisitaRelatorio(BaseModel):
    id: uuid.UUID
    visitante: Referencia
    unidade: UnidadeRelatorio
    avulso: bool
    status: StatusVisita
    entrada: Movimentacao
    saida: Movimentacao | None


class VeiculoRelatorio(BaseModel):
    id: uuid.UUID
    unidade: UnidadeRelatorio
    placa: str
    marca: str
    modelo: str
    cor: str
    ativo: bool
    criado_em: datetime
    removido_em: datetime | None
    placa_duplicada: bool
