import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Condominio, Unidade, Usuario, VinculoCondominio

pytestmark = pytest.mark.postgres


@pytest.fixture
def session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        pytest.fail("Estes testes exigem PostgreSQL real")
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


def create_context(session):
    user = Usuario(nome="Teste", email=f"{uuid.uuid4()}@example.test")
    first = Condominio(nome="Condomínio A")
    second = Condominio(nome="Condomínio B")
    session.add_all([user, first, second])
    session.flush()
    unit = Unidade(condominio_id=first.id, identificacao="Bloco A / 101")
    session.add(unit)
    session.flush()
    return user, first, second, unit


def test_user_can_belong_to_multiple_condominiums(session):
    user, first, second, unit = create_context(session)
    session.add_all(
        [
            VinculoCondominio(
                usuario_id=user.id, condominio_id=first.id, unidade_id=unit.id, perfil="morador"
            ),
            VinculoCondominio(usuario_id=user.id, condominio_id=second.id, perfil="funcionario"),
        ]
    )
    session.flush()
    assert (
        session.scalar(
            text("SELECT count(*) FROM vinculos_condominio WHERE usuario_id = :id"), {"id": user.id}
        )
        == 2
    )
    assert user.administrador_plataforma is False


def test_membership_rejects_unit_from_another_condominium(session):
    user, first, second, unit = create_context(session)
    session.add(
        VinculoCondominio(
            usuario_id=user.id, condominio_id=second.id, unidade_id=unit.id, perfil="morador"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_membership_cannot_grant_platform_role(session):
    user, first, second, unit = create_context(session)
    session.add(VinculoCondominio(usuario_id=user.id, condominio_id=first.id, perfil="plataforma"))
    with pytest.raises(IntegrityError) as error:
        session.flush()
    assert error.value.orig.diag.constraint_name == "ck_vinculos_condominio_perfil_local"


def test_duplicate_membership_is_rejected(session):
    user, first, second, unit = create_context(session)
    for role in ("morador", "funcionario"):
        session.add(VinculoCondominio(usuario_id=user.id, condominio_id=first.id, perfil=role))
    with pytest.raises(IntegrityError):
        session.flush()
