"""Chamados de suporte (plataforma.md, seção 3)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

StatusDoChamado = Literal["aberto", "em_atendimento", "encerrado"]
Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChamadoEntrada(BaseModel):
    """Abertura (US-901). `anexos` são IDs de arquivos já enviados ao storage (módulo suporte)."""

    model_config = ConfigDict(extra="forbid")

    titulo: Titulo
    descricao: Texto
    anexos: list[uuid.UUID] = Field(default_factory=list, max_length=5)

    @field_validator("anexos")
    @classmethod
    def sem_arquivo_repetido(cls, anexos: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(anexos)) != len(anexos):
            raise ValueError("Não repita o mesmo arquivo.")
        return anexos


class MensagemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: Texto


class EncerramentoEntrada(BaseModel):
    """`{}`: o corpo existe para o contrato, mas não aceita nada."""

    model_config = ConfigDict(extra="forbid")


class ConsultaDaAdministracao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusDoChamado | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ConsultaDaPlataforma(ConsultaDaAdministracao):
    condominio_id: uuid.UUID | None = None
    de: date | None = None
    ate: date | None = None
    busca: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None


class Referencia(BaseModel):
    id: uuid.UUID
    nome: str


class AutorDaMensagem(BaseModel):
    tipo: Literal["administracao", "plataforma"]
    nome: str


class MensagemSaida(BaseModel):
    id: uuid.UUID
    autor: AutorDaMensagem
    texto: str
    em: datetime


class ChamadoResumo(BaseModel):
    id: uuid.UUID
    titulo: str
    status: StatusDoChamado
    # Só nas rotas do ADM.
    condominio: Referencia | None = None
    aberto_por: Referencia
    atendido_por: Referencia | None
    criado_em: datetime
    encerrado_em: datetime | None


class ChamadoSaida(ChamadoResumo):
    descricao: str
    anexos: list[uuid.UUID]
    mensagens: list[MensagemSaida]


class PaginaDeChamados(BaseModel):
    items: list[ChamadoResumo]
    page: int
    page_size: int
    total: int
