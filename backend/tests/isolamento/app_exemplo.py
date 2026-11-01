"""Módulo de exemplo que existe SÓ nos testes (TASK-18).

Serve de molde para o guia "Como criar um endpoint novo respeitando o isolamento"
(docs/architecture.md). O trecho entre os marcadores abaixo é comparado com o do guia por
`test_guia_sincronizado.py`: se um mudar sem o outro, o teste falha.

O model usa um `DeclarativeBase` próprio, de propósito: assim ele nunca entra em `Base.metadata`
(o Alembic não enxerga, não há migration) e a tabela é criada dentro da transação de cada teste.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, ForeignKey, String, Table, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.contexto import ContextoCondominio
from app.db.repositorio import RepositorioDoCondominio
from app.db.session import get_session
from app.modules.auth.dependencies import ContextoDep


class BaseTeste(DeclarativeBase):
    pass


# Só existe para a FK de `itens_teste` ser resolvida; a tabela real `condominios` já está no banco.
Table("condominios", BaseTeste.metadata, Column("id", Uuid, primary_key=True))


class Item(BaseTeste):
    """Pré-requisito do guia: todo model de negócio tem `condominio_id` obrigatório (R2)."""

    __tablename__ = "itens_teste"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(80))


# inicio-exemplo
class ItemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")  # condominio_id no corpo vira 422 (R1)
    nome: str = Field(min_length=1, max_length=80)


class ItemSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str


class ItemRepositorio(RepositorioDoCondominio[Item]):
    modelo = Item  # o filtro por condomínio vem da classe base


class ItemService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.itens = ItemRepositorio(session, contexto)

    def listar(self) -> list[Item]:
        return self.itens.listar()

    def obter(self, item_id: uuid.UUID) -> Item:
        return self.itens.obter(item_id)  # 404 se não existir ou for de outro condomínio

    def criar(self, dados: ItemEntrada) -> Item:
        item = self.itens.criar(dados.model_dump())
        self.session.commit()  # quem faz commit é o service, nunca o repository
        return item

    def renomear(self, item_id: uuid.UUID, dados: ItemEntrada) -> Item:
        item = self.itens.atualizar(item_id, dados.model_dump())
        self.session.commit()
        return item

    def remover(self, item_id: uuid.UUID) -> None:
        self.itens.remover(item_id)  # em módulo real, prefira desativar (matriz, seção 7)
        self.session.commit()


def get_item_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> ItemService:
    return ItemService(session, contexto)  # o contexto vem do token + banco, nunca do cliente


ServiceDep = Annotated[ItemService, Depends(get_item_service)]
router = APIRouter(prefix="/itens")


@router.get("", response_model=list[ItemSaida])
def listar(service: ServiceDep) -> list[Item]:
    return service.listar()


@router.get("/{item_id}", response_model=ItemSaida)
def obter(item_id: uuid.UUID, service: ServiceDep) -> Item:
    return service.obter(item_id)


@router.post("", response_model=ItemSaida, status_code=201)
def criar(dados: ItemEntrada, service: ServiceDep) -> Item:
    return service.criar(dados)


@router.patch("/{item_id}", response_model=ItemSaida)
def renomear(item_id: uuid.UUID, dados: ItemEntrada, service: ServiceDep) -> Item:
    return service.renomear(item_id, dados)


@router.delete("/{item_id}", status_code=204)
def remover(item_id: uuid.UUID, service: ServiceDep) -> None:
    service.remover(item_id)


# fim-exemplo


# Rota só de teste: devolve o contexto montado pela dependência, para conferir o que veio do banco.
diagnostico = APIRouter(prefix="/diagnostico")


@diagnostico.get("/contexto")
def ver_contexto(contexto: ContextoDep) -> dict[str, str]:
    return {
        "usuario_id": str(contexto.usuario_id),
        "condominio_id": str(contexto.condominio_id),
        "perfil": contexto.perfil,
        "vinculo_id": str(contexto.vinculo_id),
    }
