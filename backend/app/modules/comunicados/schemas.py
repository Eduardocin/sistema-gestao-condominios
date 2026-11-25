"""Comunicados do ADM às Administrações (plataforma.md, seção 2)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ComunicadoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Titulo
    texto: Texto


class ConsultaDeComunicados(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class Referencia(BaseModel):
    id: uuid.UUID
    nome: str


class ComunicadoDaAdministracao(BaseModel):
    """O que a Administração enxerga: o texto, sem os outros destinatários."""

    id: uuid.UUID
    titulo: str
    texto: str
    criado_em: datetime


class ComunicadoSaida(ComunicadoDaAdministracao):
    enviado_por: Referencia
    total_destinatarios: int


class ComunicadoComDestinatarios(ComunicadoSaida):
    destinatarios: list[Referencia]


class PaginaDeComunicados(BaseModel):
    items: list[ComunicadoSaida]
    page: int
    page_size: int
    total: int


class PaginaDeComunicadosDaAdministracao(BaseModel):
    items: list[ComunicadoDaAdministracao]
    page: int
    page_size: int
    total: int
