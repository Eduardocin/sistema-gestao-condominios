"""Cadastros reais e gestão de funcionários em PostgreSQL migrado, com JWT."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.security import verificar_senha
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import montar_predio

pytestmark = pytest.mark.postgres


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
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client


def conta(**alteracoes):
    return {
        "nome": "Pessoa Fictícia",
        "email": f"{uuid.uuid4().hex}@exemplo.test",
        "telefone": "11987654321",
        "senha": "SenhaFicticia123",
        **alteracoes,
    }


@pytest.mark.parametrize("tipo", ["morador", "administracao"])
def test_cadastro_persiste_hash_e_emite_sessao_sem_condominio(client, session, tipo):
    dados = conta()
    if tipo == "administracao":
        dados["documento"] = "11222333000181"  # CNPJ fictício com dígitos verificadores
    resposta = client.post(f"/api/v1/contas/{tipo}", json=dados)
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["condominio"] is None
    assert corpo["condominios"] == []
    assert corpo["requer_selecao"] is False
    assert corpo["administrador_plataforma"] is False
    usuario = session.get(Usuario, uuid.UUID(corpo["usuario"]["id"]))
    assert usuario.tipo_cadastro == tipo
    assert usuario.senha_hash.startswith("$argon2id$")
    assert verificar_senha(dados["senha"], usuario.senha_hash)
    assert "senha" not in corpo["usuario"]
    assert "senha_hash" not in resposta.text
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {corpo['access_token']}"}
        ).status_code
        == 200
    )
    login = client.post(
        "/api/v1/auth/login", json={"identificador": dados["email"], "senha": dados["senha"]}
    )
    assert login.status_code == 200


@pytest.mark.parametrize("campo", ["email", "telefone", "documento"])
def test_cadastro_traduz_conflitos_de_campos_unicos(client, campo):
    dados = conta(documento="11222333000181")
    assert client.post("/api/v1/contas/administracao", json=dados).status_code == 201
    outra = conta(telefone="11987654322", documento="52998224725")
    outra[campo] = dados[campo]
    if campo == "email":
        outra[campo] = f"  {dados[campo].upper()}  "
    resposta = client.post("/api/v1/contas/administracao", json=outra)
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == f"{campo}_ja_cadastrado"


@pytest.mark.parametrize(
    "tipo,alteracoes",
    [
        ("morador", {"nome": "Ana"}),
        ("morador", {"email": "invalido"}),
        ("morador", {"telefone": "(11)987654321"}),
        ("morador", {"senha": "so_letras"}),
        ("morador", {"senha": "12345678"}),
        ("administracao", {"documento": "11111111111"}),
        ("administracao", {"documento": "52998224724"}),
        ("administracao", {"documento": "11222333000182"}),
        ("administracao", {"documento": "12.222.333/0001-81"}),
        ("morador", {"condominio_id": str(uuid.uuid4())}),
    ],
)
def test_cadastro_rejeita_dados_invalidos_sem_gravar(client, session, tipo, alteracoes):
    dados = conta(documento="52998224725") if tipo == "administracao" else conta()
    resposta = client.post(f"/api/v1/contas/{tipo}", json={**dados, **alteracoes})
    assert resposta.status_code == 422
    assert session.scalar(select(func.count()).select_from(Usuario)) == 0


def funcionario(responsavel_id, **alteracoes):
    return {
        "nome": "Porteiro Fictício",
        "funcao": "porteiro",
        "telefone": "11987654321",
        "email": "porteiro@exemplo.test",
        "foto_arquivo_id": None,
        "responsavel_id": str(responsavel_id),
        **alteracoes,
    }


def responsavel(client, predio):
    resposta = client.post(
        "/api/v1/responsaveis-administracao",
        headers=predio.cabecalho_de("administracao"),
        json={"nome": "Síndica Fictícia"},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["id"]


def test_funcionario_cadastra_desliga_e_preserva_auditoria(client, session):
    predio = montar_predio(session)
    cabecalho = predio.cabecalho_de("administracao")
    responsavel_id = responsavel(client, predio)
    resposta = client.post(
        "/api/v1/funcionarios", headers=cabecalho, json=funcionario(responsavel_id)
    )
    assert resposta.status_code == 201, resposta.text
    id_ = resposta.json()["id"]
    assert resposta.json()["ativo"] is True
    lista = client.get("/api/v1/funcionarios", headers=predio.cabecalho_de("funcionario"))
    assert lista.json()["items"] == [{"id": id_, "nome": "Porteiro Fictício"}]
    desligamento = client.post(
        f"/api/v1/funcionarios/{id_}/desligamento",
        headers=cabecalho,
        json={"responsavel_id": responsavel_id},
    )
    assert desligamento.status_code == 200, desligamento.text
    assert desligamento.json()["ativo"] is False
    assert desligamento.json()["desligado_em"] is not None
    assert client.get("/api/v1/funcionarios", headers=cabecalho).json()["items"] == []
    assert (
        client.get(
            "/api/v1/funcionarios?ativo=false", headers=predio.cabecalho_de("funcionario")
        ).json()["items"]
        == []
    )
    assert (
        len(client.get("/api/v1/funcionarios?ativo=false", headers=cabecalho).json()["items"]) == 1
    )
    assert (
        client.post(
            f"/api/v1/funcionarios/{id_}/desligamento",
            headers=cabecalho,
            json={"responsavel_id": responsavel_id},
        ).status_code
        == 409
    )
    eventos = list(session.scalars(select(RegistroAuditoria).order_by(RegistroAuditoria.id)))
    assert [e.acao for e in eventos] == [
        "responsaveis.alterar",
        "funcionario.cadastrar",
        "funcionario.desativar",
    ]
    assert eventos[-1].responsavel_nome == "Síndica Fictícia"
    assert eventos[-1].usuario_id == predio.administracao.id
    assert eventos[-1].condominio_id == predio.condominio.id
    assert eventos[-1].antes == {"ativo": True}
    assert eventos[-1].depois["ativo"] is False


def test_listagem_isola_condominio_filtra_busca_e_pagina(client, session):
    a, b = montar_predio(session), montar_predio(session, "Prédio B")
    ra, rb = responsavel(client, a), responsavel(client, b)
    for predio, responsavel_id, nome in [
        (a, ra, "Ana Portaria"),
        (a, ra, "Bruno"),
        (b, rb, "Ana B"),
    ]:
        assert (
            client.post(
                "/api/v1/funcionarios",
                headers=predio.cabecalho_de("administracao"),
                json=funcionario(responsavel_id, nome=nome),
            ).status_code
            == 201
        )
    resposta = client.get(
        "/api/v1/funcionarios?busca=ana&page=1&page_size=1", headers=a.cabecalho_de("administracao")
    )
    assert resposta.json()["total"] == 1
    assert [i["nome"] for i in resposta.json()["items"]] == ["Ana Portaria"]
    assert client.get(
        "/api/v1/responsaveis-administracao", headers=a.cabecalho_de("administracao")
    ).json() == [{"id": ra, "nome": "Síndica Fictícia", "ativo": True}]


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma", None])
def test_perfis_sem_permissao_nao_escrevem(client, session, perfil):
    predio = montar_predio(session)
    headers = predio.cabecalho_de(perfil) if perfil else {}
    esperado = 403 if perfil else 401
    assert (
        client.post(
            "/api/v1/funcionarios", headers=headers, json=funcionario(uuid.uuid4())
        ).status_code
        == esperado
    )
    assert (
        client.post(
            "/api/v1/responsaveis-administracao", headers=headers, json={"nome": "Pessoa Fictícia"}
        ).status_code
        == esperado
    )


def test_responsavel_ausente_inativo_ou_de_outro_condominio_nao_grava(client, session):
    a, b = montar_predio(session), montar_predio(session, "Prédio B")
    rb = responsavel(client, b)
    inativo = ResponsavelAdministracao(condominio_id=a.condominio.id, nome="Inativo", ativo=False)
    session.add(inativo)
    session.flush()
    cabecalho = a.cabecalho_de("administracao")
    for id_ in [rb, str(inativo.id), str(uuid.uuid4())]:
        assert (
            client.post(
                "/api/v1/funcionarios", headers=cabecalho, json=funcionario(id_)
            ).status_code
            == 404
        )
    dados = funcionario(rb)
    del dados["responsavel_id"]
    assert client.post("/api/v1/funcionarios", headers=cabecalho, json=dados).status_code == 422
    assert session.scalar(select(func.count()).select_from(Funcionario)) == 0


def test_desligamento_de_outro_condominio_e_404(client, session):
    a, b = montar_predio(session), montar_predio(session, "Prédio B")
    ra, rb = responsavel(client, a), responsavel(client, b)
    id_ = client.post(
        "/api/v1/funcionarios", headers=b.cabecalho_de("administracao"), json=funcionario(rb)
    ).json()["id"]
    resposta = client.post(
        f"/api/v1/funcionarios/{id_}/desligamento",
        headers=a.cabecalho_de("administracao"),
        json={"responsavel_id": ra},
    )
    assert resposta.status_code == 404
    assert session.get(Funcionario, uuid.UUID(id_)).ativo is True


@pytest.mark.parametrize("status", ["pendente", "rejeitado", "desativado"])
def test_bootstrap_responsaveis_disponivel_so_no_cadastro_e_condominio_ativo(
    client, session, status
):
    predio = montar_predio(session)
    predio.condominio.status = status
    if status == "rejeitado":
        predio.condominio.motivo_rejeicao = "Motivo fictício para exercício do fluxo de cadastro"
    session.flush()
    headers = predio.cabecalho_de("administracao")
    resposta = client.post(
        "/api/v1/responsaveis-administracao", headers=headers, json={"nome": "Responsável Fictício"}
    )
    assert resposta.status_code == (403 if status == "desativado" else 201)
    assert client.get("/api/v1/funcionarios", headers=headers).status_code == 403


def test_falha_da_auditoria_reverte_cadastro(client, session):
    from sqlalchemy import event

    predio = montar_predio(session)
    id_ = responsavel(client, predio)

    def falhar(mapper, connection, target):
        if target.acao == "funcionario.cadastrar":
            raise RuntimeError("Falha controlada na persistência da auditoria")

    event.listen(RegistroAuditoria, "before_insert", falhar)
    try:
        resposta = client.post(
            "/api/v1/funcionarios",
            headers=predio.cabecalho_de("administracao"),
            json=funcionario(id_),
        )
    finally:
        event.remove(RegistroAuditoria, "before_insert", falhar)
    assert resposta.status_code == 500
    session.rollback()
    assert session.scalar(select(func.count()).select_from(Funcionario)) == 0
    assert (
        session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.acao == "funcionario.cadastrar")
        )
        == 0
    )


def test_responsavel_nome_duplicado_ignora_caixa_e_espacos(client, session):
    predio = montar_predio(session)
    responsavel(client, predio)
    resposta = client.post(
        "/api/v1/responsaveis-administracao",
        headers=predio.cabecalho_de("administracao"),
        json={"nome": "  SÍNDICA   FICTÍCIA  "},
    )
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "nome_duplicado"
    assert session.scalar(select(func.count()).select_from(ResponsavelAdministracao)) == 1


@pytest.mark.parametrize(
    "alteracoes",
    [
        {"nome": "   "},
        {"funcao": "administrador"},
        {"telefone": "123"},
        {"email": "invalido"},
        {"condominio_id": str(uuid.uuid4())},
    ],
)
def test_funcionario_rejeita_campos_invalidos(client, session, alteracoes):
    predio = montar_predio(session)
    id_ = responsavel(client, predio)
    resposta = client.post(
        "/api/v1/funcionarios",
        headers=predio.cabecalho_de("administracao"),
        json=funcionario(id_, **alteracoes),
    )
    assert resposta.status_code == 422
    assert session.scalar(select(func.count()).select_from(Funcionario)) == 0


def test_funcionario_rejeita_foto_de_outro_condominio(client, session):
    from app.modules.storage.models import Arquivo

    a, b = montar_predio(session), montar_predio(session, "Prédio B")
    id_ = responsavel(client, a)
    foto = Arquivo(
        condominio_id=b.condominio.id,
        chave_storage=f"teste/{uuid.uuid4()}.png",
        nome_original="foto-ficticia.png",
        tipo_mime="image/png",
        tamanho_bytes=10,
        enviado_por_usuario_id=b.administracao.id,
    )
    session.add(foto)
    session.flush()
    resposta = client.post(
        "/api/v1/funcionarios",
        headers=a.cabecalho_de("administracao"),
        json=funcionario(id_, foto_arquivo_id=str(foto.id)),
    )
    assert resposta.status_code == 404
    assert session.scalar(select(func.count()).select_from(Funcionario)) == 0


@pytest.mark.parametrize("motivo", ["outro_autor", "outro_modulo", "valida"])
def test_funcionario_so_usa_foto_propria_do_modulo_fotos(client, session, motivo):
    from app.modules.storage.models import Arquivo

    predio = montar_predio(session)
    responsavel_id = responsavel(client, predio)
    id_ = uuid.uuid4()
    modulo = "ocorrencias" if motivo == "outro_modulo" else "fotos"
    foto = Arquivo(
        id=id_,
        condominio_id=predio.condominio.id,
        chave_storage=f"condominio/{predio.condominio.id}/{modulo}/{id_}",
        nome_original="foto-ficticia.png",
        tipo_mime="image/png",
        tamanho_bytes=10,
        enviado_por_usuario_id=(
            predio.funcionario.id if motivo == "outro_autor" else predio.administracao.id
        ),
    )
    session.add(foto)
    session.flush()
    resposta = client.post(
        "/api/v1/funcionarios",
        headers=predio.cabecalho_de("administracao"),
        json=funcionario(responsavel_id, foto_arquivo_id=str(id_)),
    )
    assert resposta.status_code == (201 if motivo == "valida" else 404)
    if motivo == "valida":
        assert resposta.json()["foto_arquivo_id"] == str(id_)
    else:
        assert session.scalar(select(func.count()).select_from(Funcionario)) == 0
