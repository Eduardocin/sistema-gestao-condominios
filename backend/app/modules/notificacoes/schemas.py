"""Entrada e saída do acompanhamento da fila de e-mails (plataforma.md, 6.3)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

StatusDoEnvio = Literal["pendente", "enviado", "falhou"]
EventoDoEnvio = Literal[
    "recuperacao_senha", "condominio_aprovado", "encomenda_registrada", "reserva_cancelada"
]


class ConsultaDeEnvios(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusDoEnvio | None = None
    evento: EventoDoEnvio | None = None
    condominio_id: uuid.UUID | None = None
    de: date | None = None
    ate: date | None = None
    page: int = 1
    page_size: int = 20


class EnvioSaida(BaseModel):
    id: uuid.UUID
    evento: str
    destinatario: str  # mascarado: a***@exemplo.com
    status: str
    tentativas: int
    ultimo_erro: str | None
    criado_em: datetime
    enviado_em: datetime | None


class PaginaDeEnvios(BaseModel):
    items: list[EnvioSaida]
    page: int
    page_size: int
    total: int


class ResultadoDoLote(BaseModel):
    enviados: int = 0
    falhas: int = 0  # tentativas que deram erro (o envio pode voltar à fila)
    esgotados: int = 0  # envios que passaram a `falhou`
