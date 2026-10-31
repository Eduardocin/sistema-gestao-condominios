"""get_current_context: ordem de checagem da matriz (seção 5) e itens 6, 7 e 8 da seção 11."""

import dataclasses
import uuid

import pytest

from app.core.contexto import ContextoCondominio
from app.modules.auth.security import TipoToken
from tests.isolamento.cenario import (
    cabecalho,
    criar_condominio,
    criar_usuario,
    token_de,
    vincular,
)

pytestmark = pytest.mark.postgres

URL = "/api/v1/diagnostico/contexto"


def test_contexto_e_imutavel():
    contexto = ContextoCondominio(
        usuario_id=uuid.uuid4(),
        condominio_id=uuid.uuid4(),
        perfil="morador",
        vinculo_id=uuid.uuid4(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        contexto.condominio_id = uuid.uuid4()


# --- passo 1: identidade (401) ------------------------------------------------


def test_sem_token_responde_401(client):
    resposta = client.get(URL)

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "not_authenticated"
    assert resposta.headers["www-authenticate"] == "Bearer"


def test_token_invalido_responde_401(client):
    resposta = client.get(URL, headers=cabecalho("isto-nao-e-um-jwt"))

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "not_authenticated"


def test_refresh_token_nao_vale_como_access(client, a):
    token = token_de(a.usuario, a.condominio.id, tipo=TipoToken.REFRESH)

    assert client.get(URL, headers=cabecalho(token)).status_code == 401


def test_sv_desatualizado_responde_401(client, session, a):
    token = token_de(a.usuario, a.condominio.id, sessao_versao=a.usuario.sessao_versao)
    a.usuario.sessao_versao += 1  # ex.: troca de senha derruba as sessões
    session.flush()

    resposta = client.get(URL, headers=cabecalho(token))

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "not_authenticated"


def test_usuario_inativo_responde_401(client, session, a):
    a.usuario.ativo = False
    session.flush()

    assert client.get(URL, headers=a.cabecalho).status_code == 401


# --- passo 2: condomínio (403) ------------------------------------------------


def test_token_sem_cid_responde_403(client, a):
    token = token_de(a.usuario, None)

    resposta = client.get(URL, headers=cabecalho(token))

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


def test_cid_de_condominio_sem_vinculo_responde_403(client, a, b):
    # O usuário do A apresenta um token com o cid do B: o banco não tem vínculo, então nega.
    token = token_de(a.usuario, b.condominio.id)

    resposta = client.get(URL, headers=cabecalho(token))

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"
    # A mensagem não pode denunciar nada sobre o outro condomínio.
    assert str(b.condominio.id) not in resposta.text
    assert b.condominio.nome not in resposta.text


def test_vinculo_desativado_depois_do_login_perde_acesso_na_hora(client, session, a):
    assert client.get(URL, headers=a.cabecalho).status_code == 200

    a.vinculo.ativo = False  # a Administração desvinculou a pessoa; o token continua válido
    session.flush()

    assert client.get(URL, headers=a.cabecalho).status_code == 403


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "administracao"])
def test_condominio_desativado_nega_todos_os_perfis(client, session, perfil):
    condominio = criar_condominio(session, "Fora do ar", ativo=False)
    usuario = criar_usuario(session)
    vincular(session, usuario, condominio, perfil=perfil)
    token = token_de(usuario, condominio.id, perfil=perfil)

    resposta = client.get(URL, headers=cabecalho(token))

    # Vale até para a Administração: o fluxo de cadastro será outra variante (fora da TASK-18).
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


def test_adm_da_plataforma_sem_cid_responde_403(client, session):
    adm = criar_usuario(session, adm=True)

    assert client.get(URL, headers=cabecalho(token_de(adm, None))).status_code == 403


def test_adm_da_plataforma_com_cid_forjado_responde_403(client, session, a):
    adm = criar_usuario(session, adm=True)

    assert client.get(URL, headers=cabecalho(token_de(adm, a.condominio.id))).status_code == 403


def test_adm_da_plataforma_com_vinculo_tambem_e_negado(client, session, a):
    # Mesmo que um vínculo escape para o ADM, a rota de condomínio continua negada (R8).
    adm = criar_usuario(session, adm=True)
    vincular(session, adm, a.condominio)

    assert client.get(URL, headers=cabecalho(token_de(adm, a.condominio.id))).status_code == 403


# --- o que o contexto carrega ------------------------------------------------


def test_contexto_vem_do_vinculo_no_banco(client, a):
    corpo = client.get(URL, headers=a.cabecalho).json()

    assert corpo == {
        "usuario_id": str(a.usuario.id),
        "condominio_id": str(a.condominio.id),
        "perfil": "morador",
        "vinculo_id": str(a.vinculo.id),
    }


def test_claim_perfil_do_token_nunca_decide(client, a):
    # O token jura que é Administração, mas o banco diz que é morador (R6).
    token = token_de(a.usuario, a.condominio.id, perfil="administracao")

    assert client.get(URL, headers=cabecalho(token)).json()["perfil"] == "morador"


def test_mudanca_de_perfil_vale_na_requisicao_seguinte(client, session, a):
    assert client.get(URL, headers=a.cabecalho).json()["perfil"] == "morador"

    a.vinculo.perfil = "funcionario"
    session.flush()

    assert client.get(URL, headers=a.cabecalho).json()["perfil"] == "funcionario"
