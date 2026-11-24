"""TASK-57: correção e reenvio com PostgreSQL, JWT e auditoria reais."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.tempo import get_relogio
from app.main import create_app
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios import repository
from app.modules.condominios.models import Condominio, CondominioAnalise, VinculoCondominio
from app.modules.notificacoes.models import EnvioEmail
from app.modules.unidades.models import Andar, Bloco, ChaveAcesso, MoradorUnidade
from tests.auditoria.conftest import cenario as cenario
from tests.isolamento.cenario import cabecalho, token_de
from tests.task29.conftest import caso as caso
from tests.task29.conftest import client as client
from tests.task29.conftest import pendente
from tests.task29.conftest import session as session

pytestmark = pytest.mark.postgres
BASE = "/api/v1/condominio"


@pytest.fixture
def rejeitado(session, caso):
    pendente(session, caso)
    caso.a.condominio.status = "rejeitado"
    caso.a.condominio.motivo_rejeicao = "Corrigir dados e identificação."
    session.add(
        CondominioAnalise(
            condominio_id=caso.a.condominio.id,
            usuario_id=caso.a.adm.id,
            evento="rejeitado",
            motivo=caso.a.condominio.motivo_rejeicao,
            criado_em=caso.a.condominio.enviado_em + timedelta(days=1),
        )
    )
    session.commit()
    return caso


def dados(caso):
    return {
        "nome": "Residencial Corrigido",
        "cnpj": "04252011000110",
        "endereco": {
            "cep": "50030230",
            "logradouro": "Rua da Aurora",
            "numero": "123",
            "complemento": None,
            "bairro": "Boa Vista",
            "cidade": "Recife",
            "uf": "pe",
        },
        "responsavel_id": str(caso.responsavel.id),
    }


def escritas(caso):
    responsavel = {"responsavel_id": str(caso.responsavel.id)}
    return [
        ("put", BASE, dados(caso)),
        ("put", f"/api/v1/estrutura/blocos/{caso.bloco.id}", responsavel | {"nome": "Bloco B"}),
        (
            "put",
            f"/api/v1/estrutura/andares/{caso.andar.id}",
            responsavel | {"nome": "Primeiro", "ordem": 1},
        ),
        (
            "put",
            f"/api/v1/estrutura/unidades/{caso.a.unidade_101.id}",
            responsavel | {"identificacao": "101-A"},
        ),
        ("post", BASE + "/reenvio", responsavel),
    ]


def eventos(session, condominio_id):
    return list(
        session.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.condominio_id == condominio_id,
                RegistroAuditoria.acao.in_(
                    ["condominio.editar", "estrutura.editar", "condominio.reenviar"]
                ),
            )
            .order_by(RegistroAuditoria.id)
        )
    )


def test_consulta_e_correcao_de_dados_preservam_rejeicao(client, session, rejeitado):
    c = rejeitado
    headers = c.a.cabecalho_de("administracao")
    original_envio = c.a.condominio.enviado_em
    consulta = client.get(BASE, headers=headers)
    assert consulta.status_code == 200
    assert consulta.json()["motivo_rejeicao"] == "Corrigir dados e identificação."
    resposta = client.put(BASE, headers=headers, json=dados(c))
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["id"] == str(c.a.condominio.id)
    assert corpo["nome"] == dados(c)["nome"] and corpo["cnpj"] == dados(c)["cnpj"]
    assert corpo["endereco"]["uf"] == "PE"
    assert corpo["status"] == "rejeitado"
    assert corpo["analises"] == consulta.json()["analises"]
    session.refresh(c.a.condominio)
    assert c.a.condominio.enviado_em == original_envio
    [evento] = eventos(session, c.a.condominio.id)
    assert evento.acao == "condominio.editar"
    assert evento.antes["nome"] != evento.depois["nome"]
    assert evento.depois["cnpj"] != dados(c)["cnpj"]
    assert evento.usuario_id == c.a.administracao.id
    assert evento.responsavel_nome == c.responsavel.nome
    assert str(evento.ip) == "203.0.113.27"
    assert client.get("/api/v1/encomendas", headers=headers).status_code == 403


def test_corrige_estrutura_sem_recriar_ids_ou_vinculos(client, session, rejeitado):
    c = rejeitado
    headers = c.a.cabecalho_de("administracao")
    antes = client.get(BASE + "/estrutura", headers=headers)
    assert antes.status_code == 200, antes.text
    bloco_antes = antes.json()["blocos"][0]
    moradores = list(session.scalars(select(MoradorUnidade.id)))
    vinculos = list(session.scalars(select(VinculoCondominio.id)))
    for metodo, rota, corpo in escritas(c)[1:4]:
        resposta = client.request(metodo, rota, headers=headers, json=corpo)
        assert resposta.status_code == 200, resposta.text
    bloco = client.get(BASE + "/estrutura", headers=headers).json()["blocos"][0]
    assert bloco["id"] == bloco_antes["id"] and bloco["nome"] == "Bloco B"
    assert bloco["andares"][0]["id"] == bloco_antes["andares"][0]["id"]
    assert bloco["andares"][0]["nome"] == "Primeiro"
    assert bloco["andares"][0]["ordem"] == 1
    unidades = bloco["andares"][0]["unidades"]
    assert {u["id"] for u in unidades} == {u["id"] for u in bloco_antes["andares"][0]["unidades"]}
    assert (
        next(u for u in unidades if u["id"] == str(c.a.unidade_101.id))["identificacao"] == "101-A"
    )
    assert list(session.scalars(select(MoradorUnidade.id))) == moradores
    assert list(session.scalars(select(VinculoCondominio.id))) == vinculos
    registros = eventos(session, c.a.condominio.id)
    assert [e.recurso_tipo for e in registros] == ["bloco", "andar", "unidade"]
    assert all(e.acao == "estrutura.editar" for e in registros)
    assert all(e.responsavel_nome == c.responsavel.nome for e in registros)


def test_reenvios_preservam_todas_as_rejeicoes(client, session, rejeitado):
    c = rejeitado
    headers = c.a.cabecalho_de("administracao")
    instante = datetime(2026, 11, 21, 12, tzinfo=UTC)
    client.app.dependency_overrides[get_relogio] = lambda: lambda: instante
    corpo = {"responsavel_id": str(c.responsavel.id)}
    resposta = client.post(BASE + "/reenvio", headers=headers, json=corpo)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "pendente"
    assert resposta.json()["motivo_rejeicao"] is None
    assert datetime.fromisoformat(resposta.json()["enviado_em"]) == instante
    session.refresh(c.a.condominio)
    assert c.a.condominio.motivo_rejeicao is None
    assert c.a.condominio.enviado_em == instante
    assert [a["evento"] for a in resposta.json()["analises"]] == [
        "enviado",
        "rejeitado",
        "reenviado",
    ]
    fila = client.get(
        "/api/v1/plataforma/condominios",
        headers=c.a.cabecalho_de("plataforma"),
        params={"busca": c.a.condominio.cnpj},
    )
    assert fila.json()["items"][0]["id"] == str(c.a.condominio.id)
    assert client.post(BASE + "/reenvio", headers=headers, json=corpo).status_code == 409
    assert client.get("/api/v1/encomendas", headers=headers).status_code == 403

    rejeicao = client.post(
        f"/api/v1/plataforma/condominios/{c.a.condominio.id}/rejeicao",
        headers=c.a.cabecalho_de("plataforma"),
        json={"motivo": "Segunda rejeição."},
    )
    assert rejeicao.status_code == 200
    instante += timedelta(minutes=1)
    segunda = client.post(BASE + "/reenvio", headers=headers, json=corpo)
    assert segunda.status_code == 200
    assert [a["motivo"] for a in segunda.json()["analises"] if a["evento"] == "rejeitado"] == [
        "Corrigir dados e identificação.",
        "Segunda rejeição.",
    ]
    registros = eventos(session, c.a.condominio.id)
    assert len(registros) == 2
    assert all(e.acao == "condominio.reenviar" for e in registros)
    assert all(e.antes == {"status": "rejeitado"} for e in registros)
    assert all(e.depois["status"] == "pendente" for e in registros)
    assert all(e.responsavel_nome == c.responsavel.nome for e in registros)


@pytest.mark.parametrize("estado", ["pendente", "ativo", "desativado"])
def test_reenvio_exige_estado_rejeitado(client, session, rejeitado, estado):
    c = rejeitado
    c.a.condominio.status = estado
    session.commit()
    metodo, rota, corpo = escritas(c)[-1]
    resposta = client.request(metodo, rota, headers=c.a.cabecalho_de("administracao"), json=corpo)
    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["error"]["reason"] == "transicao_invalida"
    session.refresh(c.a.condominio)
    assert c.a.condominio.status == estado
    assert eventos(session, c.a.condominio.id) == []


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma"])
def test_perfis_sem_autorizacao(client, session, rejeitado, perfil):
    c = rejeitado
    headers = c.a.cabecalho_de(perfil)
    assert client.get(BASE + "/estrutura", headers=headers).status_code == 403
    for metodo, rota, corpo in escritas(c):
        assert client.request(metodo, rota, headers=headers, json=corpo).status_code == 403
    assert eventos(session, c.a.condominio.id) == []


def test_identidade_vinculo_e_ids_de_outro_condominio(client, session, rejeitado):
    c = rejeitado
    assert client.post(BASE + "/reenvio", json={}).status_code == 401
    for cid in (None, c.b.condominio.id):
        headers = cabecalho(token_de(c.a.administracao, cid, perfil="administracao"))
        assert client.get(BASE, headers=headers).status_code == 403
        assert client.get(BASE + "/estrutura", headers=headers).status_code == 403
        for metodo, rota, corpo in escritas(c):
            assert client.request(metodo, rota, headers=headers, json=corpo).status_code == 403

    bloco = Bloco(condominio_id=c.b.condominio.id, nome="Bloco de B")
    session.add(bloco)
    session.flush()
    andar = Andar(condominio_id=c.b.condominio.id, bloco_id=bloco.id, nome="Andar B", ordem=0)
    session.add(andar)
    session.commit()
    headers = c.a.cabecalho_de("administracao")
    for (_, rota, corpo), id_ in zip(
        escritas(c)[1:4], [bloco.id, andar.id, c.b.unidade_101.id], strict=True
    ):
        resposta = client.put(rota.rsplit("/", 1)[0] + f"/{id_}", headers=headers, json=corpo)
        assert resposta.status_code == 404
    session.refresh(c.b.condominio)
    assert c.b.condominio.status == "ativo"
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == c.a.administracao.id,
            VinculoCondominio.condominio_id == c.a.condominio.id,
        )
    )
    vinculo.ativo = False
    session.commit()
    assert (
        client.post(BASE + "/reenvio", headers=headers, json=escritas(c)[-1][2]).status_code == 403
    )
    assert eventos(session, c.a.condominio.id) == []


def test_responsavel_obrigatorio_e_campos_protegidos(client, session, rejeitado):
    c = rejeitado
    headers = c.a.cabecalho_de("administracao")
    for metodo, rota, corpo in escritas(c):
        sem_responsavel = {k: v for k, v in corpo.items() if k != "responsavel_id"}
        assert (
            client.request(metodo, rota, headers=headers, json=sem_responsavel).status_code == 422
        )
    assert (
        client.post(
            BASE + "/reenvio",
            headers=headers,
            json={"responsavel_id": str(c.outro.id)},
        ).status_code
        == 404
    )
    c.responsavel.ativo = False
    session.commit()
    assert (
        client.post(BASE + "/reenvio", headers=headers, json=escritas(c)[-1][2]).status_code == 404
    )
    assert (
        client.put(BASE, headers=headers, json=dados(c) | {"status": "pendente"}).status_code == 422
    )
    assert (
        client.put(
            BASE, headers=headers, json=dados(c) | {"documentos": [str(uuid.uuid4())]}
        ).status_code
        == 422
    )
    session.refresh(c.a.condominio)
    assert c.a.condominio.status == "rejeitado"
    assert eventos(session, c.a.condominio.id) == []


def test_validacao_e_cnpj_duplicado_nao_alteram_dados(client, session, rejeitado):
    c = rejeitado
    headers = c.a.cabecalho_de("administracao")
    nome = c.a.condominio.nome
    assert (
        client.put(BASE, headers=headers, json=dados(c) | {"cnpj": "00000000000000"}).status_code
        == 422
    )
    resposta = client.put(BASE, headers=headers, json=dados(c) | {"cnpj": c.b.condominio.cnpj})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "cnpj_ja_cadastrado"
    for _, rota, corpo in escritas(c)[1:4]:
        campo, valor = (
            ("ordem", True)
            if "/andares/" in rota
            else (("identificacao", "@") if "/unidades/" in rota else ("nome", " "))
        )
        assert client.put(rota, headers=headers, json=corpo | {campo: valor}).status_code == 422
    session.refresh(c.a.condominio)
    assert c.a.condominio.nome == nome
    assert c.a.condominio.cnpj == "11222333000181"
    assert eventos(session, c.a.condominio.id) == []


@pytest.mark.parametrize("tipo", ["bloco", "andar", "unidade"])
def test_nome_duplicado_preserva_estrutura(client, session, rejeitado, tipo):
    c = rejeitado
    if tipo == "bloco":
        session.add(Bloco(condominio_id=c.a.condominio.id, nome="Bloco B"))
        _, rota, corpo = escritas(c)[1]
    elif tipo == "andar":
        session.add(
            Andar(condominio_id=c.a.condominio.id, bloco_id=c.bloco.id, nome="Primeiro", ordem=1)
        )
        _, rota, corpo = escritas(c)[2]
    else:
        _, rota, corpo = escritas(c)[3]
        corpo["identificacao"] = c.a.unidade_102.identificacao
    session.commit()
    resposta = client.put(rota, headers=c.a.cabecalho_de("administracao"), json=corpo)
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "nome_duplicado"
    session.refresh(c.bloco)
    session.refresh(c.andar)
    session.refresh(c.a.unidade_101)
    assert c.bloco.nome == "Bloco A" and c.andar.nome == "Térreo"
    assert c.a.unidade_101.identificacao == "Bloco A / 101"
    assert eventos(session, c.a.condominio.id) == []


@pytest.mark.parametrize("operacao", range(5))
def test_falha_apos_auditoria_reverte_toda_a_escrita(
    client, session, rejeitado, monkeypatch, operacao
):
    c = rejeitado
    original = auditoria.registrar_acao
    nome, envio = c.a.condominio.nome, c.a.condominio.enviado_em

    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Falha controlada depois do flush da auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    metodo, rota, corpo = escritas(c)[operacao]
    resposta = client.request(metodo, rota, headers=c.a.cabecalho_de("administracao"), json=corpo)
    assert resposta.status_code == 500
    session.refresh(c.a.condominio)
    session.refresh(c.bloco)
    session.refresh(c.andar)
    session.refresh(c.a.unidade_101)
    assert c.a.condominio.nome == nome
    assert c.a.condominio.status == "rejeitado"
    assert c.a.condominio.enviado_em == envio
    assert c.a.condominio.motivo_rejeicao == "Corrigir dados e identificação."
    assert c.bloco.nome == "Bloco A" and c.andar.nome == "Térreo"
    assert c.andar.ordem == 0 and c.a.unidade_101.identificacao == "Bloco A / 101"
    assert len(repository.historico(session, c.a.condominio.id)) == 2
    assert eventos(session, c.a.condominio.id) == []


@pytest.fixture
def concorrente(cenario):
    c = cenario
    with c.fabrica() as session:
        condominio = session.get(Condominio, c.a.condominio.id)
        condominio.status = "rejeitado"
        condominio.motivo_rejeicao = "Correção necessária"
        condominio.criado_por_usuario_id = c.a.administracao.id
        session.add(
            CondominioAnalise(
                condominio_id=condominio.id,
                usuario_id=c.a.adm.id,
                evento="rejeitado",
                motivo=condominio.motivo_rejeicao,
            )
        )
        session.commit()
    try:
        yield c
    finally:
        with c.fabrica() as session:
            for model in (EnvioEmail, ChaveAcesso, CondominioAnalise):
                session.execute(delete(model).where(model.condominio_id == c.a.condominio.id))
            session.commit()


@pytest.mark.parametrize("segunda", ["reenvio", "aprovacao", "edicao"])
def test_reenvio_serializado_com_outro_reenvio_decisao_ou_edicao(concorrente, monkeypatch, segunda):
    c = concorrente
    barreira = threading.Barrier(2)
    obter_cadastro, obter_plataforma = repository.obter_do_cadastro, repository.obter_plataforma

    def bloquear_cadastro(*args, **kwargs):
        if kwargs.get("bloquear"):
            barreira.wait(timeout=10)
        return obter_cadastro(*args, **kwargs)

    def bloquear_plataforma(*args, **kwargs):
        if kwargs.get("bloquear"):
            barreira.wait(timeout=10)
        return obter_plataforma(*args, **kwargs)

    monkeypatch.setattr(repository, "obter_do_cadastro", bloquear_cadastro)
    monkeypatch.setattr(repository, "obter_plataforma", bloquear_plataforma)
    responsavel = {"responsavel_id": str(c.responsavel.id)}

    def enviar(acao):
        with TestClient(create_app()) as client:
            if acao == "aprovacao":
                return client.post(
                    f"/api/v1/plataforma/condominios/{c.a.condominio.id}/aprovacao",
                    headers=c.a.cabecalho_de("plataforma"),
                    json={},
                )
            if acao == "edicao":
                return client.put(
                    BASE,
                    headers=c.a.cabecalho_de("administracao"),
                    json={
                        "nome": "Nome corrigido na disputa",
                        "cnpj": "04252011000110",
                        "endereco": dados(c)["endereco"],
                        **responsavel,
                    },
                )
            return client.post(
                BASE + "/reenvio", headers=c.a.cabecalho_de("administracao"), json=responsavel
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(enviar, ["reenvio", segunda]))
    if segunda == "reenvio":
        assert sorted(r.status_code for r in respostas) == [200, 409]
    else:
        assert respostas[0].status_code == 200, respostas[0].text
        assert respostas[1].status_code in {200, 409}, respostas[1].text
    with c.fabrica() as session:
        condominio = session.get(Condominio, c.a.condominio.id)
        aprovado = segunda == "aprovacao" and respostas[1].status_code == 200
        assert condominio.status == ("ativo" if aprovado else "pendente")
        assert condominio.motivo_rejeicao is None
        historico = repository.historico(session, condominio.id)
        assert [a.evento for a in historico].count("reenviado") == 1
        assert [a.evento for a in historico].count("aprovado") == int(aprovado)
        assert (
            len([e for e in eventos(session, condominio.id) if e.acao == "condominio.reenviar"])
            == 1
        )
        if segunda == "edicao":
            assert (condominio.nome == "Nome corrigido na disputa") == (
                respostas[1].status_code == 200
            )
