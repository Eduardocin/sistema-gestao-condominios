"""Contrato HTTP real de permissões por aba, com PostgreSQL migrado e dados fictícios."""

import uuid
from datetime import UTC, datetime
from typing import get_args

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.autorizacao import require_aba, require_permission
from app.modules.permissoes_aba.schemas import AbaNome
from app.modules.unidades.models import ABAS_MORADOR, MoradorUnidade, PermissaoAba
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de, vincular

pytestmark = pytest.mark.postgres


@pytest.fixture
def client(session):
    app = create_app()

    def banco():
        try:
            yield session
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_session] = banco

    def protegido():
        return {"ok": True}

    for aba in ABAS_MORADOR:
        app.add_api_route(
            f"/teste/unidades/{{unidade_id}}/abas/{aba}",
            protegido,
            dependencies=[Depends(require_permission("vinculos:ver")), Depends(require_aba(aba))],
        )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def cenario(session):
    p = montar_predio(session)
    usuario = criar_usuario(session)
    vincular(session, usuario, p.condominio)
    dono = p.morador_unidade
    alvo = MoradorUnidade(
        usuario_id=usuario.id,
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        origem="convite",
    )
    session.add(alvo)
    session.flush()
    for morador in (dono, alvo):
        session.add_all(
            PermissaoAba(
                condominio_id=p.condominio.id,
                morador_unidade_id=morador.id,
                aba=aba,
                com_acesso=morador is dono or aba == "usuarios",
            )
            for aba in ABAS_MORADOR
        )
    session.commit()
    return p, dono, alvo, usuario


def url(p, morador=None):
    base = f"/api/v1/unidades/{p.unidade_101.id}/moradores"
    return f"{base}/{morador.id}/permissoes" if morador else base


def alterar(client, p, alvo, abas, perfil="morador"):
    return client.put(url(p, alvo), json={"abas": abas}, headers=p.cabecalho_de(perfil))


def eventos(session, p):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == p.condominio.id,
                RegistroAuditoria.acao == "permissao_aba.alterar",
            )
        )
    )


def test_schema_e_modelo_usam_as_mesmas_sete_abas():
    assert set(get_args(AbaNome)) == set(ABAS_MORADOR)


@pytest.mark.parametrize(
    ("perfil", "esperado"),
    [("morador", 200), ("administracao", 200), ("funcionario", 403), ("plataforma", 403)],
)
def test_perfil_de_listagem(client, cenario, perfil, esperado):
    p, *_ = cenario
    resposta = client.get(url(p), headers=p.cabecalho_de(perfil))
    assert resposta.status_code == esperado
    if esperado == 200:
        assert resposta.json()["total"] == 2
        for item in resposta.json()["items"]:
            assert set(item["permissoes"]) == set(ABAS_MORADOR)
            assert not {"email", "telefone", "documento"} & item.keys()


@pytest.mark.parametrize(
    ("perfil", "esperado"),
    [("morador", 200), ("administracao", 403), ("funcionario", 403), ("plataforma", 403)],
)
def test_perfil_de_edicao(client, cenario, perfil, esperado):
    p, _, alvo, _ = cenario
    assert alterar(client, p, alvo, {"visitantes": True}, perfil).status_code == esperado


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_token_obrigatorio(client, cenario, metodo):
    p, _, alvo, _ = cenario
    resposta = (
        client.get(url(p))
        if metodo == "get"
        else client.put(url(p, alvo), json={"abas": {"visitantes": True}})
    )
    assert resposta.status_code == 401


@pytest.mark.parametrize("aba", ABAS_MORADOR)
def test_edicao_parcial_e_auditoria(client, cenario, session, aba):
    p, _, alvo, _ = cenario
    antes = aba == "usuarios"
    resposta = alterar(client, p, alvo, {aba: not antes})
    assert resposta.status_code == 200
    esperado = {nome: nome == "usuarios" for nome in ABAS_MORADOR}
    esperado[aba] = not antes
    assert resposta.json()["permissoes"] == esperado
    registros = eventos(session, p)
    assert len(registros) == 1
    registro = registros[0]
    assert registro.usuario_id == p.morador.id
    assert registro.recurso_id == alvo.id
    assert registro.antes == {aba: antes}
    assert registro.depois == {aba: not antes}


def test_repetir_valor_nao_duplica_evento(client, cenario, session):
    p, _, alvo, _ = cenario
    for _ in range(2):
        assert alterar(client, p, alvo, {"visitantes": True}).status_code == 200
    assert len(eventos(session, p)) == 1


@pytest.mark.parametrize("aba", ABAS_MORADOR)
def test_mudanca_vale_na_proxima_requisicao_com_o_mesmo_token(client, cenario, aba):
    p, _, alvo, usuario = cenario
    headers = cabecalho(token_de(usuario, p.condominio.id))
    protegido = f"/teste/unidades/{p.unidade_101.id}/abas/{aba}"
    assert alterar(client, p, alvo, {aba: True}).status_code == 200
    assert client.get(protegido, headers=headers).status_code == 200
    assert alterar(client, p, alvo, {aba: False}).status_code == 200
    assert client.get(protegido, headers=headers).status_code == 403


def test_ultimo_usuarios_e_alteracao_tudo_ou_nada(client, cenario, session):
    p, dono, alvo, _ = cenario
    assert alterar(client, p, alvo, {"usuarios": False}).status_code == 200
    resposta = alterar(client, p, dono, {"usuarios": False, "visitantes": False})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "ultimo_usuarios"
    assert len(eventos(session, p)) == 1
    resposta = client.get(url(p), headers=p.cabecalho_de("morador"))
    atual = next(item for item in resposta.json()["items"] if item["id"] == str(dono.id))
    assert atual["permissoes"]["usuarios"] is True
    assert atual["permissoes"]["visitantes"] is True


@pytest.mark.parametrize(
    "corpo",
    [
        {"abas": {}},
        {"abas": {"inexistente": True}},
        {"abas": {"visitantes": "true"}},
        {"abas": {"visitantes": 1}},
        {"abas": {"visitantes": True}, "condominio_id": str(uuid.uuid4())},
        {"abas": {"visitantes": True}, "usuario_id": str(uuid.uuid4())},
    ],
)
def test_corpo_invalido_nao_altera_permissoes(client, cenario, session, corpo):
    p, _, alvo, _ = cenario
    resposta = client.put(url(p, alvo), json=corpo, headers=p.cabecalho_de("morador"))
    assert resposta.status_code == 422
    assert eventos(session, p) == []


@pytest.mark.parametrize("consulta", ["page=0", "page_size=101", "page_size=0"])
def test_paginacao_invalida(client, cenario, consulta):
    p, *_ = cenario
    assert client.get(f"{url(p)}?{consulta}", headers=p.cabecalho_de("morador")).status_code == 422


def test_paginacao_e_identificacao_do_proprio_morador(client, cenario):
    p, dono, _, _ = cenario
    respostas = [
        client.get(f"{url(p)}?page={page}&page_size=1", headers=p.cabecalho_de("morador"))
        for page in (1, 2)
    ]
    assert all(r.status_code == 200 and r.json()["total"] == 2 for r in respostas)
    items = [r.json()["items"][0] for r in respostas]
    assert len({item["id"] for item in items}) == 2
    assert next(item for item in items if item["eu"])["id"] == str(dono.id)


def test_unidade_alheia_e_inexistente_retornam_mesmo_404(client, cenario, session):
    p, *_ = cenario
    outro = montar_predio(session, "Outro")
    headers = p.cabecalho_de("morador")
    respostas = [
        client.get(f"/api/v1/unidades/{id_}/moradores", headers=headers)
        for id_ in (p.unidade_102.id, outro.unidade_101.id, uuid.uuid4())
    ]
    assert all(r.status_code == 404 for r in respostas)
    assert len({r.content for r in respostas}) == 1


def test_morador_alvo_precisa_pertencer_a_unidade(client, cenario, session):
    p, _, alvo, _ = cenario
    alvo.unidade_id = p.unidade_102.id
    session.flush()
    assert alterar(client, p, alvo, {"visitantes": True}).status_code == 404
    assert eventos(session, p) == []


def test_edicao_nao_alcanca_morador_de_outro_condominio(client, cenario, session):
    p, *_ = cenario
    outro = montar_predio(session, "Outro")
    assert alterar(client, p, outro.morador_unidade, {"visitantes": True}).status_code == 404
    assert eventos(session, p) == []


def test_perfil_negado_e_checado_antes_do_corpo(client, cenario):
    p, _, alvo, _ = cenario
    resposta = client.put(url(p, alvo), json={"abas": {}}, headers=p.cabecalho_de("funcionario"))
    assert resposta.status_code == 403


def test_morador_desvinculado_nao_e_listado_ou_editado(client, cenario, session):
    p, _, alvo, _ = cenario
    alvo.status = "desvinculado"
    alvo.desvinculado_em = datetime.now(UTC)
    session.flush()
    resposta = client.get(url(p), headers=p.cabecalho_de("morador"))
    assert resposta.json()["total"] == 1
    assert alterar(client, p, alvo, {"visitantes": True}).status_code == 404


def test_aba_sem_linha_no_banco_nega_por_padrao(client, cenario, session):
    p, dono, _, _ = cenario
    permissao = session.get(PermissaoAba, (dono.id, "usuarios"))
    session.delete(permissao)
    session.flush()
    assert client.get(url(p), headers=p.cabecalho_de("morador")).status_code == 403


def test_falha_na_auditoria_reverte_as_permissoes(client, cenario, session, monkeypatch):
    from app.modules.permissoes_aba.repository import RepositorioAuditoria

    p, _, alvo, _ = cenario

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha de teste na auditoria")

    monkeypatch.setattr(RepositorioAuditoria, "registrar", falhar)
    assert alterar(client, p, alvo, {"visitantes": True}).status_code == 500
    permissao = session.get(PermissaoAba, (alvo.id, "visitantes"))
    assert permissao is not None and permissao.com_acesso is False
    assert eventos(session, p) == []
