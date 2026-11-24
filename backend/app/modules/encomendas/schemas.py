import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StatusEncomenda(StrEnum):
    AGUARDANDO_RETIRADA = "aguardando_retirada"
    ENTREGUE_AGUARDANDO_CONFIRMACAO = "entregue_aguardando_confirmacao"
    RETIRADA_CONFIRMADA = "retirada_confirmada"


class EncomendaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unidade_id: uuid.UUID
    destinatario_morador_unidade_id: uuid.UUID
    descricao: str = Field(min_length=1, max_length=200)
    recebido_por_funcionario_id: uuid.UUID
    transportadora: str | None = Field(default=None, max_length=120)

    @field_validator("descricao")
    @classmethod
    def normalizar_descricao(cls, valor: str) -> str:
        descricao = valor.strip()
        if not descricao:
            raise ValueError("Informe a descrição da encomenda.")
        return descricao

    @field_validator("transportadora")
    @classmethod
    def normalizar_transportadora(cls, valor: str | None) -> str | None:
        return (valor or "").strip() or None


class EntregaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recebedor_morador_unidade_id: uuid.UUID
    entregue_por_funcionario_id: uuid.UUID


class ConfirmacaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnidadeResumo(BaseModel):
    id: uuid.UUID
    identificacao: str


class MoradorResumo(BaseModel):
    id: uuid.UUID
    nome: str


class RecebimentoSaida(BaseModel):
    em: datetime
    funcionario_id: uuid.UUID
    funcionario_nome: str


class EntregaSaida(BaseModel):
    em: datetime
    funcionario_id: uuid.UUID
    funcionario_nome: str
    recebedor_id: uuid.UUID
    recebedor_nome: str


class ConfirmacaoSaida(BaseModel):
    em: datetime
    morador_id: uuid.UUID
    morador_nome: str


class EncomendaSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    unidade: UnidadeResumo
    destinatario: MoradorResumo
    descricao: str
    transportadora: str | None
    foto_arquivo_id: uuid.UUID
    status: StatusEncomenda
    recebimento: RecebimentoSaida
    entrega: EntregaSaida | None
    confirmacao: ConfirmacaoSaida | None
    pode_confirmar: bool


class UnidadeOpcao(BaseModel):
    id: uuid.UUID
    identificacao: str
    bloco: str | None
    andar: str | None


class MoradorOpcao(BaseModel):
    id: uuid.UUID
    nome: str


class PaginaEncomendas(BaseModel):
    items: list[EncomendaSaida]
    page: int
    page_size: int
    total: int


class PaginaUnidades(BaseModel):
    items: list[UnidadeOpcao]
    page: int
    page_size: int
    total: int


class PaginaMoradores(BaseModel):
    items: list[MoradorOpcao]
    page: int
    page_size: int
    total: int


class PeriodoRelatorio(BaseModel):
    de: date | None
    ate: date | None


class TotaisPorStatus(BaseModel):
    registradas: int = 0
    aguardando_retirada: int = 0
    entregue_aguardando_confirmacao: int = 0
    retirada_confirmada: int = 0


class UnidadeNoRelatorio(TotaisPorStatus):
    unidade: UnidadeResumo


class RelatorioEncomendas(BaseModel):
    """Relatório da Administração (US-404): contagens por status, no total e por unidade."""

    periodo: PeriodoRelatorio
    totais: TotaisPorStatus
    por_unidade: list[UnidadeNoRelatorio]
