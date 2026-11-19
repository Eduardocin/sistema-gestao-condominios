import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

SituacaoFiltro = Literal["vigentes", "agendados", "encerrados", "todos"]
SituacaoAviso = Literal["vigente", "agendado", "expirado", "encerrado"]


class AvisoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    texto: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    importante: bool = False
    inicio_em: AwareDatetime
    fim_em: AwareDatetime
    responsavel_id: uuid.UUID

    @model_validator(mode="after")
    def validar_periodo(self) -> Self:
        if self.fim_em <= self.inicio_em:
            raise ValueError("fim_em precisa ser maior que inicio_em.")
        return self


class EncerramentoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsavel_id: uuid.UUID


class ResponsavelSaida(BaseModel):
    id: uuid.UUID
    nome: str


class UnidadeSaida(BaseModel):
    id: uuid.UUID
    identificacao: str


class AvisoSaida(BaseModel):
    id: uuid.UUID
    titulo: str
    texto: str
    importante: bool
    inicio_em: datetime
    fim_em: datetime
    encerrado_em: datetime | None
    situacao: SituacaoAviso
    unidade: UnidadeSaida | None
    publicado_por: ResponsavelSaida | None = None


class PaginaDeAvisos(BaseModel):
    items: list[AvisoSaida]
    page: int
    page_size: int
    total: int
