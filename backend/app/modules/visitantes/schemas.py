import uuid
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.validation import validar_documento

Canal = Literal["interfone", "telefone"]
Situacao = Literal["vigentes", "futuros", "encerrados", "cancelados"]
StatusVisita = Literal["em_andamento", "encerrada"]
CPF = Annotated[str, Field(pattern=r"^[0-9]{11}$")]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DadosVisitante(Entrada):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    cpf: CPF | None = None
    idade: Annotated[int, Field(ge=0, le=120, strict=True)] | None = None
    observacoes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )
    entrada_prevista: date
    saida_prevista: date

    @field_validator("cpf")
    @classmethod
    def cpf_valido(cls, valor: str | None) -> str | None:
        return validar_documento(valor) if valor is not None else None

    @model_validator(mode="after")
    def periodo_valido(self) -> Self:
        if self.saida_prevista < self.entrada_prevista or self.saida_prevista == date.max:
            raise ValueError("Informe um período válido para a visita.")
        return self


class CadastroVisitante(DadosVisitante):
    unidade_id: uuid.UUID


class EdicaoVisitante(DadosVisitante):
    unidade_id: uuid.UUID | None = None


class BuscaDocumento(Entrada):
    unidade_id: uuid.UUID
    cpf: CPF


class FuncionarioEntrada(Entrada):
    funcionario_id: uuid.UUID


class ReferenciasEntrada(FuncionarioEntrada):
    visitante_id: uuid.UUID
    unidade_id: uuid.UUID


class ContatoAutorizado(Entrada):
    morador_id: uuid.UUID
    canal: Canal
    resposta: Literal["autorizou"]


class ContatoSemEntrada(ReferenciasEntrada):
    morador_id: uuid.UUID
    canal: Canal
    resposta: Literal["negou", "sem_resposta"]


class CadastroAvulso(FuncionarioEntrada):
    unidade_id: uuid.UUID
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    cpf: CPF
    contato: ContatoAutorizado

    @field_validator("cpf")
    @classmethod
    def cpf_valido(cls, valor: str) -> str:
        return validar_documento(valor)


class EntradaVisita(ReferenciasEntrada):
    autorizacao_id: uuid.UUID | None = None
    contato: ContatoAutorizado | None = None

    @model_validator(mode="after")
    def uma_evidencia(self) -> Self:
        if (self.autorizacao_id is None) == (self.contato is None):
            raise ValueError("Informe autorização prévia ou contato autorizado.")
        return self


class OpcaoVisitante(BaseModel):
    id: uuid.UUID
    nome: str
    unidade_id: uuid.UUID
    entrada_prevista: date
    saida_prevista: date


class VisitanteMorador(OpcaoVisitante):
    avulso: bool
    idade: int | None
    observacoes: str | None
    cpf: str | None
    cancelado_em: datetime | None


class Referencia(BaseModel):
    id: uuid.UUID
    nome: str


class VisitantePortaria(OpcaoVisitante):
    unidade: Referencia
    ambigua: bool


class Autorizacao(BaseModel):
    id: uuid.UUID
    visitante_id: uuid.UUID
    unidade_id: uuid.UUID
    autorizado_por: Referencia
    inicio: datetime
    fim: datetime


class Movimentacao(BaseModel):
    em: datetime
    funcionario: Referencia


class VisitaSaida(BaseModel):
    id: uuid.UUID
    visitante: Referencia
    unidade: Referencia
    status: StatusVisita
    entrada: Movimentacao
    saida: Movimentacao | None
    autorizacao_id: uuid.UUID | None
    autorizacao: Autorizacao | None
    contato: ContatoAutorizado | None


class ContatoSaida(ContatoSemEntrada):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    registrado_em: datetime
    visitante: Referencia
    unidade: Referencia
    funcionario: Referencia


class Pagina[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
