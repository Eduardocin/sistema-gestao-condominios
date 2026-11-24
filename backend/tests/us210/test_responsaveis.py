import pytest

from app.modules.auditoria import service as auditoria
from app.modules.funcionarios.models import ResponsavelAdministracao
from tests.us210.conftest import CONTA, RESPONSAVEIS, dados
from tests.us210.test_conta import eventos

pytestmark = pytest.mark.postgres


def test_edicao_desativacao_preserva_ids_e_nomes_historicos(client, session, caso):
    assert client.put(CONTA, headers=caso.a.headers, json=dados(caso)).status_code == 200
    segundo = client.post(
        RESPONSAVEIS, headers=caso.a.headers, json={"nome": "  Outro   Responsável "}
    )
    assert segundo.status_code == 201 and segundo.json()["nome"] == "Outro Responsável"
    rota = f"{RESPONSAVEIS}/{caso.a.responsavel.id}"
    editado = client.put(rota, headers=caso.a.headers, json={"nome": "  Nome   Corrigido "})
    assert editado.status_code == 200 and editado.json()["nome"] == "Nome Corrigido"
    assert editado.json()["id"] == str(caso.a.responsavel.id)
    quantidade = len(eventos(session, caso, "responsaveis.alterar"))
    assert (
        client.put(rota, headers=caso.a.headers, json={"nome": "Nome Corrigido"}).status_code == 200
    )
    assert len(eventos(session, caso, "responsaveis.alterar")) == quantidade
    resposta = client.post(rota + "/desativacao", headers=caso.a.headers, json={})
    assert resposta.status_code == 200 and resposta.json()["ativo"] is False
    assert client.get(RESPONSAVEIS, headers=caso.a.headers).json() == [segundo.json()]
    assert client.get(RESPONSAVEIS, headers=caso.a.headers, params={"ativo": False}).json() == [
        resposta.json()
    ]
    assert eventos(session, caso)[0].responsavel_nome == "Síndica Original"
    assert session.get(ResponsavelAdministracao, caso.a.responsavel.id) is not None
    assert client.post(rota + "/desativacao", headers=caso.a.headers, json={}).status_code == 409
    assert (
        client.post(
            RESPONSAVEIS, headers=caso.a.headers, json={"nome": "Nome Corrigido"}
        ).status_code
        == 201
    )


def test_duplicidade_validacao_e_ultimo_responsavel(client, caso):
    segundo = client.post(RESPONSAVEIS, headers=caso.a.headers, json={"nome": "Outro"}).json()
    rota = f"{RESPONSAVEIS}/{segundo['id']}"
    assert (
        client.put(rota, headers=caso.a.headers, json={"nome": "síndica original"}).status_code
        == 409
    )
    for nome in (" ", "x" * 101):
        assert client.put(rota, headers=caso.a.headers, json={"nome": nome}).status_code == 422
    assert (
        client.put(rota, headers=caso.a.headers, json={"nome": "Outro", "ativo": False}).status_code
        == 422
    )
    assert (
        client.post(
            rota + "/desativacao", headers=caso.a.headers, json={"ativo": False}
        ).status_code
        == 422
    )
    assert client.post(rota + "/desativacao", headers=caso.a.headers, json={}).status_code == 200
    ultimo = client.post(
        f"{RESPONSAVEIS}/{caso.a.responsavel.id}/desativacao", headers=caso.a.headers, json={}
    )
    assert ultimo.status_code == 409 and ultimo.json()["error"]["reason"] == "ultimo_responsavel"


@pytest.mark.parametrize("status", ["pendente", "rejeitado", "ativo", "desativado"])
def test_gestao_preserva_excecao_de_cadastro(client, session, caso, status):
    caso.a.condominio.status = status
    caso.a.condominio.motivo_rejeicao = "Documentação" if status == "rejeitado" else None
    session.commit()
    rota = f"{RESPONSAVEIS}/{caso.a.responsavel.id}"
    esperado = 403 if status == "desativado" else 200
    assert (
        client.put(rota, headers=caso.a.headers, json={"nome": "Corrigido"}).status_code == esperado
    )
    novo = client.post(RESPONSAVEIS, headers=caso.a.headers, json={"nome": "Segundo"})
    assert novo.status_code == (403 if status == "desativado" else 201)
    assert (
        client.post(rota + "/desativacao", headers=caso.a.headers, json={}).status_code == esperado
    )


def test_alheios_sao_404(client, caso):
    rota = f"{RESPONSAVEIS}/{caso.b.responsavel.id}"
    assert client.put(rota, headers=caso.a.headers, json={"nome": "Inválido"}).status_code == 404
    assert client.post(rota + "/desativacao", headers=caso.a.headers, json={}).status_code == 404


@pytest.mark.parametrize("operacao", ["editar", "desativar"])
@pytest.mark.parametrize("falha", ["auditoria", "commit"])
def test_rollback(client, session, caso, monkeypatch, operacao, falha):
    assert (
        client.post(RESPONSAVEIS, headers=caso.a.headers, json={"nome": "Segundo"}).status_code
        == 201
    )

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha simulada US-210")

    rota = f"{RESPONSAVEIS}/{caso.a.responsavel.id}"
    with monkeypatch.context() as m:
        if falha == "auditoria":
            m.setattr(auditoria, "registrar_acao", falhar)
        else:
            m.setattr(session, "commit", falhar)
        resposta = (
            client.put(rota, headers=caso.a.headers, json={"nome": "Alterado"})
            if operacao == "editar"
            else client.post(rota + "/desativacao", headers=caso.a.headers, json={})
        )
    assert resposta.status_code == 500
    session.refresh(caso.a.responsavel)
    assert caso.a.responsavel.ativo and caso.a.responsavel.nome == "Síndica Original"
