"""Entrada e saída das áreas comuns e das reservas (api-contracts/convivencia.md, §2 e §4)."""

import re
import uuid
from datetime import date, datetime, time
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)

_HORA_CHEIA = re.compile(r"^([01]\d|2[0-3]):00$")


def _ler_hora_cheia(valor: Any) -> Any:
    """ "HH:00" vira `time`. Qualquer outra coisa ("08:30", "8:00", "24:00", número) é erro."""
    if isinstance(valor, time):  # vindo do banco (saída)
        return valor
    if isinstance(valor, str) and (achou := _HORA_CHEIA.match(valor)):
        return time(int(achou.group(1)))
    raise ValueError('Use uma hora cheia no formato "HH:00".')


# Entra e sai como texto "HH:MM". Hora quebrada (08:30) é 422: a grade da reserva é de 1 hora.
HoraCheia = Annotated[
    time,
    BeforeValidator(_ler_hora_cheia),
    PlainSerializer(lambda hora: hora.strftime("%H:%M"), return_type=str),
    WithJsonSchema({"type": "string", "pattern": r"^([01]\d|2[0-3]):00$", "examples": ["08:00"]}),
]


class AreaComumEntrada(BaseModel):
    """Corpo do POST e do PUT (o PUT substitui os campos editáveis)."""

    # Campo desconhecido (inclusive `condominio_id` e `ativa`) é 422, nunca ignorado (R1).
    model_config = ConfigDict(extra="forbid")

    # O strip vem antes do tamanho: "   " vira "" e cai no min_length.
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    foto_arquivo_id: uuid.UUID
    regras: Annotated[str, StringConstraints(max_length=2000)] | None = None
    abre_as: HoraCheia
    fecha_as: HoraCheia
    # SmallInteger no banco: 32767 é o teto. StrictInt recusa "40" e 40.5.
    capacidade: Annotated[StrictInt, Field(ge=1, le=32767)]

    @model_validator(mode="after")
    def _janela_de_funcionamento(self) -> Self:
        # Com as duas horas cheias, fecha > abre já garante a janela mínima de 1 hora.
        if self.fecha_as <= self.abre_as:
            raise ValueError("fecha_as precisa ser maior que abre_as (janela de pelo menos 1h).")
        return self


class AcaoVazia(BaseModel):
    """Corpo das ações de desativação e reativação: `{}`. Qualquer campo é 422."""

    model_config = ConfigDict(extra="forbid")


class AreaComumSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    foto_arquivo_id: uuid.UUID
    regras: str | None
    abre_as: HoraCheia
    fecha_as: HoraCheia
    capacidade: int
    ativa: bool


class PaginaDeAreas(BaseModel):
    """Formato de lista das convenções da API (seção 3)."""

    items: list[AreaComumSaida]
    page: int
    page_size: int
    total: int


# --- reservas (convivencia.md, seção 4) -------------------------------------------------------

_HORA_HH_MM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _ler_hora_hh_mm(valor: Any) -> Any:
    """Só o FORMATO "HH:MM". Se é hora cheia, quem decide é o service (422 `hora_invalida`),
    para respeitar a ordem de validação do contrato (a área vem antes da hora)."""
    if isinstance(valor, str) and (achou := _HORA_HH_MM.match(valor)):
        return time(int(achou.group(1)), int(achou.group(2)))
    raise ValueError('Use o formato "HH:MM".')


# Saída "HH:MM" sem regra de entrada (hora_fim é calculada, nunca recebida).
HoraTexto = Annotated[
    time,
    PlainSerializer(lambda hora: hora.strftime("%H:%M"), return_type=str),
    WithJsonSchema({"type": "string", "examples": ["18:00"]}),
]


class ReservaEntrada(BaseModel):
    """Corpo do POST /reservas. Sem `hora_fim`: a reserva é sempre um slot de 1 hora."""

    model_config = ConfigDict(extra="forbid")

    unidade_id: uuid.UUID
    area_id: uuid.UUID
    data: date
    hora_inicio: Annotated[
        time,
        BeforeValidator(_ler_hora_hh_mm),
        WithJsonSchema({"type": "string", "pattern": r"^\d{2}:\d{2}$", "examples": ["18:00"]}),
    ]


class CancelamentoEntrada(BaseModel):
    """Morador: `{}`. Administração: `motivo` e `responsavel_id` (o service exige os dois)."""

    model_config = ConfigDict(extra="forbid")

    motivo: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
        | None
    ) = None
    responsavel_id: uuid.UUID | None = None


class Referencia(BaseModel):
    id: uuid.UUID
    nome: str


class UnidadeRef(BaseModel):
    id: uuid.UUID
    identificacao: str


class CancelamentoSaida(BaseModel):
    em: datetime
    por: Literal["morador", "administracao"]
    motivo: str | None
    # Só para a Administração: quando não é preenchido, a rota omite o campo (exclude_unset).
    responsavel: Referencia | None = None


class ReservaSaida(BaseModel):
    id: uuid.UUID
    area: Referencia
    unidade: UnidadeRef
    data: date
    hora_inicio: HoraTexto
    hora_fim: HoraTexto
    status: Literal["ativa", "cancelada"]
    # Só para a própria unidade e para a Administração; senão, o campo não aparece.
    reservada_por: Referencia | None = None
    criada_em: datetime
    cancelamento: CancelamentoSaida | None


class PaginaDeReservas(BaseModel):
    items: list[ReservaSaida]
    page: int
    page_size: int
    total: int


EstadoSlot = Literal["livre", "da_minha_unidade", "ocupado", "bloqueado", "passado"]


class SlotSaida(BaseModel):
    hora_inicio: HoraTexto
    hora_fim: HoraTexto
    estado: EstadoSlot
    # Só em `da_minha_unidade`. Nunca há referência a reserva de outra unidade.
    reserva_id: uuid.UUID | None = None


class AgendaSaida(BaseModel):
    area_id: uuid.UUID
    unidade_id: uuid.UUID
    data: date
    unidade_ja_reservou: bool
    slots: list[SlotSaida]


class DiaDoCalendario(BaseModel):
    data: date
    bloqueado: bool
    tem_reserva_da_minha_unidade: bool


class CalendarioSaida(BaseModel):
    mes: str
    dias: list[DiaDoCalendario]


# --- bloqueio de datas (US-602) -------------------------------------------------------------


class BloqueioEntrada(BaseModel):
    """Corpo do POST de bloqueio. Datas inclusivas, no fuso do condomínio (regra 15)."""

    model_config = ConfigDict(extra="forbid")

    data_inicio: date
    data_fim: date
    # O DER guarda até 200 caracteres (`bloqueios_area.motivo`).
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    responsavel_id: uuid.UUID
    confirmar_cancelamentos: bool = False

    @model_validator(mode="after")
    def _intervalo(self) -> Self:
        if self.data_fim < self.data_inicio:
            raise ValueError("data_fim não pode ser anterior a data_inicio.")
        return self


class ReservaAfetada(BaseModel):
    id: uuid.UUID
    unidade: UnidadeRef
    data: date
    hora_inicio: HoraTexto


class PreviaDoBloqueio(BaseModel):
    reservas_afetadas: list[ReservaAfetada]
    total: int


class BloqueioSaida(BaseModel):
    id: uuid.UUID
    area_id: uuid.UUID
    data_inicio: date
    data_fim: date
    motivo: str | None
    responsavel: Referencia
    criado_em: datetime


class BloqueioCriadoSaida(BloqueioSaida):
    reservas_canceladas: int


class PaginaDeBloqueios(BaseModel):
    items: list[BloqueioSaida]
    page: int
    page_size: int
    total: int
