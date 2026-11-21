import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator

from app.core.validation import validar_documento

NomeEstrutura = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
IdentificacaoUnidade = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
]
StatusCondominio = Literal["pendente", "ativo", "rejeitado", "desativado"]


class EnderecoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cep: str = Field(pattern=r"^[0-9]{8}$")
    logradouro: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
    ]
    numero: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    complemento: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = (
        None
    )
    bairro: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    cidade: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    uf: str = Field(pattern=r"^[A-Z]{2}$")

    @field_validator("uf", mode="before")
    @classmethod
    def normalizar_uf(cls, valor: object) -> object:
        return valor.strip().upper() if isinstance(valor, str) else valor


class AndarEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: NomeEstrutura
    ordem: Annotated[StrictInt, Field(ge=0, le=200)]
    unidades: list[IdentificacaoUnidade] = Field(min_length=1, max_length=60)

    @field_validator("unidades")
    @classmethod
    def validar_unidades(cls, unidades: list[str]) -> list[str]:
        if any(not all(c.isalpha() or c in "0123456789 -/" for c in u) for u in unidades):
            raise ValueError("Unidades aceitam somente letras, dígitos, espaço, hífen e barra.")
        if len(set(unidades)) != len(unidades):
            raise ValueError("As identificações das unidades não podem se repetir no andar.")
        return unidades


class BlocoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: NomeEstrutura
    andares: list[AndarEntrada] = Field(min_length=1, max_length=100)

    @field_validator("andares")
    @classmethod
    def validar_andares(cls, andares: list[AndarEntrada]) -> list[AndarEntrada]:
        if len({andar.nome for andar in andares}) != len(andares):
            raise ValueError("Os nomes dos andares não podem se repetir no bloco.")
        return andares


class CadastroCondominio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    cnpj: str = Field(pattern=r"^[0-9]{14}$")
    endereco: EnderecoEntrada
    logo_arquivo_id: uuid.UUID | None = None
    documentos: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    blocos: list[BlocoEntrada] = Field(min_length=1, max_length=20)

    _cnpj = field_validator("cnpj")(validar_documento)

    @field_validator("blocos")
    @classmethod
    def validar_estrutura(cls, blocos: list[BlocoEntrada]) -> list[BlocoEntrada]:
        if len({bloco.nome for bloco in blocos}) != len(blocos):
            raise ValueError("Os nomes dos blocos não podem se repetir no condomínio.")
        if sum(len(andar.unidades) for bloco in blocos for andar in bloco.andares) > 2000:
            raise ValueError("O condomínio pode ter no máximo 2000 unidades.")
        return blocos


class ContagemEstrutura(BaseModel):
    blocos: int
    andares: int
    unidades: int


class CadastroCondominioSaida(BaseModel):
    id: uuid.UUID
    nome: str
    cnpj: str
    status: Literal["pendente"]
    enviado_em: datetime
    estrutura: ContagemEstrutura


class CondominioResumo(BaseModel):
    id: uuid.UUID
    nome: str
    status: StatusCondominio
    perfil: Literal["administracao"] = "administracao"


class AcaoAprovacao(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RejeicaoEntrada(AcaoAprovacao):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class FiltrosFila(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StatusCondominio = "pendente"
    busca: str | None = Field(default=None, max_length=150)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AdministracaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str
    email: str


class DocumentoSaida(BaseModel):
    arquivo_id: uuid.UUID
    nome_original: str


class DuplicidadeSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    status: StatusCondominio


class ItemFila(DuplicidadeSaida):
    cnpj: str | None
    enviado_em: datetime | None
    administracao: AdministracaoSaida | None
    documentos: list[DocumentoSaida]
    estrutura: ContagemEstrutura
    possivel_duplicidade: list[DuplicidadeSaida]


class PaginaFila(BaseModel):
    items: list[ItemFila]
    page: int
    page_size: int
    total: int


class AnaliseSaida(BaseModel):
    evento: str
    motivo: str | None
    em: datetime


class EnderecoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cep: str | None
    logradouro: str | None
    numero: str | None
    complemento: str | None
    bairro: str | None
    cidade: str | None
    uf: str | None


class CondominioSaida(DuplicidadeSaida):
    cnpj: str | None
    endereco: EnderecoSaida
    logo_arquivo_id: uuid.UUID | None
    motivo_rejeicao: str | None
    aprovado_em: datetime | None
    analises: list[AnaliseSaida]


class UnidadeAnalise(BaseModel):
    id: uuid.UUID
    identificacao: str
    ativo: bool


class AndarAnalise(BaseModel):
    id: uuid.UUID
    nome: str
    ordem: int
    ativo: bool
    unidades: list[UnidadeAnalise]


class BlocoAnalise(BaseModel):
    id: uuid.UUID
    nome: str
    ativo: bool
    andares: list[AndarAnalise]


class DetalhePlataforma(CondominioSaida):
    enviado_em: datetime | None
    administracao: AdministracaoSaida | None
    documentos: list[DocumentoSaida]
    estrutura: ContagemEstrutura
    possivel_duplicidade: list[DuplicidadeSaida]
    blocos: list[BlocoAnalise]


class AcaoCorrecao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    responsavel_id: uuid.UUID


class EdicaoCondominio(AcaoCorrecao):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    cnpj: str = Field(pattern=r"^[0-9]{14}$")
    endereco: EnderecoEntrada

    _cnpj = field_validator("cnpj")(validar_documento)


class EdicaoBloco(AcaoCorrecao):
    nome: NomeEstrutura


class EdicaoAndar(EdicaoBloco):
    ordem: Annotated[StrictInt, Field(ge=0, le=200)]


class EdicaoUnidade(AcaoCorrecao):
    identificacao: IdentificacaoUnidade

    @field_validator("identificacao")
    @classmethod
    def validar_identificacao(cls, valor: str) -> str:
        if not all(c.isalpha() or c in "0123456789 -/" for c in valor):
            raise ValueError("Unidades aceitam somente letras, dígitos, espaço, hífen e barra.")
        return valor


class BlocoCorrecaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    ativo: bool


class AndarCorrecaoSaida(BlocoCorrecaoSaida):
    ordem: int


class EstruturaSaida(BaseModel):
    blocos: list[BlocoAnalise]


class ReenvioSaida(CondominioSaida):
    enviado_em: datetime
