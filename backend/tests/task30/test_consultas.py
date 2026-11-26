import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.modules.auth.security import TipoToken, decodificar_token
from app.modules.condominios.models import VinculoCondominio
from app.modules.storage.router import get_storage_adapter
from app.modules.unidades.models import PermissaoAba, ProprietarioUnidade
from tests.isolamento.cenario import cabecalho
from tests.task29.conftest import arquivo
from tests.task30.conftest import vincular
from tests.task30.test_vinculos import associacoes

pytestmark = pytest.mark.postgres
BASE = "/api/v1/minhas-unidades"


def selecionar(client, caso, predio=None):
    resposta = client.post(
        "/api/v1/auth/selecionar-condominio",
        headers=caso.headers,
        json={"condominio_id": str((predio or caso.a).condominio.id)},
    )
    assert resposta.status_code == 200, resposta.text
    return cabecalho(resposta.json()["access_token"])


def test_me_multiplas_unidades_e_selecao_sem_mudar_jwt(client, session, caso):
    for chave_ in caso.chaves:
        assert vincular(client, caso, chave_=chave_.codigo).status_code == 201
    headers = selecionar(client, caso)
    token = headers["Authorization"].removeprefix("Bearer ")
    claims = decodificar_token(token, tipo_esperado=TipoToken.ACCESS)
    assert claims.condominio_id == caso.a.condominio.id and claims.usuario_id == caso.usuario.id
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert {u["id"] for u in me.json()["unidades"]} == {
        str(caso.a.unidade_101.id),
        str(caso.a.unidade_102.id),
    }
    assert all("abas" in unidade for unidade in me.json()["unidades"])
    outros = client.get("/api/v1/auth/me", headers=selecionar(client, caso, caso.b)).json()
    assert [u["id"] for u in outros["unidades"]] == [str(caso.b.unidade_102.id)]
    for vinculo in session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
    ):
        assert vinculo.unidade_id is None
    assert client.get("/api/v1/auth/me", headers=caso.headers).json()["unidades"] == []


@pytest.mark.parametrize("documento", ["52998224725", "11222333000181"])
def test_lista_e_detalhe_proprietario_sem_documento_ou_chave(client, session, caso, documento):
    for chave_ in caso.chaves:
        assert vincular(client, caso, chave_=chave_.codigo).status_code == 201
    session.add(
        ProprietarioUnidade(
            condominio_id=caso.a.condominio.id,
            unidade_id=caso.a.unidade_102.id,
            nome="Maria Souza",
            documento=documento,
            emails=["maria@exemplo.test"],
            whatsapps=["81988887777"],
            telefone="8133334444",
        )
    )
    session.commit()
    headers = selecionar(client, caso)
    pagina = client.get(BASE, headers=headers, params={"page_size": 1}).json()
    assert pagina["total"] == 2 and len(pagina["items"]) == 1
    assert (
        client.get(BASE, headers=headers, params={"page_size": 1, "page": 3}).json()["items"] == []
    )
    resposta = client.get(f"{BASE}/{caso.a.unidade_102.id}", headers=headers)
    assert resposta.status_code == 200
    proprietario = resposta.json()["proprietario"]
    assert proprietario == {
        "nome": "Maria Souza",
        "emails": ["maria@exemplo.test"],
        "whatsapps": ["81988887777"],
        "telefone": "8133334444",
        "foto_arquivo_id": None,
    }
    assert "documento" not in resposta.text and documento not in resposta.text
    assert "codigo" not in resposta.text and "chave" not in resposta.text
    assert (
        client.get(f"{BASE}/{caso.a.unidade_101.id}", headers=headers).json()["proprietario"]
        is None
    )


def test_isolamento_de_unidade_e_condominio(client, caso):
    assert vincular(client, caso).status_code == 201
    headers = selecionar(client, caso)
    respostas = [
        client.get(f"{BASE}/{id_}", headers=headers)
        for id_ in (caso.a.unidade_101.id, caso.b.unidade_102.id, uuid.uuid4())
    ]
    assert all(r.status_code == 404 for r in respostas)
    assert respostas[0].json() == respostas[1].json() == respostas[2].json()
    assert (
        client.post(
            "/api/v1/auth/selecionar-condominio",
            headers=caso.headers,
            json={"condominio_id": str(caso.b.condominio.id)},
        ).status_code
        == 404
    )


def test_aba_unidades_e_vinculo_valem_na_proxima_requisicao(client, session, caso):
    assert vincular(client, caso).status_code == 201
    headers = selecionar(client, caso)
    (morador_,) = associacoes(session, caso.usuario)
    permissao = session.get(PermissaoAba, (morador_.id, "unidades"))
    permissao.com_acesso = False
    session.commit()
    assert client.get(BASE, headers=headers).json()["items"] == []
    assert client.get(f"{BASE}/{morador_.unidade_id}", headers=headers).status_code == 403
    assert len(client.get("/api/v1/auth/me", headers=headers).json()["unidades"]) == 1
    permissao.com_acesso = True
    session.commit()
    assert client.get(f"{BASE}/{morador_.unidade_id}", headers=headers).status_code == 200
    morador_.status = "desvinculado"
    morador_.desvinculado_em = caso.relogio.momento
    session.commit()
    assert client.get(BASE, headers=headers).json()["items"] == []
    assert client.get(f"{BASE}/{morador_.unidade_id}", headers=headers).status_code == 404
    assert client.get("/api/v1/auth/me", headers=headers).json()["unidades"] == []


def test_unidade_inativa_e_legado_nao_concedem_acesso(client, session, caso):
    assert vincular(client, caso).status_code == 201
    headers = selecionar(client, caso)
    vinculo = session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
    ).one()
    vinculo.unidade_id = caso.a.unidade_101.id  # não é uma associação atual
    caso.a.unidade_102.ativo = False
    session.commit()
    assert client.get("/api/v1/auth/me", headers=headers).json()["unidades"] == []
    assert client.get(BASE, headers=headers).json()["total"] == 0
    assert client.get(f"{BASE}/{caso.a.unidade_102.id}", headers=headers).status_code == 404
    assert client.get(f"{BASE}/{caso.a.unidade_101.id}", headers=headers).status_code == 404


@pytest.mark.parametrize("perfil", ["administracao", "funcionario", "plataforma"])
def test_consultas_so_morador(client, caso, perfil):
    headers = caso.a.cabecalho_de(perfil)
    assert client.get(BASE, headers=headers).status_code == 403
    assert client.get(f"{BASE}/{caso.a.unidade_101.id}", headers=headers).status_code == 403


def test_consultas_exigem_cid_e_identidade(client, caso):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=caso.headers).status_code == 403


@pytest.mark.parametrize("estado", ["pendente", "rejeitado", "desativado"])
def test_condominio_nao_ativo(client, session, caso, estado):
    assert vincular(client, caso).status_code == 201
    headers = selecionar(client, caso)
    caso.a.condominio.status = estado
    caso.a.condominio.motivo_rejeicao = "Motivo" if estado == "rejeitado" else None
    session.commit()
    assert client.get(BASE, headers=headers).status_code == 403


def test_integracao_com_edicao_de_permissoes_existente(client, session, caso):
    assert vincular(client, caso).status_code == 201
    headers = selecionar(client, caso)
    (morador_,) = associacoes(session, caso.usuario)
    rota = f"/api/v1/unidades/{caso.a.unidade_102.id}/moradores/{morador_.id}/permissoes"
    assert client.put(rota, headers=headers, json={"abas": {"unidades": False}}).status_code == 200
    assert client.get(BASE, headers=headers).json()["items"] == []
    assert client.put(rota, headers=headers, json={"abas": {"usuarios": False}}).status_code == 409


def test_foto_do_proprietario_exige_proprio_vinculo_e_aba(client, session, caso):
    assert vincular(client, caso).status_code == 201
    foto = arquivo(session, caso.a)
    session.add(
        ProprietarioUnidade(
            condominio_id=caso.a.condominio.id,
            unidade_id=caso.a.unidade_102.id,
            nome="Maria",
            documento="52998224725",
            foto_arquivo_id=foto.id,
        )
    )
    session.commit()
    client.app.dependency_overrides[get_storage_adapter] = lambda: SimpleNamespace(
        sign=lambda key, seconds: f"https://storage.exemplo.test/{key}"
    )
    headers = selecionar(client, caso)
    rota = f"/api/v1/arquivos/{foto.id}/download"
    assert client.get(rota, headers=headers).status_code == 200
    assert client.get(rota, headers=caso.a.cabecalho_de("morador")).status_code == 404
    (morador_,) = associacoes(session, caso.usuario)
    session.get(PermissaoAba, (morador_.id, "unidades")).com_acesso = False
    session.commit()
    assert client.get(rota, headers=headers).status_code == 404


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page_size": 101}, {"condominio_id": str(uuid.uuid4())}]
)
def test_paginacao_invalida_e_escopo_protegido(client, caso, params):
    assert vincular(client, caso).status_code == 201
    assert client.get(BASE, headers=selecionar(client, caso), params=params).status_code == 422
