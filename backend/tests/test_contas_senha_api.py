"""TASK-53 (parte A): troca de senha logado e redefinição por token, contra PostgreSQL migrado."""

import json
import logging
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.rate_limit import get_login_rate_limiter
from app.modules.auth.security import hash_do_token, hash_senha, verificar_senha
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.usuarios.models import TokenRecuperacaoSenha, Usuario
from tests.isolamento.cenario import cabecalho, token_de
from tests.test_contas_funcionarios_api import conta
from tests.test_contas_funcionarios_api import session as sessao_postgres

session = sessao_postgres  # transação externa desfeita no fim de cada teste

pytestmark = pytest.mark.postgres

TROCA = "/api/v1/contas/me/senha"
REDEFINICAO = "/api/v1/contas/redefinicao-senha"
SENHA = "SenhaFicticia123"
NOVA = "OutraSenha456"


@pytest.fixture
def client(session):
    def sessao_da_requisicao():
        try:
            yield session
        except Exception:
            session.rollback()
            raise

    app = create_app()
    app.dependency_overrides[get_session] = sessao_da_requisicao
    get_login_rate_limiter().resetar()
    with TestClient(app, client=("203.0.113.53", 50000), raise_server_exceptions=False) as client:
        yield client
    get_login_rate_limiter().resetar()


def telefone() -> str:
    return "119" + "".join(random.choices("0123456789", k=8))


def cadastrar(client, tipo="morador"):
    dados = conta(telefone=telefone(), senha=SENHA)
    if tipo == "administracao":
        dados["documento"] = "52998224725"
    resposta = client.post(f"/api/v1/contas/{tipo}", json=dados)
    assert resposta.status_code == 201, resposta.text
    sessao = resposta.json()
    return sessao, dados


def bearer(sessao) -> dict[str, str]:
    return {"Authorization": f"Bearer {sessao['access_token']}"}


def login(client, email, senha):
    return client.post("/api/v1/auth/login", json={"identificador": email, "senha": senha})


def eventos(session, usuario_id, acao):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.recurso_id == uuid.UUID(str(usuario_id)),
                RegistroAuditoria.acao == acao,
            )
        )
    )


def emitir_token(session, usuario_id, *, expirado=False, usado=False) -> str:
    """Grava só o hash, como fará a parte B, e devolve o token em texto."""
    token = secrets.token_urlsafe(32)
    agora = datetime.now(UTC)
    criado = agora - timedelta(hours=2) if expirado else agora
    session.add(
        TokenRecuperacaoSenha(
            usuario_id=uuid.UUID(str(usuario_id)),
            token_hash=hash_do_token(token),
            criado_em=criado,
            expira_em=criado + timedelta(hours=1),
            usado_em=agora if usado else None,
        )
    )
    # Commit para sair do savepoint: um rollback de requisição que falha não pode apagar o token.
    session.commit()
    return token


def sem_segredos(texto: str, *segredos: str) -> bool:
    return all(segredo not in texto for segredo in segredos)


def test_hash_do_token_e_sha256_hexadecimal():
    assert hash_do_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert len(hash_do_token(secrets.token_urlsafe(32))) == 64


# --- troca de senha logado ---------------------------------------------------------------------


def test_troca_sem_token_e_401(client):
    assert client.put(TROCA, json={"senha_atual": SENHA, "senha_nova": NOVA}).status_code == 401


@pytest.mark.parametrize("adm_plataforma", [False, True])
def test_conta_sem_cadastro_proprio_e_403(client, session, adm_plataforma):
    """Conta compartilhada (e ADM) troca o acesso pela US-210, com responsável."""
    usuario = Usuario(
        nome="Conta compartilhada",
        email=f"{uuid.uuid4().hex}@exemplo.test",
        senha_hash=hash_senha(SENHA),
        administrador_plataforma=adm_plataforma,
    )
    session.add(usuario)
    session.commit()
    resposta = client.put(
        TROCA,
        headers=cabecalho(token_de(usuario, None)),
        json={"senha_atual": SENHA, "senha_nova": NOVA},
    )
    assert resposta.status_code == 403
    session.refresh(usuario)
    assert verificar_senha(SENHA, usuario.senha_hash)


@pytest.mark.parametrize("tipo", ["morador", "administracao"])
def test_troca_com_sucesso_derruba_sessoes_antigas(client, session, tipo):
    sessao, dados = cadastrar(client, tipo)
    usuario_id = sessao["usuario"]["id"]

    resposta = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": SENHA, "senha_nova": NOVA}
    )
    assert resposta.status_code == 200, resposta.text
    nova = resposta.json()
    assert set(nova) == set(sessao)  # mesma estrutura do login
    assert nova["usuario"]["id"] == usuario_id
    assert nova["access_token"] != sessao["access_token"]
    assert sem_segredos(resposta.text, SENHA, NOVA, "$argon2", "senha_hash")

    # Tokens antigos caem; os novos funcionam.
    assert client.get("/api/v1/auth/me", headers=bearer(sessao)).status_code == 401
    refresh = "/api/v1/auth/refresh"
    assert client.post(refresh, json={"refresh_token": sessao["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(nova)).status_code == 200
    assert client.post(refresh, json={"refresh_token": nova["refresh_token"]}).status_code == 200

    # Login: a nova entra, a antiga não.
    assert login(client, dados["email"], NOVA).status_code == 200
    assert login(client, dados["email"], SENHA).status_code == 401

    (evento,) = eventos(session, usuario_id, "conta.senha_alterar")
    assert evento.recurso_tipo == "usuario" and evento.usuario_id == uuid.UUID(usuario_id)
    assert evento.condominio_id is None and evento.perfil is None
    assert str(evento.ip) == "203.0.113.53"
    assert evento.antes == {"sessao_versao": 1} and evento.depois == {"sessao_versao": 2}
    trilha = json.dumps([evento.antes, evento.depois])
    assert sem_segredos(trilha, SENHA, NOVA, "$argon2", "senha", "token")


def test_senha_atual_errada_e_422_e_vira_429_no_limite(client, session):
    sessao, dados = cadastrar(client)
    errada = {"senha_atual": "Errada999", "senha_nova": NOVA}
    limite = get_login_rate_limiter()._max_falhas

    for _ in range(limite):
        resposta = client.put(TROCA, headers=bearer(sessao), json=errada)
        assert resposta.status_code == 422
        assert resposta.json()["error"]["reason"] == "senha_atual_incorreta"

    bloqueada = client.put(TROCA, headers=bearer(sessao), json=errada)
    assert bloqueada.status_code == 429
    assert bloqueada.json()["error"]["code"] == "too_many_attempts"
    assert int(bloqueada.headers["Retry-After"]) > 0
    # Bloqueado vale até para a senha certa, e nada muda.
    certa = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": SENHA, "senha_nova": NOVA}
    )
    assert certa.status_code == 429
    assert login(client, dados["email"], SENHA).status_code == 200


def test_acerto_limpa_o_contador(client):
    sessao, _ = cadastrar(client)
    limite = get_login_rate_limiter()._max_falhas
    for _ in range(limite - 1):
        client.put(
            TROCA, headers=bearer(sessao), json={"senha_atual": "Errada999", "senha_nova": NOVA}
        )
    # Acerta a senha atual, mas a nova é igual: o contador zera mesmo assim.
    igual = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": SENHA, "senha_nova": SENHA}
    )
    assert igual.json()["error"]["reason"] == "senha_nova_igual_atual"
    for _ in range(limite - 1):
        resposta = client.put(
            TROCA, headers=bearer(sessao), json={"senha_atual": "Errada999", "senha_nova": NOVA}
        )
        assert resposta.status_code == 422


@pytest.mark.parametrize(
    "senha_nova",
    ["curta1", "semdigitos", "12345678", "x1" * 65, "EMAIL"],
    ids=["curta", "sem-digito", "sem-letra", "longa", "igual-ao-email"],
)
def test_senha_nova_fora_da_regra_e_422(client, session, senha_nova):
    sessao, dados = cadastrar(client)
    if senha_nova == "EMAIL":
        senha_nova = dados["email"].upper()
    resposta = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": SENHA, "senha_nova": senha_nova}
    )
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "validation_error"
    assert login(client, dados["email"], SENHA).status_code == 200
    assert eventos(session, sessao["usuario"]["id"], "conta.senha_alterar") == []


def test_senha_nova_igual_a_atual_e_422(client):
    sessao, _ = cadastrar(client)
    resposta = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": SENHA, "senha_nova": SENHA}
    )
    assert resposta.status_code == 422
    assert resposta.json()["error"]["reason"] == "senha_nova_igual_atual"


@pytest.mark.parametrize(
    "corpo",
    [
        {"senha_nova": NOVA},
        {"senha_atual": SENHA},
        {"senha_atual": SENHA, "senha_nova": NOVA, "x": 1},
    ],
)
def test_corpo_invalido_na_troca_e_422(client, corpo):
    sessao, _ = cadastrar(client)
    assert client.put(TROCA, headers=bearer(sessao), json=corpo).status_code == 422


# --- redefinição por token ---------------------------------------------------------------------


def test_redefinicao_com_sucesso(client, session, caplog):
    caplog.set_level(logging.DEBUG)
    sessao, dados = cadastrar(client)
    usuario_id = sessao["usuario"]["id"]
    token = emitir_token(session, usuario_id)

    resposta = client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA})
    assert resposta.status_code == 204
    assert resposta.content == b""

    assert login(client, dados["email"], NOVA).status_code == 200
    assert login(client, dados["email"], SENHA).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(sessao)).status_code == 401  # sv mudou

    (evento,) = eventos(session, usuario_id, "conta.senha_redefinir")
    assert evento.usuario_id == uuid.UUID(usuario_id) and str(evento.ip) == "203.0.113.53"
    assert evento.antes == {"sessao_versao": 1} and evento.depois == {"sessao_versao": 2}
    trilha = json.dumps([evento.antes, evento.depois])
    assert sem_segredos(trilha, token, hash_do_token(token), NOVA, "$argon2")
    assert sem_segredos(caplog.text, token, hash_do_token(token), NOVA)


def test_mesma_resposta_para_usado_expirado_inexistente_e_conta_inativa(client, session, caplog):
    caplog.set_level(logging.DEBUG)
    sessao, _ = cadastrar(client)
    usuario_id = sessao["usuario"]["id"]

    usado = emitir_token(session, usuario_id)
    assert client.post(REDEFINICAO, json={"token": usado, "senha_nova": NOVA}).status_code == 204
    segundo_uso = client.post(REDEFINICAO, json={"token": usado, "senha_nova": "Mais1Senha"})

    expirado = emitir_token(session, usuario_id, expirado=True)
    inexistente = secrets.token_urlsafe(32)

    inativa, _ = cadastrar(client)
    token_inativa = emitir_token(session, inativa["usuario"]["id"])
    session.get(Usuario, uuid.UUID(inativa["usuario"]["id"])).ativo = False
    session.commit()

    respostas = [
        segundo_uso,
        client.post(REDEFINICAO, json={"token": expirado, "senha_nova": NOVA}),
        client.post(REDEFINICAO, json={"token": inexistente, "senha_nova": NOVA}),
        client.post(REDEFINICAO, json={"token": token_inativa, "senha_nova": NOVA}),
    ]
    referencia = respostas[0]
    assert referencia.status_code == 422
    assert referencia.json()["error"]["reason"] == "token_invalido"
    for resposta in respostas:
        assert (resposta.status_code, resposta.content) == (422, referencia.content)
        for token in (usado, expirado, inexistente, token_inativa):
            assert sem_segredos(resposta.text, token, hash_do_token(token))
    for token in (usado, expirado, inexistente, token_inativa):
        assert sem_segredos(caplog.text, token, hash_do_token(token))


def test_conta_compartilhada_com_token_e_token_invalido(client, session):
    usuario = Usuario(
        nome="Conta compartilhada",
        email=f"{uuid.uuid4().hex}@exemplo.test",
        senha_hash=hash_senha(SENHA),
    )
    session.add(usuario)
    session.commit()
    token = emitir_token(session, usuario.id)
    resposta = client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA})
    assert resposta.status_code == 422
    assert resposta.json()["error"]["reason"] == "token_invalido"
    session.refresh(usuario)
    assert verificar_senha(SENHA, usuario.senha_hash)


@pytest.mark.parametrize("senha_fraca", ["curta1", "semdigitos", "EMAIL"])
def test_senha_fraca_nao_consome_o_token(client, session, senha_fraca):
    sessao, dados = cadastrar(client)
    token = emitir_token(session, sessao["usuario"]["id"])
    if senha_fraca == "EMAIL":
        senha_fraca = dados["email"]  # só dá para conferir depois de achar a conta pelo token

    resposta = client.post(REDEFINICAO, json={"token": token, "senha_nova": senha_fraca})
    assert resposta.status_code == 422
    assert resposta.json()["error"].get("reason") != "token_invalido"

    linha = session.scalar(
        select(TokenRecuperacaoSenha).where(
            TokenRecuperacaoSenha.token_hash == hash_do_token(token)
        )
    )
    session.refresh(linha)
    assert linha.usado_em is None  # o rollback devolveu o token
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 204


def test_outros_tokens_pendentes_ficam_inutilizaveis(client, session):
    sessao, _ = cadastrar(client)
    usuario_id = sessao["usuario"]["id"]
    primeiro, segundo = emitir_token(session, usuario_id), emitir_token(session, usuario_id)
    outro_usuario, _ = cadastrar(client)
    de_outra_conta = emitir_token(session, outro_usuario["usuario"]["id"])

    assert client.post(REDEFINICAO, json={"token": primeiro, "senha_nova": NOVA}).status_code == 204
    resposta = client.post(REDEFINICAO, json={"token": segundo, "senha_nova": "Mais1Senha"})
    assert resposta.status_code == 422
    assert resposta.json()["error"]["reason"] == "token_invalido"
    # Só os tokens da própria conta: o de outra pessoa continua valendo.
    assert (
        client.post(REDEFINICAO, json={"token": de_outra_conta, "senha_nova": NOVA}).status_code
        == 204
    )


def test_redefinicao_derruba_a_troca_logada_pendente(client, session):
    """Depois da redefinição, o access token antigo não serve nem para trocar a senha."""
    sessao, _ = cadastrar(client)
    token = emitir_token(session, sessao["usuario"]["id"])
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 204
    resposta = client.put(
        TROCA, headers=bearer(sessao), json={"senha_atual": NOVA, "senha_nova": "Mais1Senha"}
    )
    assert resposta.status_code == 401


@pytest.mark.parametrize(
    "corpo",
    [
        {"senha_nova": NOVA},
        {"token": "", "senha_nova": NOVA},
        {"token": "x" * 513, "senha_nova": NOVA},
        {"token": "abc", "senha_nova": NOVA, "email": "a@b.c"},
    ],
)
def test_corpo_invalido_na_redefinicao_e_422(client, corpo):
    assert client.post(REDEFINICAO, json=corpo).status_code == 422


def test_falha_na_auditoria_desfaz_tudo_e_mantem_o_token(client, session, monkeypatch):
    from app.modules.contas import service

    sessao, dados = cadastrar(client)
    token = emitir_token(session, sessao["usuario"]["id"])

    def quebrar(*args, **kwargs):
        raise RuntimeError("auditoria fora do ar")

    monkeypatch.setattr(service.auditoria, "registrar_acao", quebrar)
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 500
    monkeypatch.undo()

    assert login(client, dados["email"], SENHA).status_code == 200  # senha não mudou
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 204


def test_corpo_das_respostas_nao_traz_token_nem_hash(client, session):
    sessao, _ = cadastrar(client)
    token = emitir_token(session, sessao["usuario"]["id"])
    respostas = [
        client.post(REDEFINICAO, json={"token": token, "senha_nova": "curta1"}),
        client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}),
        client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}),
    ]
    for resposta in respostas:
        assert sem_segredos(resposta.text, token, hash_do_token(token), "$argon2")


def test_sessao_sem_mudanca_quando_a_resposta_e_token_invalido(client, session):
    sessao, _ = cadastrar(client)
    client.post(REDEFINICAO, json={"token": secrets.token_urlsafe(32), "senha_nova": NOVA})
    assert client.get("/api/v1/auth/me", headers=bearer(sessao)).status_code == 200


def test_bearer_de_outra_conta_nao_muda_o_dono_do_token(client, session):
    """Rota pública: um Bearer de outra conta não muda de quem é a senha redefinida."""
    dono, dados_dono = cadastrar(client)
    intruso, _ = cadastrar(client)
    token = emitir_token(session, dono["usuario"]["id"])
    resposta = client.post(
        REDEFINICAO, headers=bearer(intruso), json={"token": token, "senha_nova": NOVA}
    )
    assert resposta.status_code == 204
    assert login(client, dados_dono["email"], NOVA).status_code == 200
    assert client.get("/api/v1/auth/me", headers=bearer(intruso)).status_code == 200


def test_tempo_de_validade_vem_do_banco_com_fuso(client, session):
    # Garante que `expira_em > now()` usa timestamp com fuso: um token que expira daqui a
    # um minuto ainda vale.
    sessao, _ = cadastrar(client)
    token = secrets.token_urlsafe(32)
    session.add(
        TokenRecuperacaoSenha(
            usuario_id=uuid.UUID(sessao["usuario"]["id"]),
            token_hash=hash_do_token(token),
            criado_em=datetime.now(UTC) - timedelta(minutes=59),
            expira_em=datetime.now(UTC) + timedelta(minutes=1),
        )
    )
    session.commit()
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 204


def test_redefinicao_desbloqueia_login_apos_excesso_de_falhas(client, session):
    sessao, dados = cadastrar(client)
    limite = get_login_rate_limiter()._max_falhas
    for _ in range(limite):
        assert login(client, dados["email"], "Errada999").status_code == 401
    assert login(client, dados["email"], SENHA).status_code == 429

    token = emitir_token(session, sessao["usuario"]["id"])
    assert client.post(REDEFINICAO, json={"token": token, "senha_nova": NOVA}).status_code == 204
    assert login(client, dados["email"], NOVA).status_code == 200


def test_troca_preserva_condominio_selecionado_e_inutiliza_tokens(client, session):
    sessao, _ = cadastrar(client)
    usuario_id = uuid.UUID(sessao["usuario"]["id"])
    aurora = Condominio(nome="Aurora", status="ativo")
    boa_vista = Condominio(nome="Boa Vista", status="ativo")
    session.add_all([aurora, boa_vista])
    session.flush()
    session.add_all(
        [
            VinculoCondominio(
                usuario_id=usuario_id, condominio_id=aurora.id, perfil="morador", ativo=True
            ),
            VinculoCondominio(
                usuario_id=usuario_id, condominio_id=boa_vista.id, perfil="morador", ativo=True
            ),
        ]
    )
    session.commit()
    token_recuperacao = emitir_token(session, usuario_id)

    selecao = client.post(
        "/api/v1/auth/selecionar-condominio",
        headers=bearer(sessao),
        json={"condominio_id": str(boa_vista.id)},
    )
    assert selecao.status_code == 200

    troca = client.put(
        TROCA,
        headers=bearer(selecao.json()),
        json={"senha_atual": SENHA, "senha_nova": NOVA},
    )
    assert troca.status_code == 200
    corpo = troca.json()
    assert corpo["condominio"]["id"] == str(boa_vista.id)
    assert corpo["requer_selecao"] is False
    me = client.get("/api/v1/auth/me", headers=bearer(corpo))
    assert me.status_code == 200
    assert me.json()["condominio"]["id"] == str(boa_vista.id)

    (evento,) = eventos(session, usuario_id, "conta.senha_alterar")
    assert evento.condominio_id is None and evento.perfil is None

    redefinicao = client.post(
        REDEFINICAO, json={"token": token_recuperacao, "senha_nova": "Mais1Senha"}
    )
    assert redefinicao.status_code == 422
    assert redefinicao.json()["error"]["reason"] == "token_invalido"
