"""Entrada e saída dos visitantes cadastrados pelo Morador (api-contracts/convivencia.md, §6.2)."""

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
