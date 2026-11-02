import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import ChaveAcesso, Condominio, EventoAuditoria, Usuario, VinculoCondominio
from app.db.session import get_session
from app.main import create_app
from app.modules.auth.security import hash_senha
from app.modules.usuarios.validation import normalizar_cpf, validar_senha_forte

pytestmark = pytest.mark.postgres

SENHA_FORTE = "Senha#Forte123"
CPF_VALIDO = "52998224725"
CHAVE_TESTE = "chave-teste-valida-condominio-morador-0001"


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


@pytest.fixture
def client(session):
    condominio = Condominio(nome=f"Condomínio de teste {uuid.uuid4().hex[:8]}", status="ativo")
    session.add(condominio)
    session.flush()
    session.add(
        ChaveAcesso(
            id=uuid.uuid4(),
            condominio_id=condominio.id,
            codigo_hash=hashlib.sha256(CHAVE_TESTE.encode()).hexdigest(),
            expira_em=datetime.now(UTC) + timedelta(days=1),
        )
    )
    session.flush()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


def cadastro(email: str, cpf: str = CPF_VALIDO) -> dict[str, str]:
    return {
        "nome": "Ana Martins",
        "email": email,
        "cpf": cpf,
        "senha": SENHA_FORTE,
        "chave_acesso": CHAVE_TESTE,
    }


def criar_usuario_ativo(session: Session, *, perfil: str = "morador") -> tuple[Usuario, str | None]:
    usuario = Usuario(
        nome="Perfil existente",
        email=f"{uuid.uuid4().hex}@exemplo.test",
        cpf=CPF_VALIDO,
        senha_hash=hash_senha(SENHA_FORTE),
        ativo=True,
        status_conta="ativo",
    )
    condominio = Condominio(nome=f"Condomínio {uuid.uuid4().hex[:8]}")
    session.add_all([usuario, condominio])
    session.flush()
    session.add(
        VinculoCondominio(
            usuario_id=usuario.id,
            condominio_id=condominio.id,
            perfil=perfil,
            ativo=True,
        )
    )
    session.flush()
    return usuario, str(condominio.id)


def test_validadores_de_cpf_e_senha_forte():
    assert normalizar_cpf("529.982.247-25") == CPF_VALIDO
    assert validar_senha_forte(SENHA_FORTE) == SENHA_FORTE

    with pytest.raises(ValueError, match="CPF válido"):
        normalizar_cpf("111.111.111-11")
    with pytest.raises(ValueError, match="CPF válido"):
        normalizar_cpf("529.982.247-24")
    with pytest.raises(ValueError, match="12 caracteres"):
        validar_senha_forte("Senha123")


def test_cadastro_de_morador_cria_conta_pendente_e_audita(client, session):
    email = f"{uuid.uuid4().hex}@exemplo.test"

    resposta = client.post("/api/v1/usuarios/moradores", json=cadastro(email))

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["email"] == email
    assert corpo["cpf"] == CPF_VALIDO
    assert corpo["status_conta"] == "pendente"
    usuario = session.scalar(select(Usuario).where(Usuario.email == email))
    assert usuario is not None
    assert usuario.ativo is False
    assert usuario.senha_hash != SENHA_FORTE
    eventos = session.scalars(
        select(EventoAuditoria).where(
            EventoAuditoria.tipo_evento == "criacao_conta",
            EventoAuditoria.usuario_id == usuario.id,
        )
    ).all()
    assert len(eventos) == 1
    assert eventos[0].perfil == "morador"
    assert eventos[0].ip is not None


def test_cadastro_de_administracao_cria_vinculo_pendente_e_audita(client, session):
    condominio = Condominio(nome=f"Condomínio {uuid.uuid4().hex[:8]}")
    session.add(condominio)
    session.flush()
    email = f"{uuid.uuid4().hex}@exemplo.test"

    resposta = client.post(
        "/api/v1/usuarios/administracao",
        json={**cadastro(email), "condominio_id": str(condominio.id)},
    )

    assert resposta.status_code == 201
    usuario = session.scalar(select(Usuario).where(Usuario.email == email))
    assert usuario is not None
    assert usuario.status_conta == "pendente"
    assert usuario.ativo is False
    vinculo = session.scalar(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == usuario.id)
    )
    assert vinculo is not None
    assert vinculo.perfil == "administracao"
    assert vinculo.ativo is False
    evento = session.scalar(
        select(EventoAuditoria).where(
            EventoAuditoria.tipo_evento == "criacao_conta",
            EventoAuditoria.usuario_id == usuario.id,
        )
    )
    assert evento is not None
    assert evento.conta_compartilhada is True
    assert evento.nome_responsavel == "Ana Martins"
    assert evento.condominio_id == condominio.id


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("cpf", "11111111111"),
        ("cpf", "52998224724"),
        ("senha", "fraca"),
        ("email", "nao-e-email"),
    ],
)
def test_cadastro_rejeita_dados_invalidos(client, campo, valor):
    payload = cadastro(f"{uuid.uuid4().hex}@exemplo.test")
    payload[campo] = valor

    resposta = client.post("/api/v1/usuarios/moradores", json=payload)

    assert resposta.status_code == 422


def test_cadastro_rejeita_email_ou_cpf_duplicado(client):
    email = f"{uuid.uuid4().hex}@exemplo.test"
    assert client.post("/api/v1/usuarios/moradores", json=cadastro(email)).status_code == 201

    email_duplicado = client.post(
        "/api/v1/usuarios/moradores",
        json=cadastro(email, cpf="11144477735"),
    )
    cpf_duplicado = client.post(
        "/api/v1/usuarios/moradores",
        json=cadastro(f"{uuid.uuid4().hex}@exemplo.test"),
    )

    assert email_duplicado.status_code == 409
    assert cpf_duplicado.status_code == 409


def test_conta_pendente_nao_consegue_fazer_login(client):
    email = f"{uuid.uuid4().hex}@exemplo.test"
    cadastro_resposta = client.post("/api/v1/usuarios/moradores", json=cadastro(email))
    assert cadastro_resposta.status_code == 201

    resposta = client.post(
        "/api/v1/auth/login",
        json={"identificador": email, "senha": SENHA_FORTE},
    )

    assert resposta.status_code == 401


def test_usuario_consulta_e_edita_apenas_o_proprio_perfil_com_auditoria(client, session):
    usuario, condominio_id = criar_usuario_ativo(session)
    email_anterior = usuario.email
    login = client.post(
        "/api/v1/auth/login",
        json={"identificador": usuario.email, "senha": SENHA_FORTE},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    consulta = client.get("/api/v1/usuarios/me", headers=headers)
    edicao = client.patch(
        "/api/v1/usuarios/me",
        headers=headers,
        json={"nome": "Ana Atualizada", "email": "ana-atualizada@exemplo.test"},
    )

    assert consulta.status_code == 200
    assert consulta.json()["id"] == str(usuario.id)
    assert edicao.status_code == 200
    assert edicao.json()["nome"] == "Ana Atualizada"
    evento = session.scalar(
        select(EventoAuditoria).where(
            EventoAuditoria.tipo_evento == "edicao_conta",
            EventoAuditoria.usuario_id == usuario.id,
        )
    )
    assert evento is not None
    assert evento.condominio_id == uuid.UUID(condominio_id)
    assert evento.dados_antes == {"nome": "Perfil existente", "email": email_anterior}
    assert evento.dados_depois == {
        "nome": "Ana Atualizada",
        "email": "ana-atualizada@exemplo.test",
    }


def test_edicao_de_conta_compartilhada_exige_responsavel(client, session):
    usuario, _ = criar_usuario_ativo(session, perfil="funcionario")
    login = client.post(
        "/api/v1/auth/login",
        json={
            "identificador": usuario.email,
            "senha": SENHA_FORTE,
            "nome_responsavel": "Responsável inicial",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resposta = client.patch(
        "/api/v1/usuarios/me",
        headers=headers,
        json={"nome": "Nome atualizado"},
    )

    assert resposta.status_code == 422
    assert (
        session.scalar(
            select(func.count())
            .select_from(EventoAuditoria)
            .where(
                EventoAuditoria.tipo_evento == "edicao_conta",
                EventoAuditoria.usuario_id == usuario.id,
            )
        )
        == 0
    )
