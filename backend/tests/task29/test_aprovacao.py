import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios import repository
from app.modules.condominios.models import CondominioAnalise, CondominioDocumento, VinculoCondominio
from app.modules.notificacoes.models import EnvioEmail
from app.modules.unidades import service as chaves
from app.modules.unidades.models import ChaveAcesso
from tests.isolamento.cenario import cabecalho, token_de
from tests.task29.conftest import arquivo, pendente

pytestmark = pytest.mark.postgres
BASE = "/api/v1/plataforma/condominios"


def url(caso, acao=""):
    return f"{BASE}/{caso.a.condominio.id}{acao}"


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "administracao"])
@pytest.mark.parametrize("acao", ["fila", "detalhe", "aprovacao", "rejeicao"])
def test_so_adm(client, caso, perfil, acao):
    headers = caso.a.cabecalho_de(perfil)
    if acao == "fila":
        resposta = client.get(BASE, headers=headers)
    elif acao == "detalhe":
        resposta = client.get(url(caso), headers=headers)
    else:
        resposta = client.post(
            url(caso, f"/{acao}"),
            headers=headers,
            json={"motivo": "x"} if acao == "rejeicao" else {},
        )
    assert resposta.status_code == 403


def test_sem_identidade(client):
    assert client.get(BASE).status_code == 401


def test_fila_detalhes_documentos_duplicidades_e_paginacao(client, session, caso):
    pendente(session, caso)
    caso.b.condominio.nome = caso.a.condominio.nome.upper()
    caso.b.condominio.status = "pendente"
    caso.b.condominio.enviado_em += timedelta(days=1)
    doc = arquivo(session, caso.a, mime="application/pdf")
    session.add(CondominioDocumento(condominio_id=caso.a.condominio.id, arquivo_id=doc.id))
    session.commit()
    headers = caso.a.cabecalho_de("plataforma")  # token sem cid
    params = {"busca": caso.a.condominio.nome, "page_size": 1}
    resposta = client.get(BASE, headers=headers, params=params)
    assert resposta.status_code == 200, resposta.text
    pagina = resposta.json()
    assert pagina["total"] == 2 and pagina["page"] == 1 and pagina["page_size"] == 1
    item = pagina["items"][0]
    assert item["id"] == str(caso.a.condominio.id)
    assert item["cnpj"] == "11222333000181" and item["enviado_em"]
    assert item["administracao"] == {
        "nome": caso.a.administracao.nome,
        "email": caso.a.administracao.email,
    }
    assert item["documentos"] == [{"arquivo_id": str(doc.id), "nome_original": doc.nome_original}]
    assert item["estrutura"] == {"blocos": 1, "andares": 1, "unidades": 2}
    assert item["possivel_duplicidade"] == [
        {"id": str(caso.b.condominio.id), "nome": caso.b.condominio.nome, "status": "pendente"}
    ]
    pagina2 = client.get(BASE, headers=headers, params={**params, "page": 2}).json()
    assert pagina2["items"][0]["id"] == str(caso.b.condominio.id)
    assert client.get(BASE, headers=headers, params={**params, "page": 3}).json()["items"] == []
    assert (
        client.get(BASE, headers=headers, params={"busca": "11222333000181"}).json()["total"] == 1
    )
    assert client.get(BASE, headers=headers, params={"busca": "%"}).json()["total"] == 0
    assert (
        client.get(BASE, headers=headers, params={**params, "status": "ativo"}).json()["total"] == 0
    )
    detalhe = client.get(url(caso), headers=headers).json()
    assert detalhe["documentos"] == item["documentos"]
    assert len(detalhe["blocos"][0]["andares"][0]["unidades"]) == 2
    assert detalhe["analises"][0]["evento"] == "enviado"
    assert "chave" not in json.dumps(detalhe)
    assert client.get(f"{BASE}/{uuid.uuid4()}", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "params", [{"status": "x"}, {"page": 0}, {"page_size": 101}, {"page_size": 0}]
)
def test_filtros_invalidos(client, caso, params):
    assert (
        client.get(BASE, headers=caso.a.cabecalho_de("plataforma"), params=params).status_code
        == 422
    )


def test_aprovacao_atomica_com_uma_chave_por_unidade_ativa(client, session, caso):
    pendente(session, caso)
    caso.a.unidade_102.ativo = False
    session.commit()
    resposta = client.post(
        url(caso, "/aprovacao"), headers=caso.a.cabecalho_de("plataforma"), json={}
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "ativo" and resposta.json()["aprovado_em"]
    session.expire_all()
    assert caso.a.condominio.status == "ativo"
    chave = session.scalars(
        select(ChaveAcesso).where(ChaveAcesso.condominio_id == caso.a.condominio.id)
    ).one()
    assert chave.unidade_id == caso.a.unidade_101.id and chave.revogada_em is None
    assert len(chave.codigo) == 10 and set(chave.codigo) <= set(chaves.ALFABETO_CHAVE)
    email = session.scalars(
        select(EnvioEmail).where(EnvioEmail.condominio_id == caso.a.condominio.id)
    ).one()
    assert email.status == "pendente" and email.evento == "condominio_aprovado"
    assert email.destinatario == caso.a.administracao.email
    assert email.recurso_tipo == "condominio" and email.recurso_id == caso.a.condominio.id
    analise = session.scalars(
        select(CondominioAnalise).where(
            CondominioAnalise.condominio_id == caso.a.condominio.id,
            CondominioAnalise.evento == "aprovado",
        )
    ).one()
    assert (
        analise.usuario_id == caso.a.adm.id and analise.criado_em == caso.a.condominio.aprovado_em
    )
    evento = session.scalars(
        select(RegistroAuditoria).where(
            RegistroAuditoria.condominio_id == caso.a.condominio.id,
            RegistroAuditoria.acao == "condominio.aprovar",
        )
    ).one()
    assert evento.usuario_id == caso.a.adm.id and evento.perfil == "plataforma"
    assert evento.criado_em and str(evento.ip) == "203.0.113.27"
    assert evento.depois == {"status": "ativo", "chaves_geradas": 1}
    assert chave.codigo not in json.dumps(evento.depois)
    assert (
        client.get("/api/v1/unidades", headers=caso.a.cabecalho_de("plataforma")).status_code == 403
    )


def test_rejeicao_e_leitura_autorizada_do_motivo(client, session, caso):
    pendente(session, caso)
    resposta = client.post(
        url(caso, "/rejeicao"),
        headers=caso.a.cabecalho_de("plataforma"),
        json={"motivo": "  Documento ilegível.  "},
    )
    assert resposta.status_code == 200
    assert resposta.json()["motivo_rejeicao"] == "Documento ilegível."
    consulta = client.get("/api/v1/condominio", headers=caso.a.cabecalho_de("administracao"))
    assert consulta.status_code == 200
    assert consulta.json()["motivo_rejeicao"] == "Documento ilegível."
    assert [a["evento"] for a in consulta.json()["analises"]] == ["enviado", "rejeitado"]
    evento = session.scalars(
        select(RegistroAuditoria).where(
            RegistroAuditoria.acao == "condominio.rejeitar",
            RegistroAuditoria.condominio_id == caso.a.condominio.id,
        )
    ).one()
    assert evento.usuario_id == caso.a.adm.id and evento.depois["motivo"] == "Documento ilegível."
    assert (
        session.scalar(
            select(func.count())
            .select_from(EnvioEmail)
            .where(EnvioEmail.condominio_id == caso.a.condominio.id)
        )
        == 0
    )
    assert (
        client.get("/api/v1/unidades", headers=caso.a.cabecalho_de("administracao")).status_code
        == 403
    )
    assert client.get("/api/v1/condominio", headers=caso.b.cabecalho_de("administracao")).json()[
        "id"
    ] == str(caso.b.condominio.id)
    session.query(VinculoCondominio).filter_by(
        usuario_id=caso.a.administracao.id, condominio_id=caso.a.condominio.id
    ).one().ativo = False
    session.commit()
    assert (
        client.get("/api/v1/condominio", headers=caso.a.cabecalho_de("administracao")).status_code
        == 403
    )


def test_desativar_reativar_preserva_vinculos_e_registra_auditoria(client, session, caso):
    headers = caso.a.cabecalho_de("plataforma")
    desativacao = client.post(url(caso, "/desativacao"), headers=headers, json={})
    assert desativacao.status_code == 200, desativacao.text
    assert desativacao.json()["status"] == "desativado"
    session.expire_all()
    assert caso.a.condominio.status == "desativado"
    assert (
        session.scalar(
            select(func.count())
            .select_from(VinculoCondominio)
            .where(
                VinculoCondominio.condominio_id == caso.a.condominio.id,
                VinculoCondominio.ativo.is_(True),
            )
        )
        == 3
    )
    assert (
        client.get("/api/v1/unidades", headers=caso.a.cabecalho_de("administracao")).status_code
        == 403
    )

    evento = session.scalars(
        select(RegistroAuditoria).where(
            RegistroAuditoria.condominio_id == caso.a.condominio.id,
            RegistroAuditoria.acao == "condominio.desativar",
        )
    ).one()
    assert evento.usuario_id == caso.a.adm.id and evento.perfil == "plataforma"
    assert evento.antes == {"status": "ativo"}
    assert evento.depois == {"status": "desativado"}
    assert str(evento.ip) == "203.0.113.27"

    reativacao = client.post(url(caso, "/reativacao"), headers=headers, json={})
    assert reativacao.status_code == 200 and reativacao.json()["status"] == "ativo"
    assert [item["evento"] for item in reativacao.json()["analises"]][-2:] == [
        "desativado",
        "reativado",
    ]
    assert (
        client.get("/api/v1/unidades", headers=caso.a.cabecalho_de("administracao")).status_code
        == 200
    )
    assert client.post(url(caso, "/reativacao"), headers=headers, json={}).status_code == 409


@pytest.mark.parametrize("acao", ["desativacao", "reativacao"])
def test_transicao_de_status_exige_ativo_ou_desativado(client, session, caso, acao):
    pendente(session, caso)
    resposta = client.post(
        url(caso, f"/{acao}"),
        headers=caso.a.cabecalho_de("plataforma"),
        json={"campo_extra": "nao-permitido"},
    )
    assert resposta.status_code == 422
    assert caso.a.condominio.status == "pendente"


@pytest.mark.parametrize(
    ("status", "acao"),
    [("pendente", "desativacao"), ("ativo", "reativacao"), ("rejeitado", "reativacao")],
)
def test_status_so_muda_pelas_transicoes_permitidas(client, session, caso, status, acao):
    caso.a.condominio.status = status
    caso.a.condominio.motivo_rejeicao = "Cadastro incompleto" if status == "rejeitado" else None
    session.commit()
    resposta = client.post(
        url(caso, f"/{acao}"), headers=caso.a.cabecalho_de("plataforma"), json={}
    )
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "transicao_invalida"
    session.refresh(caso.a.condominio)
    assert caso.a.condominio.status == status


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "administracao"])
def test_transicao_de_status_exclusiva_da_plataforma(client, caso, perfil):
    resposta = client.post(
        url(caso, "/desativacao"),
        headers=caso.a.cabecalho_de(perfil),
        json={},
    )
    assert resposta.status_code == 403


def test_falha_de_auditoria_reverte_desativacao(client, session, caso, monkeypatch):
    def falhar(*args, **kwargs):
        raise RuntimeError("Falha simulada na auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    resposta = client.post(
        url(caso, "/desativacao"),
        headers=caso.a.cabecalho_de("plataforma"),
        json={},
    )
    assert resposta.status_code == 500
    session.refresh(caso.a.condominio)
    assert caso.a.condominio.status == "ativo"


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"motivo": ""},
        {"motivo": " "},
        {"motivo": "x" * 501},
        {"motivo": "x", "email": "arbitrario@example.test"},
    ],
)
def test_rejeicao_exige_motivo_valido(client, session, caso, corpo):
    pendente(session, caso)
    assert (
        client.post(
            url(caso, "/rejeicao"), headers=caso.a.cabecalho_de("plataforma"), json=corpo
        ).status_code
        == 422
    )
    assert caso.a.condominio.status == "pendente"


@pytest.mark.parametrize("estado", ["ativo", "rejeitado", "desativado"])
@pytest.mark.parametrize("acao", ["aprovacao", "rejeicao"])
def test_transicoes_invalidas(client, session, caso, estado, acao):
    caso.a.condominio.status = estado
    caso.a.condominio.motivo_rejeicao = "Motivo anterior" if estado == "rejeitado" else None
    session.commit()
    resposta = client.post(
        url(caso, f"/{acao}"),
        headers=caso.a.cabecalho_de("plataforma"),
        json={"motivo": "x"} if acao == "rejeicao" else {},
    )
    assert (
        resposta.status_code == 409 and resposta.json()["error"]["reason"] == "transicao_invalida"
    )


@pytest.mark.parametrize("etapa", ["chave", "historico", "email", "auditoria"])
def test_falha_reverte_todos_os_efeitos(client, session, caso, monkeypatch, etapa):
    pendente(session, caso)
    modulo, nome = {
        "chave": (chaves.repository, "inserir_chave"),
        "historico": (repository, "registrar_decisao"),
        "email": (repository, "enfileirar_aprovacao"),
        "auditoria": (auditoria, "registrar_acao"),
    }[etapa]
    original = getattr(modulo, nome)
    chamadas = []

    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        chamadas.append(1)
        if etapa != "chave" or len(chamadas) == 2:
            raise RuntimeError("Falha simulada após persistir")

    monkeypatch.setattr(modulo, nome, falhar)
    resposta = client.post(
        url(caso, "/aprovacao"), headers=caso.a.cabecalho_de("plataforma"), json={}
    )
    assert resposta.status_code == 500
    session.expire_all()
    assert caso.a.condominio.status == "pendente" and caso.a.condominio.aprovado_em is None
    for modelo in (ChaveAcesso, EnvioEmail, RegistroAuditoria):
        assert (
            session.scalar(
                select(func.count())
                .select_from(modelo)
                .where(modelo.condominio_id == caso.a.condominio.id)
            )
            == 0
        )
    assert (
        session.scalar(
            select(func.count())
            .select_from(CondominioAnalise)
            .where(CondominioAnalise.condominio_id == caso.a.condominio.id)
        )
        == 1
    )


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma"])
def test_leitura_de_cadastro_restrita(client, caso, perfil):
    assert client.get("/api/v1/condominio", headers=caso.a.cabecalho_de(perfil)).status_code == 403


def test_leitura_sem_cid_e_cid_forjado_nao_autorizam(client, caso):
    for cid in (None, caso.b.condominio.id):
        headers = cabecalho(token_de(caso.a.administracao, cid, perfil="administracao"))
        assert client.get("/api/v1/condominio", headers=headers).status_code == 403


def test_aprovacao_nao_aceita_email_arbitrario_e_legado_sem_criador(client, session, caso):
    pendente(session, caso)
    headers = caso.a.cabecalho_de("plataforma")
    assert (
        client.post(
            url(caso, "/aprovacao"), headers=headers, json={"email": "arbitrario@exemplo.test"}
        ).status_code
        == 422
    )
    caso.a.condominio.criado_por_usuario_id = None
    session.commit()
    resposta = client.post(url(caso, "/aprovacao"), headers=headers, json={})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "cadastro_sem_administracao"
    session.expire_all()
    assert caso.a.condominio.status == "pendente"
    assert not list(
        session.scalars(
            select(ChaveAcesso).where(ChaveAcesso.condominio_id == caso.a.condominio.id)
        )
    )


def test_duplicidade_por_endereco_sem_confundir_dados_ausentes(client, session, caso):
    pendente(session, caso)
    for predio in (caso.a, caso.b):
        predio.condominio.logradouro = "Rua da Aurora"
        predio.condominio.numero = "100"
    session.commit()
    headers = caso.a.cabecalho_de("plataforma")
    assert client.get(url(caso), headers=headers).json()["possivel_duplicidade"][0]["id"] == str(
        caso.b.condominio.id
    )
    caso.b.condominio.numero = "200"
    session.commit()
    assert client.get(url(caso), headers=headers).json()["possivel_duplicidade"] == []
    caso.a.condominio.cidade = None
    caso.b.condominio.cidade = None
    caso.b.condominio.nome = caso.a.condominio.nome
    session.commit()
    assert client.get(url(caso), headers=headers).json()["possivel_duplicidade"] == []
