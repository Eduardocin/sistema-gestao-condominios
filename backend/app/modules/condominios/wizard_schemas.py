import re
import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.usuarios.schemas import CadastroBase


def _normalizar_texto(valor: str) -> str:
    return " ".join(valor.split())


class DadosGeraisRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    cep: str | None = Field(default=None, max_length=9)
    logradouro: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    complemento: str | None = Field(default=None, max_length=100)
    bairro: str | None = Field(default=None, max_length=100)
    cidade: str | None = Field(default=None, max_length=100)
    estado: str | None = Field(default=None, min_length=2, max_length=2)
    telefone: str | None = Field(default=None, max_length=20)

    @field_validator(
        "nome", "logradouro", "numero", "complemento", "bairro", "cidade", mode="before"
    )
    @classmethod
    def limpar_texto(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        texto = _normalizar_texto(valor)
        if not texto:
            raise ValueError("O campo não pode ficar vazio.")
        return texto

    @field_validator("cep")
    @classmethod
    def validar_cep(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        cep = re.sub(r"\D", "", valor)
        if len(cep) != 8:
            raise ValueError("Informe um CEP com oito dígitos.")
        return cep

    @field_validator("estado")
    @classmethod
    def normalizar_estado(cls, valor: str | None) -> str | None:
        return valor.upper() if valor else None


class BlocoRequest(BaseModel):
    nome: str = Field(min_length=1, max_length=80)

    @field_validator("nome")
    @classmethod
    def normalizar_nome(cls, valor: str) -> str:
        return _normalizar_texto(valor)


class BlocosRequest(BaseModel):
    blocos: list[BlocoRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def nomes_unicos(self) -> Self:
        nomes = [bloco.nome.casefold() for bloco in self.blocos]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Os nomes dos blocos devem ser únicos.")
        return self


class GeracaoUnidadesRequest(BaseModel):
    bloco: str = Field(min_length=1, max_length=80)
    andar_inicial: int = Field(ge=0, le=200)
    quantidade_andares: int = Field(ge=1, le=200)
    unidades_por_andar: int = Field(ge=1, le=100)

    @field_validator("bloco")
    @classmethod
    def normalizar_bloco(cls, valor: str) -> str:
        return _normalizar_texto(valor)


class UnidadesRequest(BaseModel):
    geracoes: list[GeracaoUnidadesRequest] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def limitar_quantidade_unidades(self) -> Self:
        total = sum(
            geracao.quantidade_andares * geracao.unidades_por_andar for geracao in self.geracoes
        )
        if total > 10_000:
            raise ValueError("O wizard permite gerar no máximo 10.000 unidades por condomínio.")
        nomes = [geracao.bloco.casefold() for geracao in self.geracoes]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Informe uma única configuração de unidades por bloco.")
        return self


class AreaComumRequest(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    descricao: str | None = Field(default=None, max_length=500)

    @field_validator("nome", "descricao", mode="before")
    @classmethod
    def normalizar_textos(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        texto = _normalizar_texto(valor)
        if not texto:
            raise ValueError("O campo não pode ficar vazio.")
        return texto


class AreasComunsRequest(BaseModel):
    areas_comuns: list[AreaComumRequest] = Field(max_length=100)

    @model_validator(mode="after")
    def nomes_unicos(self) -> Self:
        nomes = [area.nome.casefold() for area in self.areas_comuns]
        if len(nomes) != len(set(nomes)):
            raise ValueError("Os nomes das áreas comuns devem ser únicos.")
        return self


class ResponsavelRequest(CadastroBase):
    model_config = ConfigDict(extra="forbid")


class WizardIniciadoOut(BaseModel):
    id: uuid.UUID
    token: str
    etapa_atual: str
    expira_em: datetime


class WizardStatusOut(BaseModel):
    id: uuid.UUID
    etapa_atual: str
    expira_em: datetime
    dados_gerais: dict[str, str | None] | None = None
    blocos: list[dict[str, str]] | None = None
    unidades: list[dict[str, int | str]] | None = None
    areas_comuns: list[dict[str, str | None]] | None = None
    responsavel_configurado: bool


class WizardConcluidoOut(BaseModel):
    condominio_id: uuid.UUID
    condominio_ativo: bool
    usuario_administracao_id: uuid.UUID
    unidades_criadas: int
    status_conta: str
    token_status_solicitacao: str
