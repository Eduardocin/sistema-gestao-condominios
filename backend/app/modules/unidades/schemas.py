import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SolicitarVinculoUnidadeRequest(BaseModel):
    bloco: str = Field(min_length=1, max_length=80)
    unidade: str = Field(min_length=1, max_length=80)
    chave_acesso: str = Field(min_length=20, max_length=128)
    responsavel_principal: bool = False

    @field_validator("bloco", "unidade")
    @classmethod
    def normalizar_texto(cls, valor: str) -> str:
        texto = " ".join(valor.split())
        if not texto:
            raise ValueError("Informe o bloco e a unidade.")
        return texto


class AprovarVinculoUnidadeRequest(BaseModel):
    nome_responsavel: str = Field(min_length=2, max_length=150)

    @field_validator("nome_responsavel")
    @classmethod
    def normalizar_responsavel(cls, valor: str) -> str:
        nome = " ".join(valor.split())
        if not nome:
            raise ValueError("Informe o nome da pessoa responsável.")
        return nome


class RejeitarVinculoUnidadeRequest(AprovarVinculoUnidadeRequest):
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def normalizar_motivo(cls, valor: str) -> str:
        motivo = " ".join(valor.split())
        if not motivo:
            raise ValueError("O motivo da rejeição é obrigatório.")
        return motivo


class SolicitacaoVinculoUnidadeOut(BaseModel):
    id: uuid.UUID
    morador_nome: str
    morador_email: str
    bloco: str
    unidade: str
    responsavel_principal: bool
    solicitado_em: datetime


class SolicitacaoCriadaOut(BaseModel):
    solicitacao_id: uuid.UUID
    status: str
    condominio_id: uuid.UUID
    unidade_id: uuid.UUID
    responsavel_principal: bool


class DecisaoVinculoUnidadeOut(BaseModel):
    solicitacao_id: uuid.UUID
    status: str
    motivo_rejeicao: str | None
    responsavel_principal: bool
    notificacao_registrada: bool
