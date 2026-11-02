import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RejeitarCondominioRequest(BaseModel):
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def validar_motivo(cls, valor: str) -> str:
        motivo = " ".join(valor.split())
        if not motivo:
            raise ValueError("O motivo da rejeição é obrigatório.")
        return motivo


class CondominioPendenteOut(BaseModel):
    id: uuid.UUID
    nome: str
    cidade: str | None
    estado: str | None
    criado_em: datetime
    solicitante_nome: str | None
    solicitante_email: str | None


class ChaveGeradaOut(BaseModel):
    condominio_id: uuid.UUID
    status: str
    chave_acesso: str
    expira_em: datetime


class ChaveRevogadaOut(BaseModel):
    condominio_id: uuid.UUID
    revogada: bool


class DecisaoCondominioOut(BaseModel):
    condominio_id: uuid.UUID
    status: str
    motivo_rejeicao: str | None
    notificacao_registrada: bool


class ValidarChaveRequest(BaseModel):
    chave_acesso: str = Field(min_length=20, max_length=128)


class ChaveValidadaOut(BaseModel):
    valida: bool
    condominio_id: uuid.UUID | None
    condominio_nome: str | None
    expira_em: datetime | None


class StatusSolicitacaoOut(BaseModel):
    condominio_id: uuid.UUID
    nome: str
    status: str
    motivo_rejeicao: str | None
    criado_em: datetime
