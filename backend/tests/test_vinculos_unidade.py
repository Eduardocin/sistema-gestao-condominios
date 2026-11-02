import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    BlocoCondominio,
    ChaveAcesso,
    Condominio,
    EventoAuditoria,
    SolicitacaoVinculoUnidade,
    Unidade,
    Usuario,
    VinculoCondominio,
)
from app.db.session import get_session
from app.main import create_app
from app.modules.auth.security import hash_senha

pytestmark = pytest.mark.postgres

SENHA = "Senha#Forte123"


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
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def preparar_condominio(session: Session) -> tuple[Condominio, Usuario, Usuario, Unidade]:
    condominio = Condominio(
        id=uuid.uuid4(),
        nome=f"Condomínio de teste {uuid.uuid4().hex[:8]}",
        status="ativo",
        ativo=True,
    )
    morador = Usuario(
        id=uuid.uuid4(),
        nome="Morador de Teste",
        email=f"morador-{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=True,
        status_conta="ativo",
    )
    administrador = Usuario(
        id=uuid.uuid4(),
        nome="Administracao de Teste",
        email=f"administracao-{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=True,
        status_conta="ativo",
    )
    session.add_all([condominio, morador, administrador])
    session.flush()
    bloco = BlocoCondominio(condominio_id=condominio.id, nome="A")
    session.add(bloco)
    session.flush()
    unidade = Unidade(
        condominio_id=condominio.id,
        bloco_id=bloco.id,
        identificacao="A-01-01",
    )
    session.add_all(
        [
            unidade,
            VinculoCondominio(
                usuario_id=morador.id,
                condominio_id=condominio.id,
                perfil="morador",
                ativo=False,
            ),
            VinculoCondominio(
                usuario_id=administrador.id,
                condominio_id=condominio.id,
                perfil="administracao",
                ativo=True,
            ),
        ]
    )
    session.flush()
    return condominio, morador, administrador, unidade


def emitir_chave(session: Session, condominio_id: uuid.UUID) -> str:
    codigo = f"chave-de-teste-{uuid.uuid4().hex}"
    session.add(
        ChaveAcesso(
            id=uuid.uuid4(),
            condominio_id=condominio_id,
            codigo_hash=hashlib.sha256(codigo.encode()).hexdigest(),
            criada_por_usuario_id=None,
            expira_em=datetime.now(UTC) + timedelta(days=1),
        )
    )
    session.flush()
    return codigo


def token_login(client: TestClient, email: str, *, administracao: bool = False) -> str:
    corpo = {"identificador": email, "senha": SENHA}
    if administracao:
        corpo["nome_responsavel"] = "Pessoa Administradora"
    resposta = client.post("/api/v1/auth/login", json=corpo)
    assert resposta.status_code == 200
    return resposta.json()["access_token"]


def solicitar(client: TestClient, token: str, chave: str, *, responsavel_principal: bool = False):
    return client.post(
        "/api/v1/unidades/vinculos/solicitar",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "bloco": "A",
            "unidade": "A-01-01",
            "chave_acesso": chave,
            "responsavel_principal": responsavel_principal,
        },
    )


def aprovar(client: TestClient, token: str, solicitacao_id: str, *, nome_responsavel: str):
    return client.post(
        f"/api/v1/unidades/vinculos/{solicitacao_id}/aprovar",
        headers={"Authorization": f"Bearer {token}"},
        json={"nome_responsavel": nome_responsavel},
    )


def test_vinculo_pendente_nao_concede_acesso_e_aprovacao_libera_unidade(client, session):
    condominio, morador, administrador, unidade = preparar_condominio(session)
    chave = emitir_chave(session, condominio.id)
    token_morador = token_login(client, morador.email)
    token_administrador = token_login(client, administrador.email, administracao=True)

    resposta = solicitar(client, token_morador, chave, responsavel_principal=True)
    assert resposta.status_code == 201
    solicitacao_id = resposta.json()["solicitacao_id"]

    perfil_pendente = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_morador}"},
    )
    assert perfil_pendente.status_code == 200
    assert perfil_pendente.json()["condominio"] is None
    assert perfil_pendente.json()["unidades"] == []
    fila_sem_permissao = client.get(
        "/api/v1/unidades/vinculos/pendentes",
        headers={"Authorization": f"Bearer {token_morador}"},
    )
    assert fila_sem_permissao.status_code == 403
    selecao_pendente = client.post(
        "/api/v1/auth/selecionar-condominio",
        headers={"Authorization": f"Bearer {token_morador}"},
        json={"condominio_id": str(condominio.id)},
    )
    assert selecao_pendente.status_code == 404

    fila = client.get(
        "/api/v1/unidades/vinculos/pendentes",
        headers={"Authorization": f"Bearer {token_administrador}"},
    )
    assert fila.status_code == 200
    assert fila.json()[0]["id"] == solicitacao_id
    assert fila.json()[0]["unidade"] == "A-01-01"
    assert fila.json()[0]["responsavel_principal"] is True

    decisao = aprovar(
        client,
        token_administrador,
        solicitacao_id,
        nome_responsavel="Pessoa Administradora",
    )
    assert decisao.status_code == 200
    assert decisao.json()["status"] == "aprovado"
    assert decisao.json()["notificacao_registrada"] is True

    session.refresh(morador)
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == morador.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    assert vinculo is not None
    assert vinculo.ativo is True
    assert vinculo.unidade_id == unidade.id

    token_morador_aprovado = token_login(client, morador.email)
    perfil_aprovado = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_morador_aprovado}"},
    )
    assert perfil_aprovado.status_code == 200
    assert perfil_aprovado.json()["condominio"]["id"] == str(condominio.id)
    assert perfil_aprovado.json()["unidades"] == [
        {"id": str(unidade.id), "identificacao": "A-01-01"}
    ]

    eventos = session.scalars(
        select(EventoAuditoria).where(
            EventoAuditoria.recurso_id == solicitacao_id,
        )
    ).all()
    assert [evento.tipo_evento for evento in eventos].count("mudanca_permissao") == 2
    assert [evento.tipo_evento for evento in eventos].count("notificacao_condominio") == 1
    assert all(
        evento.nome_responsavel == "Pessoa Administradora"
        for evento in eventos
        if evento.perfil == "administracao"
    )


def test_solicitacao_duplicada_e_rejeicao_nao_ativam_vinculo(client, session):
    condominio, morador, administrador, _ = preparar_condominio(session)
    token_morador = token_login(client, morador.email)
    token_administrador = token_login(client, administrador.email, administracao=True)
    primeira_chave = emitir_chave(session, condominio.id)
    primeira = solicitar(client, token_morador, primeira_chave)
    assert primeira.status_code == 201

    motivo_vazio = client.post(
        f"/api/v1/unidades/vinculos/{primeira.json()['solicitacao_id']}/rejeitar",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={"motivo": "   ", "nome_responsavel": "Pessoa Administradora"},
    )
    assert motivo_vazio.status_code == 422

    segunda_chave = emitir_chave(session, condominio.id)
    duplicada = solicitar(client, token_morador, segunda_chave)
    assert duplicada.status_code == 409
    assert (
        session.scalar(
            select(ChaveAcesso).where(
                ChaveAcesso.codigo_hash == hashlib.sha256(segunda_chave.encode()).hexdigest()
            )
        )
        is None
    )

    solicitacao_id = primeira.json()["solicitacao_id"]
    rejeitada = client.post(
        f"/api/v1/unidades/vinculos/{solicitacao_id}/rejeitar",
        headers={"Authorization": f"Bearer {token_administrador}"},
        json={
            "motivo": "Comprovante de residência pendente",
            "nome_responsavel": "Pessoa Administradora",
        },
    )
    assert rejeitada.status_code == 200
    assert rejeitada.json()["status"] == "rejeitado"
    assert rejeitada.json()["notificacao_registrada"] is True

    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == morador.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    assert vinculo is not None and vinculo.ativo is False and vinculo.unidade_id is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(EventoAuditoria)
            .where(
                EventoAuditoria.recurso_id == solicitacao_id,
                EventoAuditoria.tipo_evento == "notificacao_condominio",
            )
        )
        == 1
    )


def test_apenas_uma_pessoa_pode_ser_responsavel_principal_por_unidade(client, session):
    condominio, morador, administrador, unidade = preparar_condominio(session)
    outro_morador = Usuario(
        id=uuid.uuid4(),
        nome="Outro Morador",
        email=f"morador-{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=True,
        status_conta="ativo",
    )
    terceiro_morador = Usuario(
        id=uuid.uuid4(),
        nome="Terceiro Morador",
        email=f"morador-{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=True,
        status_conta="ativo",
    )
    session.add_all([outro_morador, terceiro_morador])
    session.flush()
    session.add_all(
        [
            VinculoCondominio(
                usuario_id=outro_morador.id,
                condominio_id=condominio.id,
                perfil="morador",
                ativo=False,
            ),
            VinculoCondominio(
                usuario_id=terceiro_morador.id,
                condominio_id=condominio.id,
                perfil="morador",
                ativo=False,
            ),
        ]
    )
    session.flush()

    token_administrador = token_login(client, administrador.email, administracao=True)
    token_morador = token_login(client, morador.email)
    token_outro_morador = token_login(client, outro_morador.email)
    token_terceiro_morador = token_login(client, terceiro_morador.email)

    chave_um = emitir_chave(session, condominio.id)
    solicitacao_um = solicitar(client, token_morador, chave_um, responsavel_principal=True).json()[
        "solicitacao_id"
    ]
    aprovada_um = aprovar(
        client,
        token_administrador,
        solicitacao_um,
        nome_responsavel="Pessoa Administradora",
    )
    assert aprovada_um.status_code == 200

    chave_dois = emitir_chave(session, condominio.id)
    solicitacao_dois = solicitar(
        client, token_outro_morador, chave_dois, responsavel_principal=False
    ).json()["solicitacao_id"]
    aprovada_dois = aprovar(
        client,
        token_administrador,
        solicitacao_dois,
        nome_responsavel="Pessoa Administradora",
    )
    assert aprovada_dois.status_code == 200
    assert session.get(SolicitacaoVinculoUnidade, uuid.UUID(solicitacao_dois)).status == "aprovado"
    assert (
        unidade.id == session.get(SolicitacaoVinculoUnidade, uuid.UUID(solicitacao_um)).unidade_id
    )

    chave_tres = emitir_chave(session, condominio.id)
    solicitacao_tres = solicitar(
        client, token_terceiro_morador, chave_tres, responsavel_principal=True
    ).json()["solicitacao_id"]
    aprovada_tres = aprovar(
        client,
        token_administrador,
        solicitacao_tres,
        nome_responsavel="Pessoa Administradora",
    )
    assert aprovada_tres.status_code == 409
    assert session.get(SolicitacaoVinculoUnidade, uuid.UUID(solicitacao_tres)).status == "pendente"
