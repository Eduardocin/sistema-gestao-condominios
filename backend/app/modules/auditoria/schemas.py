"""Contextos internos: construídos pela autenticação, nunca a partir de JSON do cliente."""

import uuid
from dataclasses import dataclass
from typing import Literal

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
