"""Repositório base: o SQL gerado sempre leva o filtro de condomínio. Sem banco (sessão falsa)."""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.contexto import ContextoCondominio
from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import CampoProtegido, RepositorioDoCondominio
from tests.isolamento.app_exemplo import Item, ItemRepositorio


class OutraBase(DeclarativeBase):
    pass


class SemCondominio(OutraBase):
    """Model sem `condominio_id`: não pode ganhar um repositório de condomínio."""

    __tablename__ = "sem_condominio"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(10))


class AtributoRenomeado(OutraBase):
    """A coluna se chama condominio_id, mas o atributo não: `atualizar({"dono": ...})` driblaria
    a proteção de campos. Por isso o nome do atributo também precisa ser condominio_id."""

    __tablename__ = "atributo_renomeado"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dono: Mapped[uuid.UUID] = mapped_column("condominio_id")


@pytest.fixture
def contexto() -> ContextoCondominio:
    return ContextoCondominio(
        usuario_id=uuid.uuid4(),
        condominio_id=uuid.uuid4(),
        perfil="morador",
        vinculo_id=uuid.uuid4(),
    )


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def repo(session, contexto) -> ItemRepositorio:
    return ItemRepositorio(session, contexto)


def compilar(comando):
    compilado = comando.compile(dialect=postgresql.dialect())
    # O SQL vem com quebras de linha; normalizamos para os testes olharem só o conteúdo.
    return " ".join(str(compilado).split()), compilado.params


def parte_where(sql: str) -> str:
    """O trecho entre WHERE e RETURNING (o RETURNING lista colunas e não conta como filtro)."""
    return sql.split(" WHERE ", 1)[1].split(" RETURNING", 1)[0]


# --- SELECT ------------------------------------------------------------------------------


def test_consulta_ja_sai_filtrada_pelo_condominio(repo, contexto):
    sql, params = compilar(repo.consulta())

    assert "itens_teste.condominio_id = " in parte_where(sql)
    assert contexto.condominio_id in params.values()


def test_obter_filtra_por_id_e_por_condominio(repo, session, contexto):
    session.scalar.return_value = None
    item_id = uuid.uuid4()

    with pytest.raises(RecursoNaoEncontrado):
        repo.obter(item_id)

    sql, params = compilar(session.scalar.call_args.args[0])
    where = parte_where(sql)
    assert "itens_teste.id = " in where and "itens_teste.condominio_id = " in where
    assert {item_id, contexto.condominio_id} <= set(params.values())


def test_listar_filtra_por_condominio(repo, session, contexto):
    session.scalars.return_value = []

    repo.listar()

    sql, params = compilar(session.scalars.call_args.args[0])
    assert "itens_teste.condominio_id = " in parte_where(sql)
    assert contexto.condominio_id in params.values()


# --- UPDATE ------------------------------------------------------------------------------


def test_atualizar_filtra_por_id_e_condominio_e_nao_toca_no_condominio(repo, session, contexto):
    session.scalar.return_value = None

    with pytest.raises(RecursoNaoEncontrado):
        repo.atualizar(uuid.uuid4(), {"nome": "Novo"})

    sql, params = compilar(session.scalar.call_args.args[0])
    assert sql.startswith("UPDATE itens_teste SET ")
    where = parte_where(sql)
    assert "itens_teste.id = " in where and "itens_teste.condominio_id = " in where
    # O SET só pode ter o campo pedido: o condomínio do registro nunca muda.
    assert "condominio_id" not in sql.split(" WHERE ", 1)[0]
    assert contexto.condominio_id in params.values()


@pytest.mark.parametrize("campo", ["condominio_id", "id"])
def test_atualizar_recusa_campos_protegidos(repo, session, campo):
    with pytest.raises(CampoProtegido):
        repo.atualizar(uuid.uuid4(), {"nome": "Novo", campo: uuid.uuid4()})

    session.scalar.assert_not_called()


def test_atualizar_sem_dados_falha_em_vez_de_gerar_update_vazio(repo, session):
    with pytest.raises(ValueError):
        repo.atualizar(uuid.uuid4(), {})

    session.scalar.assert_not_called()


# --- DELETE ------------------------------------------------------------------------------


def test_remover_filtra_por_id_e_condominio(repo, session, contexto):
    session.scalar.return_value = None

    with pytest.raises(RecursoNaoEncontrado):
        repo.remover(uuid.uuid4())

    sql, params = compilar(session.scalar.call_args.args[0])
    assert sql.startswith("DELETE FROM itens_teste WHERE ")
    where = parte_where(sql)
    assert "itens_teste.id = " in where and "itens_teste.condominio_id = " in where
    assert contexto.condominio_id in params.values()


# --- INSERT ------------------------------------------------------------------------------


def test_criar_preenche_o_condominio_com_o_do_contexto(repo, session, contexto):
    item = repo.criar({"nome": "Novo"})

    session.add.assert_called_once_with(item)
    assert item.condominio_id == contexto.condominio_id
    session.flush.assert_called_once()
    session.commit.assert_not_called()  # quem faz commit é o service


def test_criar_recusa_condominio_id_nos_dados(repo, session):
    with pytest.raises(CampoProtegido):
        repo.criar({"nome": "Novo", "condominio_id": uuid.uuid4()})

    session.add.assert_not_called()


# --- definição da classe -----------------------------------------------------------------


def test_subclasse_com_model_sem_condominio_id_falha_ao_definir_a_classe():
    with pytest.raises(TypeError, match="condominio_id"):

        class RepositorioInvalido(RepositorioDoCondominio[SemCondominio]):
            modelo = SemCondominio


def test_subclasse_com_atributo_de_outro_nome_para_condominio_id_falha():
    with pytest.raises(TypeError, match="condominio_id"):

        class RepositorioComAtributoRenomeado(RepositorioDoCondominio[AtributoRenomeado]):
            modelo = AtributoRenomeado


def test_subclasse_sem_declarar_o_modelo_falha_ao_definir_a_classe():
    with pytest.raises(TypeError, match="modelo"):

        class RepositorioSemModelo(RepositorioDoCondominio[Item]):
            pass


def test_a_base_so_oferece_metodos_que_aplicam_o_condominio():
    # R3: este teste obriga quem criar um método novo na base (ex.: um `get_by_id`) a pensar no
    # filtro e a atualizar a lista abaixo de propósito.
    publicos = {n for n in dir(RepositorioDoCondominio) if not n.startswith("_")}
    assert publicos == {"consulta", "listar", "obter", "criar", "atualizar", "remover"}
