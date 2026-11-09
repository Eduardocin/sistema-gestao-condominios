"""Formatos de entrada e saída das permissões por aba (contrato em api-contracts/nucleo.md, §8)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

# As sete abas do DER (`ABAS_MORADOR`, em unidades/models.py). Fica escrito por extenso porque o
# Literal precisa dos valores na hora de checar os tipos; um teste garante que as duas listas
# são iguais.
AbaNome = Literal[
    "unidades", "visitantes", "veiculos", "reservas", "encomendas", "ocorrencias", "usuarios"
]


class AlterarPermissoesEntrada(BaseModel):
    """Corpo do PUT: `{"abas": {"visitantes": true, "veiculos": false}}`."""

    # Campo desconhecido (inclusive `condominio_id` ou `usuario_id`) é 422, nunca ignorado (R1).
    model_config = ConfigDict(extra="forbid")

    # Aceita um subconjunto das abas: só as informadas mudam. Aba com nome errado é 422.
    # StrictBool: só `true`/`false` de verdade, nada de "sim", 1 ou "true" entre aspas.
    abas: dict[AbaNome, StrictBool] = Field(min_length=1)


class MoradorSaida(BaseModel):
    """Um morador da unidade com as sete abas. Sem e-mail, telefone ou documento de propósito:
    para decidir permissões basta saber quem é a pessoa (LGPD, US-1007)."""

    model_config = ConfigDict(from_attributes=True)

    # Vai na URL do PUT (`morador_unidade_id`): identifica o morador NESTA unidade.
    id: uuid.UUID
    nome: str
    parentesco: str | None
    vinculado_em: datetime
    # True na linha de quem está consultando, para a tela avisar antes de tirar o próprio acesso.
    eu: bool
    # Sempre as sete abas, `true` = Com Acesso, `false` = Sem Acesso.
    permissoes: dict[AbaNome, bool]


class PaginaDeMoradores(BaseModel):
    """Formato de lista das convenções da API (seção 3)."""

    items: list[MoradorSaida]
    page: int
    page_size: int
    total: int
