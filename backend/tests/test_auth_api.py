"""Testes da API de autenticação contra um PostgreSQL migrado (TEST_DATABASE_URL)."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.auth.rate_limit import get_login_rate_limiter
from app.modules.auth.security import hash_senha
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario

pytestmark = pytest.mark.postgres

SENHA = "Senha#Forte123"
# O hash é caro de propósito (argon2), então geramos um só para a suíte inteira.
HASH = hash_senha(SENHA)


@pytest.fixture
def session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        # Tudo o que o teste (e o service) gravou é desfeito aqui.
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    get_login_rate_limiter().resetar()
    with TestClient(app) as client:
        yield client
    get_login_rate_limiter().resetar()


def criar_usuario(session, *, ativo=True, adm=False, senha_hash=HASH, sessao_versao=1) -> Usuario:
    usuario = Usuario(
        nome="Ana Martins",
        email=f"{uuid.uuid4().hex[:12]}@exemplo.test",
        ativo=ativo,
        administrador_plataforma=adm,
        senha_hash=senha_hash,
        sessao_versao=sessao_versao,
    )
    session.add(usuario)
    session.flush()
    return usuario


def criar_condominio(session, nome="Residencial Aurora", ativo=True) -> Condominio:
    condominio = Condominio(nome=nome, status="ativo" if ativo else "desativado")
    session.add(condominio)
    session.flush()
    return condominio


def vincular(session, usuario, condominio, perfil="morador", unidade=None, ativo=True):
    vinculo = VinculoCondominio(
        usuario_id=usuario.id,
        condominio_id=condominio.id,
        unidade_id=unidade.id if unidade else None,
        perfil=perfil,
        ativo=ativo,
    )
    session.add(vinculo)
    session.flush()
    return vinculo


def entrar(client, usuario, senha=SENHA):
    return client.post("/api/v1/auth/login", json={"identificador": usuario.email, "senha": senha})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- login -----------------------------------------------------------------


def test_login_com_um_condominio_ja_devolve_token_com_cid(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    vincular(session, usuario, condominio)

    resposta = entrar(client, usuario)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["expires_in"] == 900
    assert corpo["requer_selecao"] is False
    assert corpo["condominio"]["id"] == str(condominio.id)
    assert corpo["condominio"]["perfil"] == "morador"
    assert corpo["usuario"]["email"] == usuario.email
    assert "senha_hash" not in resposta.text


def test_login_aceita_email_com_maiusculas_e_espacos(client, session):
    usuario = criar_usuario(session)
    resposta = client.post(
        "/api/v1/auth/login",
        json={"identificador": f"  {usuario.email.upper()} ", "senha": SENHA},
    )
    assert resposta.status_code == 200


def test_login_com_varios_condominios_pede_selecao(client, session):
    usuario = criar_usuario(session)
    a, b = criar_condominio(session, "Aurora"), criar_condominio(session, "Boa Vista")
    vincular(session, usuario, a)
    vincular(session, usuario, b, perfil="funcionario")

    corpo = entrar(client, usuario).json()

    assert corpo["requer_selecao"] is True
    assert corpo["condominio"] is None
    assert [c["nome"] for c in corpo["condominios"]] == ["Aurora", "Boa Vista"]


def test_login_sem_vinculo_devolve_token_sem_condominio(client, session):
    corpo = entrar(client, criar_usuario(session)).json()
    assert corpo["condominio"] is None
    assert corpo["condominios"] == []
    assert corpo["requer_selecao"] is False


def test_login_do_adm_da_plataforma(client, session):
    corpo = entrar(client, criar_usuario(session, adm=True)).json()
    assert corpo["administrador_plataforma"] is True
    assert corpo["condominios"] == []


@pytest.mark.parametrize(
    "motivo", ["senha_errada", "email_inexistente", "conta_inativa", "sem_senha"]
)
def test_falhas_de_credencial_dao_a_mesma_resposta(client, session, motivo):
    usuario = criar_usuario(
        session, ativo=motivo != "conta_inativa", senha_hash=None if motivo == "sem_senha" else HASH
    )
    email = "ninguem@exemplo.test" if motivo == "email_inexistente" else usuario.email
    senha = "senha-errada-123" if motivo == "senha_errada" else SENHA

    resposta = client.post("/api/v1/auth/login", json={"identificador": email, "senha": senha})

    assert resposta.status_code == 401
    assert resposta.json() == {
        "error": {"code": "not_authenticated", "message": "E-mail ou senha incorretos."}
    }


def test_login_com_corpo_invalido_da_422(client):
    resposta = client.post("/api/v1/auth/login", json={"identificador": "a@b.co"})
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"


def test_login_bloqueia_apos_varias_falhas(client, session):
    usuario = criar_usuario(session)
    for _ in range(5):
        assert entrar(client, usuario, senha="errada-123").status_code == 401

    # Agora até a senha certa é barrada, até o bloqueio passar.
    resposta = entrar(client, usuario)

    assert resposta.status_code == 429
    assert resposta.json()["error"]["code"] == "too_many_attempts"
    assert int(resposta.headers["retry-after"]) > 0


def test_login_bem_sucedido_zera_o_contador(client, session):
    usuario = criar_usuario(session)
    for _ in range(4):
        entrar(client, usuario, senha="errada-123")
    assert entrar(client, usuario).status_code == 200
    # Se não zerasse, esta falha seria a 5ª e já bloquearia.
    assert entrar(client, usuario, senha="errada-123").status_code == 401
    assert entrar(client, usuario).status_code == 200


def test_condominio_fora_do_ar_nao_libera_morador_mas_libera_administracao(client, session):
    morador, administracao = criar_usuario(session), criar_usuario(session)
    condominio = criar_condominio(session, ativo=False)
    vincular(session, morador, condominio, perfil="morador")
    vincular(session, administracao, condominio, perfil="administracao")

    corpo_morador = entrar(client, morador).json()
    corpo_adm = entrar(client, administracao).json()

    assert corpo_morador["condominio"] is None
    assert corpo_morador["condominios"][0]["status"] == "desativado"
    assert corpo_adm["condominio"]["id"] == str(condominio.id)


# --- selecionar condomínio ------------------------------------------------


def test_selecionar_condominio_emite_token_com_cid(client, session):
    usuario = criar_usuario(session)
    a, b = criar_condominio(session, "Aurora"), criar_condominio(session, "Boa Vista")
    vincular(session, usuario, a)
    vincular(session, usuario, b)
    token = entrar(client, usuario).json()["access_token"]

    resposta = client.post(
        "/api/v1/auth/selecionar-condominio",
        json={"condominio_id": str(b.id)},
        headers=bearer(token),
    )

    assert resposta.status_code == 200
    assert resposta.json()["condominio"]["id"] == str(b.id)
    me = client.get("/api/v1/auth/me", headers=bearer(resposta.json()["access_token"]))
    assert me.json()["condominio"]["nome"] == "Boa Vista"


def test_selecionar_condominio_de_outro_tenant_da_404(client, session):
    usuario = criar_usuario(session)
    meu, alheio = criar_condominio(session, "Meu"), criar_condominio(session, "Alheio")
    vincular(session, usuario, meu)
    token = entrar(client, usuario).json()["access_token"]

    resposta = client.post(
        "/api/v1/auth/selecionar-condominio",
        json={"condominio_id": str(alheio.id)},
        headers=bearer(token),
    )

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "not_found"


def test_selecionar_condominio_fora_do_ar_da_403_para_morador(client, session):
    usuario = criar_usuario(session)
    condominio = criar_condominio(session, ativo=False)
    vincular(session, usuario, condominio)
    token = entrar(client, usuario).json()["access_token"]

    resposta = client.post(
        "/api/v1/auth/selecionar-condominio",
        json={"condominio_id": str(condominio.id)},
        headers=bearer(token),
    )

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


# --- /me e proteção por token ---------------------------------------------


def test_me_sem_token_da_401(client):
    resposta = client.get("/api/v1/auth/me")
    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "not_authenticated"
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_me_com_token_invalido_da_401(client):
    resposta = client.get("/api/v1/auth/me", headers=bearer("lixo"))
    assert resposta.status_code == 401


def test_me_do_morador_lista_a_unidade_do_condominio(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    unidade = Unidade(condominio_id=condominio.id, identificacao="Bloco A / 101")
    session.add(unidade)
    session.flush()
    vincular(session, usuario, condominio, unidade=unidade)
    token = entrar(client, usuario).json()["access_token"]

    corpo = client.get("/api/v1/auth/me", headers=bearer(token)).json()

    assert corpo["usuario"]["id"] == str(usuario.id)
    assert corpo["unidades"] == [{"id": str(unidade.id), "identificacao": "Bloco A / 101"}]


def test_perfil_do_me_vem_do_banco_e_nao_do_token(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    vinculo = vincular(session, usuario, condominio, perfil="morador")
    token = entrar(client, usuario).json()["access_token"]

    vinculo.perfil = "funcionario"  # o perfil mudou depois que o token foi emitido
    session.flush()

    corpo = client.get("/api/v1/auth/me", headers=bearer(token)).json()
    assert corpo["condominio"]["perfil"] == "funcionario"


def test_vinculo_removido_derruba_o_acesso_ao_condominio(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    vinculo = vincular(session, usuario, condominio)
    token = entrar(client, usuario).json()["access_token"]

    vinculo.ativo = False
    session.flush()

    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 403


def test_trocar_sessao_versao_derruba_o_token(client, session):
    usuario = criar_usuario(session)
    token = entrar(client, usuario).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200

    usuario.sessao_versao += 1
    session.flush()

    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_conta_desativada_perde_o_acesso_na_hora(client, session):
    usuario = criar_usuario(session)
    token = entrar(client, usuario).json()["access_token"]

    usuario.ativo = False
    session.flush()

    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_refresh_token_nao_serve_como_access_token(client, session):
    refresh = entrar(client, criar_usuario(session)).json()["refresh_token"]
    assert client.get("/api/v1/auth/me", headers=bearer(refresh)).status_code == 401


# --- refresh ----------------------------------------------------------------


def test_refresh_emite_novo_access_token(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    vincular(session, usuario, condominio)
    refresh = entrar(client, usuario).json()["refresh_token"]

    resposta = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})

    assert resposta.status_code == 200
    novo = resposta.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=bearer(novo))
    assert me.json()["condominio"]["id"] == str(condominio.id)


def test_refresh_com_access_token_da_401(client, session):
    access = entrar(client, criar_usuario(session)).json()["access_token"]
    resposta = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert resposta.status_code == 401


def test_refresh_falha_depois_de_trocar_sessao_versao(client, session):
    usuario = criar_usuario(session)
    refresh = entrar(client, usuario).json()["refresh_token"]

    usuario.sessao_versao += 1
    session.flush()

    resposta = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resposta.status_code == 401


def test_refresh_falha_se_o_vinculo_foi_retirado(client, session):
    usuario, condominio = criar_usuario(session), criar_condominio(session)
    vinculo = vincular(session, usuario, condominio)
    refresh = entrar(client, usuario).json()["refresh_token"]

    vinculo.ativo = False
    session.flush()

    resposta = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resposta.status_code == 401
