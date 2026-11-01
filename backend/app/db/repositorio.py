"""Repositório base com isolamento por condomínio (R3, TASK-18).

Todo repository de dado de negócio herda daqui. A classe garante que:
- SELECT, UPDATE e DELETE sempre levam `condominio_id = <o do contexto>`;
- INSERT sempre grava o `condominio_id` do contexto;
- `condominio_id` nunca é aceito em `dados` (e `id` também não, no UPDATE);
- não existe método que busque por id sem condomínio.

Fica de fora de propósito: decidir permissão (é do service/autorização, TASK-19) e fazer commit
(é do service). Consultas customizadas devem partir de `self.consulta()`, que já vem filtrada.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, inspect, select, update
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.contexto import ContextoCondominio
from app.core.errors import RecursoNaoEncontrado


class CampoProtegido(ValueError):
    """Quem chamou tentou passar um campo que só o contexto ou o banco podem definir."""


class RepositorioDoCondominio[Modelo: DeclarativeBase]:
    # Cada subclasse declara o seu model: `modelo = Item`.
    modelo: type[Modelo]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Falha na definição da classe (import), não só quando alguém usa: um model sem
        # condominio_id jamais chega a rodar uma consulta.
        modelo = getattr(cls, "modelo", None)
        tabela = getattr(modelo, "__table__", None)
        if tabela is None:
            raise TypeError(f"{cls.__name__} precisa declarar `modelo = <um model mapeado>`.")
        # O atributo também precisa se chamar condominio_id: `atualizar()` recebe nomes de
        # atributo, e um apelido para a coluna (ex.: `dono`) escaparia da proteção de campos.
        # (hasattr no lugar de inspect(): não força a configuração dos mappers durante o import.)
        if "condominio_id" not in tabela.c or not hasattr(cls.modelo, "condominio_id"):
            raise TypeError(
                f"{cls.__name__}: o model {cls.modelo.__name__} não tem o atributo/coluna "
                "condominio_id (R2)."
            )

    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.contexto = contexto

    # --- peças internas ------------------------------------------------------------------

    @property
    def _colunas(self) -> Any:
        return self.modelo.__table__.c

    def _do_condominio(self) -> ColumnElement[bool]:
        return self._colunas.condominio_id == self.contexto.condominio_id

    def _do_registro(self, item_id: uuid.UUID) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
        """Filtro de UPDATE/DELETE: o registro E o condomínio. Nunca só o id."""
        return self._colunas.id == item_id, self._do_condominio()

    @staticmethod
    def _recusar(dados: Mapping[str, Any], protegidos: set[str]) -> None:
        proibidos = protegidos & set(dados)
        if proibidos:
            raise CampoProtegido(
                f"Campo(s) não aceitos em dados: {sorted(proibidos)}. "
                "O condominio_id vem sempre do contexto da requisição."
            )

    # --- consultas -----------------------------------------------------------------------

    def consulta(self) -> Select[tuple[Modelo]]:
        """Ponto de partida de qualquer SELECT: já filtrado pelo condomínio do contexto."""
        return select(self.modelo).where(self._do_condominio())

    def listar(self, *, limite: int = 100) -> list[Modelo]:
        """Até `limite` registros do condomínio. Para paginar de verdade, use `consulta()`."""
        chaves = inspect(self.modelo).primary_key
        return list(self.session.scalars(self.consulta().order_by(*chaves).limit(limite)))

    def obter(self, item_id: uuid.UUID) -> Modelo:
        """Devolve o registro ou levanta `RecursoNaoEncontrado` (404), exista ele ou não em outro
        condomínio: a resposta é a mesma (R4)."""
        item = self.session.scalar(self.consulta().where(self._colunas.id == item_id))
        if item is None:
            raise RecursoNaoEncontrado
        return item

    # --- escrita (sem commit: quem comita é o service) --------------------------------------

    def criar(self, dados: Mapping[str, Any]) -> Modelo:
        self._recusar(dados, {"condominio_id"})
        item = self.modelo(**dados, condominio_id=self.contexto.condominio_id)
        self.session.add(item)
        self.session.flush()  # aplica as constraints agora e já preenche os defaults (id, datas)
        return item

    def atualizar(self, item_id: uuid.UUID, dados: Mapping[str, Any]) -> Modelo:
        # `id` também é protegido: trocar a chave de um registro não é "atualizar".
        self._recusar(dados, {"condominio_id", "id"})
        if not dados:
            raise ValueError("atualizar() precisa de pelo menos um campo.")
        comando = (
            update(self.modelo)
            .where(*self._do_registro(item_id))
            .values(**dados)
            .returning(self.modelo)
            .execution_options(populate_existing=True)
        )
        item = self.session.scalar(comando)
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def remover(self, item_id: uuid.UUID) -> None:
        """DELETE físico. Os services devem preferir desativar: nenhum perfil apaga registro."""
        comando = delete(self.modelo).where(*self._do_registro(item_id)).returning(self._colunas.id)
        if self.session.scalar(comando) is None:
            raise RecursoNaoEncontrado
