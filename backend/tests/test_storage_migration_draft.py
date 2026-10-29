import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.postgres


def load_draft():
    path = Path(__file__).parents[1] / "alembic/drafts/arquivos_storage.py"
    assert path.exists(), "Rascunho de arquivos ainda não foi preparado"
    spec = importlib.util.spec_from_file_location("arquivos_draft", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_storage_draft_remains_outside_active_migrations():
    draft = load_draft()
    assert draft.down_revision == "PENDENTE_TASK_81"
    versions = Path(__file__).parents[1] / "alembic/versions"
    assert not any("arquivos_storage" in p.name for p in versions.iterdir())


@pytest.fixture
def database():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para um PostgreSQL dedicado")
    engine = sa.create_engine(url)
    assert engine.dialect.name == "postgresql"
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                schema = "storage_draft_" + uuid4().hex
                connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
                connection.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
                for table in ["usuarios", "condominios"]:
                    connection.execute(sa.text(f"CREATE TABLE {table} (id uuid PRIMARY KEY)"))
                user, tenant = uuid4(), uuid4()
                connection.execute(sa.text("INSERT INTO usuarios VALUES (:id)"), {"id": user})
                connection.execute(sa.text("INSERT INTO condominios VALUES (:id)"), {"id": tenant})
                draft = load_draft()
                with Operations.context(MigrationContext.configure(connection)):
                    draft.upgrade()
                    yield connection, user, tenant, draft
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def values(user, tenant, **changes):
    data = dict(
        id=uuid4(),
        condominio_id=tenant,
        chave_storage="condominio/teste/encomendas/" + uuid4().hex,
        nome_original="foto.png",
        tipo_mime="image/png",
        tamanho_bytes=80,
        enviado_por_usuario_id=user,
    )
    data.update(changes)
    return data


def insert(connection, data):
    keys = list(data)
    connection.execute(
        sa.text(
            "INSERT INTO arquivos ("
            + ",".join(keys)
            + ") VALUES ("
            + ",".join(":" + k for k in keys)
            + ")"
        ),
        data,
    )


def test_storage_draft_upgrade_and_downgrade(database):
    connection, user, tenant, draft = database
    insert(connection, values(user, tenant))
    assert connection.scalar(sa.text("SELECT count(*) FROM arquivos")) == 1
    assert connection.scalar(sa.text("SELECT criado_em FROM arquivos")) is not None
    with Operations.context(MigrationContext.configure(connection)):
        draft.downgrade()
    assert not sa.inspect(connection).has_table("arquivos")
    assert connection.scalar(sa.text("SELECT count(*) FROM usuarios")) == 1


@pytest.mark.parametrize(
    "changes",
    [
        dict(tamanho_bytes=0),
        dict(tamanho_bytes=-1),
        dict(enviado_por_usuario_id=uuid4()),
        dict(condominio_id=uuid4()),
    ],
)
def test_storage_draft_rejects_invalid_metadata(database, changes):
    connection, user, tenant, _ = database
    with pytest.raises(IntegrityError), connection.begin_nested():
        insert(connection, values(user, tenant, **changes))


def test_storage_draft_rejects_duplicate_object_key(database):
    connection, user, tenant, _ = database
    data = values(user, tenant)
    insert(connection, data)
    with pytest.raises(IntegrityError), connection.begin_nested():
        insert(connection, {**data, "id": uuid4()})


def test_storage_draft_fixture_does_not_leave_a_schema():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para PostgreSQL dedicado")
    lifecycle = database.__wrapped__()
    connection, _, _, _ = next(lifecycle)
    schema = connection.scalar(sa.text("SELECT current_schema()"))
    with pytest.raises(StopIteration):
        next(lifecycle)
    engine = sa.create_engine(url)
    try:
        with engine.connect() as observer:
            assert not observer.scalar(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
                {"schema": schema},
            )
    finally:
        engine.dispose()
