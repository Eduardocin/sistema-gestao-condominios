"""Entrada e saída de visitantes (§6.2) e veículos (§6.3), em api-contracts/convivencia.md."""

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.validation import validar_documento

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Situacao = Literal["vigentes", "futuros", "encerrados", "cancelados"]
SituacaoDoVisitante = Literal["vigente", "futuro", "encerrado", "cancelado"]


class _DadosDoVisitante(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Nome
    cpf: str | None = None
    idade: int | None = Field(default=None, ge=0, le=120)
    observacoes: str | None = None
    entrada_prevista: date
    saida_prevista: date

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, cpf: str | None) -> str | None:
        if cpf is None:
            return None
        # `validar_documento` aceita CPF ou CNPJ; aqui só vale CPF, só dígitos.
        if not re.fullmatch(r"[0-9]{11}", cpf):
            raise ValueError("Informe o CPF com 11 dígitos, sem pontos nem traço.")
        return validar_documento(cpf)

    @field_validator("observacoes")
    @classmethod
    def normalizar_observacoes(cls, observacoes: str | None) -> str | None:
        if observacoes is None:
            return None
        observacoes = observacoes.strip()
        if len(observacoes) > 300:
            raise ValueError("As observações devem ter no máximo 300 caracteres.")
        return observacoes or None

    @model_validator(mode="after")
    def periodo_valido(self) -> "_DadosDoVisitante":
        if self.saida_prevista < self.entrada_prevista:
            raise ValueError("A saída prevista não pode ser anterior à entrada prevista.")
        return self


class VisitanteEntrada(_DadosDoVisitante):
    unidade_id: uuid.UUID


class VisitanteAtualizacao(_DadosDoVisitante):
    """`PUT`: o mesmo corpo da criação. A unidade não muda; se vier, tem de ser a atual."""

    unidade_id: uuid.UUID | None = None


class UnidadeResumo(BaseModel):
    id: uuid.UUID
    identificacao: str


class VisitanteSaida(BaseModel):
    id: uuid.UUID
    unidade: UnidadeResumo
    nome: str
    cpf: str | None
    idade: int | None
    observacoes: str | None
    entrada_prevista: date
    saida_prevista: date
    avulso: bool
    situacao: SituacaoDoVisitante
    # Verdadeiro quando já existe visita registrada: a edição passa a ser recusada (409).
    ja_utilizado: bool
    criado_em: datetime
    cancelado_em: datetime | None


class PaginaDeVisitantes(BaseModel):
    items: list[VisitanteSaida]
    page: int
    page_size: int
    total: int


# --- veículos (US-502) ----------------------------------------------------------------------

PLACA = re.compile(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}")
TextoDoVeiculo = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]


def normalizar_placa(valor: str) -> str:
    """Maiúsculas, sem hífen nem espaço (regra 13 do DER)."""
    return re.sub(r"[\s-]", "", valor).upper()


class _DadosDoVeiculo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    placa: str
    marca: TextoDoVeiculo
    modelo: TextoDoVeiculo
    cor: TextoDoVeiculo

    @field_validator("placa")
    @classmethod
    def validar_placa(cls, placa: str) -> str:
        placa = normalizar_placa(placa)
        if not PLACA.fullmatch(placa):
            raise ValueError("Informe uma placa no formato antigo (ABC1234) ou Mercosul (ABC1D23).")
        return placa


class VeiculoEntrada(_DadosDoVeiculo):
    unidade_id: uuid.UUID


class VeiculoAtualizacao(_DadosDoVeiculo):
    """`PUT`: o mesmo corpo da criação. A unidade não muda; se vier, tem de ser a atual."""

    unidade_id: uuid.UUID | None = None


class VeiculoSaida(BaseModel):
    id: uuid.UUID
    unidade: UnidadeResumo
    placa: str
    marca: str
    modelo: str
    cor: str
    ativo: bool
    criado_em: datetime
    removido_em: datetime | None


class PaginaDeVeiculos(BaseModel):
    items: list[VeiculoSaida]
    page: int
    page_size: int
    total: int
