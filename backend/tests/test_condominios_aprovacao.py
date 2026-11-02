import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChaveAcesso,
    Condominio,
    EventoAuditoria,
    Usuario,
    VinculoCondominio,
)
from app.db.session import get_session
from app.main import create_app
from app.modules.auth.security import hash_senha

pytestmark = pytest.mark.postgres

SENHA = "Senha#Forte123"
TOKEN_STATUS = "token-status-solicitacao-teste-0123456789"


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


def criar_solicitacao(session: Session) -> tuple[Condominio, Usuario]:
    solicitante = Usuario(
        id=uuid.uuid4(),
        nome="Administração solicitante",
        email=f"{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=False,
        status_conta="pendente",
    )
    condominio = Condominio(
        id=uuid.uuid4(),
        nome=f"Condomínio pendente {uuid.uuid4().hex[:8]}",
        status="pendente",
        ativo=False,
        solicitante_id=solicitante.id,
        token_status_solicitacao_hash=hashlib.sha256(TOKEN_STATUS.encode()).hexdigest(),
    )
    session.add(solicitante)
    session.flush()
    session.add(condominio)
    session.flush()
    session.add(
        VinculoCondominio(
            id=uuid.uuid4(),
            usuario_id=solicitante.id,
            condominio_id=condominio.id,
            perfil="administracao",
            ativo=False,
        )
    )
    session.flush()
    return condominio, solicitante


def criar_administrador(session: Session, *, plataforma: bool = True) -> Usuario:
    administrador = Usuario(
        id=uuid.uuid4(),
        nome="ADM da Plataforma",
        email=f"{uuid.uuid4().hex}@exemplo.test",
        cpf=None,
        senha_hash=hash_senha(SENHA),
        ativo=True,
        status_conta="ativo",
        administrador_plataforma=plataforma,
    )
    session.add(administrador)
    session.flush()
    return administrador


def autenticar(client: TestClient, email: str) -> dict[str, str]:
    resposta = client.post(
        "/api/v1/auth/login",
        json={"identificador": email, "senha": SENHA},
    )
    assert resposta.status_code == 200
    return {"Authorization": f"Bearer {resposta.json()['access_token']}"}


def test_listagem_pendente_e_decisoes_sao_exclusivas_da_plataforma(client, session):
    condominio, _ = criar_solicitacao(session)
    usuario = criar_administrador(session, plataforma=False)
    headers = autenticar(client, usuario.email)

    resposta = client.get("/api/v1/condominios/aprovacoes/pendentes", headers=headers)

    assert resposta.status_code == 403
    assert session.get(Condominio, condominio.id).status == "pendente"


def test_aprovacao_ativa_conta_gera_chave_e_audita_decisao_e_notificacao(client, session):
    condominio, solicitante = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)

    lista = client.get("/api/v1/condominios/aprovacoes/pendentes", headers=headers)
    resposta = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers)

    assert lista.status_code == 200
    assert any(item["id"] == str(condominio.id) for item in lista.json())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ativo"
    assert len(corpo["chave_acesso"]) >= 32
    assert datetime.fromisoformat(corpo["expira_em"].replace("Z", "+00:00")) > datetime.now(UTC)

    session.refresh(condominio)
    session.refresh(solicitante)
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == solicitante.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    chave = session.scalar(select(ChaveAcesso).where(ChaveAcesso.condominio_id == condominio.id))
    assert condominio.status == "ativo"
    assert condominio.ativo is True
    assert solicitante.status_conta == "ativo"
    assert solicitante.ativo is True
    assert vinculo is not None and vinculo.ativo is True
    assert chave is not None
    assert chave.codigo_hash == hashlib.sha256(corpo["chave_acesso"].encode()).hexdigest()
    assert corpo["chave_acesso"] not in chave.codigo_hash
    eventos = session.scalars(
        select(EventoAuditoria).where(
            EventoAuditoria.condominio_id == condominio.id,
        )
    ).all()
    assert {evento.tipo_evento for evento in eventos} == {
        "aprovacao",
        "notificacao_condominio",
    }


def test_rejeicao_exige_motivo_e_exibe_razao_ao_solicitante(client, session):
    condominio, solicitante = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)

    sem_motivo = client.post(f"/api/v1/condominios/{condominio.id}/rejeitar", headers=headers)
    vazio = client.post(
        f"/api/v1/condominios/{condominio.id}/rejeitar",
        headers=headers,
        json={"motivo": "   "},
    )
    rejeitado = client.post(
        f"/api/v1/condominios/{condominio.id}/rejeitar",
        headers=headers,
        json={"motivo": "Documentação incompleta"},
    )
    status_solicitacao = client.get(
        f"/api/v1/condominios/solicitacoes/{condominio.id}",
        headers={"X-Token-Solicitacao": TOKEN_STATUS},
    )

    assert sem_motivo.status_code == 422
    assert vazio.status_code == 422
    assert rejeitado.status_code == 200
    assert rejeitado.json()["motivo_rejeicao"] == "Documentação incompleta"
    assert rejeitado.json()["notificacao_registrada"] is True
    assert status_solicitacao.status_code == 200
    assert status_solicitacao.json()["status"] == "rejeitado"
    assert status_solicitacao.json()["motivo_rejeicao"] == "Documentação incompleta"
    session.refresh(solicitante)
    assert solicitante.status_conta == "rejeitado"
    assert solicitante.ativo is False
    assert (
        session.scalar(
            select(func.count())
            .select_from(EventoAuditoria)
            .where(
                EventoAuditoria.condominio_id == condominio.id,
                EventoAuditoria.tipo_evento == "rejeicao",
            )
        )
        == 1
    )


def test_chave_e_validada_e_consumida_uma_unica_vez_no_cadastro_morador(client, session):
    condominio, _ = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)
    aprovacao = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers)
    chave = aprovacao.json()["chave_acesso"]

    validacao = client.post(
        "/api/v1/condominios/chaves/validar",
        json={"chave_acesso": chave},
    )
    cadastro = client.post(
        "/api/v1/usuarios/moradores",
        json={
            "nome": "Morador da Chave",
            "email": f"{uuid.uuid4().hex}@exemplo.test",
            "cpf": "52998224725",
            "senha": SENHA,
            "chave_acesso": chave,
        },
    )
    repetido = client.post(
        "/api/v1/usuarios/moradores",
        json={
            "nome": "Outro Morador",
            "email": f"{uuid.uuid4().hex}@exemplo.test",
            "cpf": "11144477735",
            "senha": SENHA,
            "chave_acesso": chave,
        },
    )
    validacao_apos_uso = client.post(
        "/api/v1/condominios/chaves/validar",
        json={"chave_acesso": chave},
    )

    assert aprovacao.status_code == 200
    assert validacao.status_code == 200 and validacao.json()["valida"] is True
    assert validacao.json()["condominio_id"] == str(condominio.id)
    assert cadastro.status_code == 201
    assert repetido.status_code == 422
    assert validacao_apos_uso.status_code == 200
    assert validacao_apos_uso.json()["valida"] is False
    conta = session.scalar(select(Usuario).where(Usuario.email == cadastro.json()["email"]))
    assert conta is not None and conta.status_conta == "pendente"
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == conta.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    assert vinculo is not None and vinculo.perfil == "morador" and not vinculo.ativo


def test_cadastro_funcionario_tambem_exige_e_consume_chave(client, session):
    condominio, _ = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)
    chave = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers).json()[
        "chave_acesso"
    ]

    resposta = client.post(
        "/api/v1/usuarios/funcionarios",
        json={
            "nome": "Conta da Portaria",
            "email": f"{uuid.uuid4().hex}@exemplo.test",
            "cpf": "11144477735",
            "senha": SENHA,
            "chave_acesso": chave,
            "nome_responsavel": "Funcionário Responsável",
        },
    )

    assert resposta.status_code == 201
    usuario = session.scalar(select(Usuario).where(Usuario.email == resposta.json()["email"]))
    assert usuario is not None
    assert usuario.status_conta == "pendente"
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == usuario.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    assert vinculo is not None and vinculo.perfil == "funcionario" and not vinculo.ativo
    evento = session.scalar(
        select(EventoAuditoria).where(
            EventoAuditoria.usuario_id == usuario.id,
            EventoAuditoria.tipo_evento == "criacao_conta",
        )
    )
    assert evento is not None
    assert evento.nome_responsavel == "Funcionário Responsável"


def test_regeneracao_revoga_chave_anterior_e_emite_nova(client, session):
    condominio, _ = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)
    primeira = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers).json()[
        "chave_acesso"
    ]
    segunda = client.post(f"/api/v1/condominios/{condominio.id}/chaves/regenerar", headers=headers)

    assert segunda.status_code == 200
    assert segunda.json()["chave_acesso"] != primeira
    antiga_validacao = client.post(
        "/api/v1/condominios/chaves/validar",
        json={"chave_acesso": primeira},
    )
    nova_validacao = client.post(
        "/api/v1/condominios/chaves/validar",
        json={"chave_acesso": segunda.json()["chave_acesso"]},
    )
    assert antiga_validacao.json()["valida"] is False
    assert nova_validacao.json()["valida"] is True
    antiga = session.scalar(
        select(ChaveAcesso).where(
            ChaveAcesso.codigo_hash == hashlib.sha256(primeira.encode()).hexdigest()
        )
    )
    assert antiga is not None and antiga.revogada_em is not None


def test_revogacao_desativa_chave_sem_gerar_substituta(client, session):
    condominio, _ = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)
    chave = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers).json()[
        "chave_acesso"
    ]

    resposta = client.post(
        f"/api/v1/condominios/{condominio.id}/chaves/revogar",
        headers=headers,
    )
    validacao = client.post(
        "/api/v1/condominios/chaves/validar",
        json={"chave_acesso": chave},
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"condominio_id": str(condominio.id), "revogada": True}
    assert validacao.status_code == 200 and validacao.json()["valida"] is False


def test_chave_invalida_ou_sem_chave_bloqueia_cadastro(client, session):
    payload = {
        "nome": "Morador Sem Chave",
        "email": f"{uuid.uuid4().hex}@exemplo.test",
        "cpf": "52998224725",
        "senha": SENHA,
    }
    sem_chave = client.post("/api/v1/usuarios/moradores", json=payload)
    invalida = client.post(
        "/api/v1/usuarios/moradores",
        json={**payload, "chave_acesso": "chave-invalida-" + "x" * 20},
    )

    assert sem_chave.status_code == 422
    assert invalida.status_code == 422
    assert session.scalar(select(Usuario).where(Usuario.email == payload["email"])) is None


def test_status_do_solicitante_exige_token_valido(client, session):
    condominio, _ = criar_solicitacao(session)

    resposta = client.get(
        f"/api/v1/condominios/solicitacoes/{condominio.id}",
        headers={"X-Token-Solicitacao": "token-errado-para-esta-solicitacao-123456"},
    )

    assert resposta.status_code == 404


def test_chave_expirada_nao_pode_ser_usada(client, session):
    condominio, _ = criar_solicitacao(session)
    administrador = criar_administrador(session)
    headers = autenticar(client, administrador.email)
    chave = client.post(f"/api/v1/condominios/{condominio.id}/aprovar", headers=headers).json()[
        "chave_acesso"
    ]
    registro = session.scalar(
        select(ChaveAcesso).where(
            ChaveAcesso.codigo_hash == hashlib.sha256(chave.encode()).hexdigest()
        )
    )
    assert registro is not None
    registro.expira_em = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()

    validacao = client.post("/api/v1/condominios/chaves/validar", json={"chave_acesso": chave})
    cadastro = client.post(
        "/api/v1/usuarios/moradores",
        json={
            "nome": "Morador Chave Expirada",
            "email": f"{uuid.uuid4().hex}@exemplo.test",
            "cpf": "52998224725",
            "senha": SENHA,
            "chave_acesso": chave,
        },
    )

    assert validacao.json()["valida"] is False
    assert cadastro.status_code == 422
