"""Entrada e saída das ocorrências (api-contracts/convivencia.md, §5)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Titulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Detalhe = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
TextoDeInteracao = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
StatusOcorrencia = Literal["em_aberto", "resolvida"]


class OcorrenciaEntrada(BaseModel):
    """Abertura (US-701). `anexos` são IDs de arquivos já enviados ao storage."""

    model_config = ConfigDict(extra="forbid")

    unidade_id: uuid.UUID
    titulo: Titulo
    detalhe: Detalhe
    anexos: list[uuid.UUID] = Field(default_factory=list, max_length=5)

    @field_validator("anexos")
    @classmethod
    def sem_arquivo_repetido(cls, anexos: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(anexos)) != len(anexos):
            raise ValueError("Cada anexo pode ser informado uma única vez.")
        return anexos


class RespostaEntrada(BaseModel):
    """Resposta da Administração (US-703), com o responsável escolhido na lista."""

    model_config = ConfigDict(extra="forbid")

    texto: TextoDeInteracao
    responsavel_id: uuid.UUID


class ResolucaoEntrada(BaseModel):
    """Resolução da Administração (US-703). O texto é opcional."""

    model_config = ConfigDict(extra="forbid")

    texto: str | None = None
    responsavel_id: uuid.UUID

    @field_validator("texto")
    @classmethod
    def normalizar_texto(cls, texto: str | None) -> str | None:
        if texto is None:
            return None
        texto = texto.strip()
        if not texto:
            return None
        if len(texto) > 2000:
            raise ValueError("O texto deve ter no máximo 2000 caracteres.")
        return texto


class UnidadeResumo(BaseModel):
    id: uuid.UUID
    identificacao: str


class PessoaResumo(BaseModel):
    id: uuid.UUID
    nome: str


class AutorSaida(BaseModel):
    tipo: Literal["morador", "administracao"]
    nome: str


class AnexoSaida(BaseModel):
    arquivo_id: uuid.UUID
    interacao_id: uuid.UUID | None


class InteracaoSaida(BaseModel):
    id: uuid.UUID
    tipo: Literal["resposta", "comentario", "resolucao", "reabertura"]
    texto: str | None
    autor: AutorSaida
    em: datetime
    anexos: list[AnexoSaida]


class OcorrenciaResumo(BaseModel):
    id: uuid.UUID
    titulo: str
    status: StatusOcorrencia
    unidade: UnidadeResumo
    criada_em: datetime
    # Nula enquanto não houver interação; a abertura não conta como interação.
    ultima_interacao_em: datetime | None
    aguardando_administracao: bool


class OcorrenciaSaida(BaseModel):
    id: uuid.UUID
    unidade: UnidadeResumo
    titulo: str
    detalhe: str
    status: StatusOcorrencia
    aberta_por: PessoaResumo
    criada_em: datetime
    resolvida_em: datetime | None
    anexos: list[AnexoSaida]
    interacoes: list[InteracaoSaida]


class PaginaDeOcorrencias(BaseModel):
    items: list[OcorrenciaResumo]
    page: int
    page_size: int
    total: int
