"""Formatos de entrada e saída da API de autenticação (contrato em docs/api-contracts/auth.md)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# O campo se chama `identificador` porque o contrato prevê e-mail OU telefone (US-101).
# Por enquanto só o e-mail existe no banco; o telefone entra quando o DER ganhar a coluna.


class LoginRequest(BaseModel):
    identificador: str = Field(min_length=3, max_length=254)
    # Limite superior evita que alguém mande um texto gigante só para gastar CPU no argon2.
    senha: str = Field(min_length=1, max_length=128)

    @field_validator("identificador")
    @classmethod
    def _normalizar(cls, valor: str) -> str:
        # E-mail é guardado em minúsculas (ADR 0002), então normalizamos antes de comparar.
        return valor.strip().lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class SelecionarCondominioRequest(BaseModel):
    condominio_id: uuid.UUID


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: str


class CondominioAcessoOut(BaseModel):
    """Um condomínio em que o usuário tem vínculo, com o perfil dele ali."""

    model_config = ConfigDict(from_attributes=True)

    # Atributos do dataclass `Acesso` (service.py): `condominio_id` vira `id` na resposta.
    id: uuid.UUID = Field(validation_alias="condominio_id")
    nome: str
    perfil: Literal["administracao", "funcionario", "morador"]
    status: Literal["ativo", "desativado"]


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    # Validade do access token, em segundos (o front usa para agendar a renovação).
    expires_in: int
    usuario: UsuarioOut
    # Preenchido quando o token já nasce com condomínio (`cid`).
    condominio: CondominioAcessoOut | None
    condominios: list[CondominioAcessoOut]
    # True quando o usuário precisa escolher o condomínio (chamar /auth/selecionar-condominio).
    requer_selecao: bool
    # True para o ADM da plataforma (que não pertence a condomínio). Só para a interface.
    administrador_plataforma: bool


class RefreshResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UnidadeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identificacao: str


class MeResponse(BaseModel):
    usuario: UsuarioOut
    condominio: CondominioAcessoOut | None
    # Só o Morador tem unidades. Permissões por aba entram com a TASK-21.
    unidades: list[UnidadeOut]
    administrador_plataforma: bool
