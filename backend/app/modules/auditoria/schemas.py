"""Contextos internos validados e schemas explícitos da consulta exclusiva da plataforma."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.core.contexto import ContextoCondominio


@dataclass(frozen=True)
class ContextoAuditoria:
    usuario_id: uuid.UUID | None
    condominio_id: uuid.UUID | None = None
    perfil: str | None = None
    ip: str | None = None

    @classmethod
    def do_condominio(
        cls, contexto: ContextoCondominio, *, ip: str | None = None
    ) -> "ContextoAuditoria":
        return cls(contexto.usuario_id, contexto.condominio_id, contexto.perfil, ip)


@dataclass(frozen=True)
class ResponsavelRef:
    tipo: Literal["administracao", "funcionario"]
    id: uuid.UUID


class ConsultaAuditoria(BaseModel):
    """Filtros da consulta exclusiva da plataforma; não são contexto de autorização."""

    model_config = ConfigDict(extra="forbid")

    condominio_id: uuid.UUID | None = None
    de: date | None = None
    ate: date | None = None
    usuario_id: uuid.UUID | None = None
    acao: str | None = Field(
        default=None, max_length=60, pattern=r"^[a-z][a-z0-9_]*\.(?:[a-z][a-z0-9_]*)?$"
    )
    recurso_tipo: str | None = Field(default=None, min_length=1, max_length=60)
    recurso_id: uuid.UUID | None = None
    cursor: str | None = Field(default=None, min_length=1, max_length=512)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validar_periodo(self) -> Self:
        if self.de and self.ate and self.de > self.ate:
            raise ValueError("O início do período deve ser anterior ou igual ao fim.")
        if self.ate == date.max:
            raise ValueError("O fim do período deve ser anterior a 9999-12-31.")
        return self


class CursorAuditoria(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criado_em: AwareDatetime
    id: int = Field(gt=0, le=9223372036854775807)


class ReferenciaAuditoria(BaseModel):
    id: uuid.UUID
    nome: str


class RegistroAuditoriaSaida(BaseModel):
    id: int
    criado_em: datetime
    acao: str
    usuario: ReferenciaAuditoria | None
    responsavel_nome: str | None
    perfil: str | None
    condominio: ReferenciaAuditoria | None
    recurso_tipo: str | None
    recurso_id: uuid.UUID | None
    antes: dict[str, Any] | None
    depois: dict[str, Any] | None
    ip: str | None


class PaginaAuditoria(BaseModel):
    items: list[RegistroAuditoriaSaida]
    page_size: int
    next_cursor: str | None
