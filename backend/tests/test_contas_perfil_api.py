"""TASK-27: perfil global e auditoria transacional, usando PostgreSQL e autenticação real."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.rate_limit import get_login_rate_limiter
from app.modules.condominios.models import VinculoCondominio
from app.modules.contas import repository
from app.modules.storage.models import Arquivo
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import montar_predio
from tests.test_contas_funcionarios_api import conta
from tests.test_contas_funcionarios_api import session as sessao_postgres

# Reutiliza a fixture PostgreSQL existente, incluindo a transação externa de limpeza.
session = sessao_postgres

pytestmark = pytest.mark.postgres
ME = "/api/v1/contas/me"


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
    with TestClient(app, client=("203.0.113.27", 50000), raise_server_exceptions=False) as client:
        yield client
    get_login_rate_limiter().resetar()


def cadastrar(client, tipo="morador", **campos):
    dados = conta(**campos)
    if tipo == "administracao":
        dados.setdefault("documento", "52998224725")
    resposta = client.post(f"/api/v1/contas/{tipo}", json=dados)
    assert resposta.status_code == 201, resposta.text
    sessao = resposta.json()
    return {"Authorization": f"Bearer {sessao['access_token']}"}, sessao, dados


def editar(dados, **campos):
    return {chave: dados[chave] for chave in ("nome", "email", "telefone")} | campos


def eventos(session, usuario_id):
    return list(
        session.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.recurso_id == uuid.UUID(str(usuario_id)),
                RegistroAuditoria.acao.in_(["conta.criar", "conta.editar"]),
            )
            .order_by(RegistroAuditoria.id)
        )
    )


@pytest.mark.parametrize(
    "tipo,documento",
    [("morador", None), ("administracao", "52998224725"), ("administracao", "11222333000181")],
)
def test_cadastro_auditado_e_perfil_sem_condominio(client, session, tipo, documento):
    campos = {"documento": documento} if documento else {}
    headers, sessao, dados = cadastrar(client, tipo, **campos)
    id_ = sessao["usuario"]["id"]
    resposta = client.get(ME, headers=headers)
    assert resposta.status_code == 200
    assert resposta.json() == {
        "id": id_,
        "nome": dados["nome"],
        "email": dados["email"],
        "telefone": dados["telefone"],
        "tipo_cadastro": tipo,
        "documento": documento,
        "foto_arquivo_id": None,
    }
    assert sessao["condominio"] is None and sessao["condominios"] == []
    assert (
        session.scalar(
            select(func.count())
            .select_from(VinculoCondominio)
            .where(VinculoCondominio.usuario_id == uuid.UUID(id_))
        )
        == 0
    )
    assert client.get("/api/v1/avisos", headers=headers).status_code == 403
    (registro,) = eventos(session, id_)
    assert registro.acao == "conta.criar" and registro.recurso_tipo == "usuario"
    assert registro.usuario_id == uuid.UUID(id_)
    assert registro.condominio_id is None and registro.perfil is None
    assert registro.responsavel_nome is None and str(registro.ip) == "203.0.113.27"
    assert registro.antes == {} and registro.depois["tipo_cadastro"] == tipo
    if documento:
        assert registro.depois["documento"] != documento
        assert "*" in registro.depois["documento"]
    gravado = json.dumps(registro.depois)
    assert all(
        segredo not in gravado
        for segredo in [dados["senha"], "$argon2", "senha_hash", "access_token", "refresh_token"]
    )
    assert "senha" not in resposta.text and "token" not in resposta.text


@pytest.mark.parametrize("tipo", ["morador", "administracao"])
def test_editar_perfil_preserva_identidade_senha_e_sessao(client, session, tipo):
    headers, sessao, dados = cadastrar(client, tipo)
    id_ = uuid.UUID(sessao["usuario"]["id"])
    usuario = session.get(Usuario, id_)
    hash_original, versao = usuario.senha_hash, usuario.sessao_versao
    documento = usuario.documento
    novos = editar(
        dados, nome="  Novo   Nome  ", email="  NOVO@EXEMPLO.TEST  ", telefone="11987654322"
    )
    resposta = client.put(ME, headers=headers, json=novos)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["id"] == str(id_)
    assert resposta.json()["nome"] == "Novo Nome"
    assert resposta.json()["email"] == "novo@exemplo.test"
    assert resposta.json()["telefone"] == "11987654322"
    assert resposta.json()["documento"] == documento
    session.expire_all()
    usuario = session.get(Usuario, id_)
    assert usuario.senha_hash == hash_original and usuario.sessao_versao == versao
    assert usuario.tipo_cadastro == tipo and usuario.administrador_plataforma is False
    # A conta continua global e a edição não derruba a sessão nem troca a senha.
    assert client.get(ME, headers=headers).json() == resposta.json()
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": sessao["refresh_token"]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"identificador": "novo@exemplo.test", "senha": dados["senha"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"identificador": dados["email"], "senha": dados["senha"]}
        ).status_code
        == 401
    )
    criacao, edicao = eventos(session, id_)
    assert criacao.acao == "conta.criar" and edicao.acao == "conta.editar"
    assert edicao.antes == editar(dados)
    assert edicao.depois == {
        "nome": "Novo Nome",
        "email": "novo@exemplo.test",
        "telefone": "11987654322",
    }
    assert edicao.usuario_id == id_ and edicao.condominio_id is None
    assert str(edicao.ip) == "203.0.113.27"
    # Manter e-mail/telefone da própria conta não é conflito de unicidade.
    assert (
        client.put(ME, headers=headers, json=editar(resposta.json(), nome="Outro Nome")).status_code
        == 200
    )


def test_identidade_vem_do_token_e_nunca_do_cliente(client, session):
    headers_a, a, dados = cadastrar(client)
    headers_b, b, _ = cadastrar(client, telefone="11987654322")
    resposta = client.get(
        ME,
        headers={**headers_a, "X-Usuario-Id": b["usuario"]["id"]},
        params={"usuario_id": b["usuario"]["id"]},
    )
    assert resposta.json()["id"] == a["usuario"]["id"]
    antes_b = client.get(ME, headers=headers_b).json()
    assert (
        client.put(
            ME,
            headers=headers_a,
            params={"usuario_id": b["usuario"]["id"]},
            json=editar(dados, nome="Nome Alterado"),
        ).status_code
        == 200
    )
    assert client.get(ME, headers=headers_b).json() == antes_b
    assert (
        client.put(
            f"/api/v1/contas/{b['usuario']['id']}", headers=headers_a, json=editar(dados)
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("nome", "   "),
        ("nome", "Ana"),
        ("nome", "x" * 121),
        ("email", "invalido"),
        ("telefone", "(11)987654321"),
        ("id", str(uuid.uuid4())),
        ("usuario_id", str(uuid.uuid4())),
        ("condominio_id", str(uuid.uuid4())),
        ("tipo_cadastro", "administracao"),
        ("administrador_plataforma", True),
        ("ativo", False),
        ("sessao_versao", 99),
        ("documento", "52998224725"),
        ("senha", "OutraSenha123"),
        ("foto_arquivo_id", str(uuid.uuid4())),
    ],
)
def test_edicao_rejeita_campos_invalidos_e_protegidos(client, session, campo, valor):
    headers, sessao, dados = cadastrar(client)
    anterior = client.get(ME, headers=headers).json()
    resposta = client.put(ME, headers=headers, json=editar(dados, **{campo: valor}))
    assert resposta.status_code == 422
    assert client.get(ME, headers=headers).json() == anterior
    assert len(eventos(session, sessao["usuario"]["id"])) == 1


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_perfil_exige_access_token_valido(client, metodo):
    assert (
        getattr(client, metodo)(ME, **({"json": {}} if metodo == "put" else {})).status_code == 401
    )
    _, sessao, dados = cadastrar(client)
    headers = {"Authorization": f"Bearer {sessao['refresh_token']}"}
    resposta = getattr(client, metodo)(
        ME, headers=headers, **({"json": editar(dados)} if metodo == "put" else {})
    )
    assert resposta.status_code == 401 and resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("alteracao", ["inativar", "revogar"])
def test_perfil_respeita_revogacao_imediata(client, session, alteracao):
    headers, sessao, dados = cadastrar(client)
    usuario = session.get(Usuario, uuid.UUID(sessao["usuario"]["id"]))
    if alteracao == "inativar":
        usuario.ativo = False
    else:
        usuario.sessao_versao += 1
    session.commit()
    assert client.get(ME, headers=headers).status_code == 401
    assert client.put(ME, headers=headers, json=editar(dados)).status_code == 401


@pytest.mark.parametrize("campo", ["email", "telefone"])
@pytest.mark.parametrize("simular_corrida", [False, True])
def test_unicidade_na_edicao_e_constraint_do_banco(
    client, session, monkeypatch, campo, simular_corrida
):
    headers, sessao, dados = cadastrar(client)
    _, _, outra = cadastrar(client, telefone="11987654322")
    if simular_corrida:
        campo_em_uso = repository.campo_em_uso
        chamadas = 0

        def consulta_previa(*args, **kwargs):
            nonlocal chamadas
            chamadas += 1
            # Simula outro cadastro ocupando o dado entre a pré-checagem e o flush.
            return False if chamadas <= 2 else campo_em_uso(*args, **kwargs)

        monkeypatch.setattr(repository, "campo_em_uso", consulta_previa)
    anterior = client.get(ME, headers=headers).json()
    resposta = client.put(
        ME, headers=headers, json=editar(dados, nome="Não Persistir", **{campo: outra[campo]})
    )
    assert resposta.status_code == 409, resposta.text
    assert resposta.json()["error"]["reason"] == f"{campo}_ja_cadastrado"
    assert client.get(ME, headers=headers).json() == anterior
    assert len(eventos(session, sessao["usuario"]["id"])) == 1


@pytest.mark.parametrize("operacao", ["morador", "administracao", "editar"])
@pytest.mark.parametrize("etapa", ["auditoria", "commit"])
def test_falha_transacional_reverte_conta_e_evento(client, session, monkeypatch, operacao, etapa):
    if operacao == "editar":
        headers, sessao, dados = cadastrar(client)
        anterior = client.get(ME, headers=headers).json()
    else:
        dados = conta()
        if operacao == "administracao":
            dados["documento"] = "52998224725"
    usuarios_antes = session.scalar(select(func.count()).select_from(Usuario))
    eventos_antes = session.scalar(select(func.count()).select_from(RegistroAuditoria))
    registrar = auditoria.registrar_acao

    def falhar_auditoria(*args, **kwargs):
        registrar(*args, **kwargs)
        raise RuntimeError("Falha controlada após inserir o evento")

    def falhar_commit():
        raise RuntimeError("Falha controlada antes do commit")

    with monkeypatch.context() as patch:
        if etapa == "auditoria":
            patch.setattr(auditoria, "registrar_acao", falhar_auditoria)
        else:
            patch.setattr(session, "commit", falhar_commit)
        if operacao == "editar":
            resposta = client.put(ME, headers=headers, json=editar(dados, nome="Não Persistir"))
        else:
            resposta = client.post(f"/api/v1/contas/{operacao}", json=dados)
    assert resposta.status_code == 500
    assert session.scalar(select(func.count()).select_from(Usuario)) == usuarios_antes
    assert session.scalar(select(func.count()).select_from(RegistroAuditoria)) == eventos_antes
    if operacao == "editar":
        assert client.get(ME, headers=headers).json() == anterior
    else:
        assert session.scalar(select(Usuario.id).where(Usuario.email == dados["email"])) is None


def test_foto_existente_e_retornada_mas_novos_uploads_dependem_de_storage_global(client, session):
    headers, sessao, dados = cadastrar(client)
    usuario = session.get(Usuario, uuid.UUID(sessao["usuario"]["id"]))
    foto = Arquivo(
        condominio_id=None,
        chave_storage=f"conta/{uuid.uuid4()}",
        nome_original="foto.png",
        tipo_mime="image/png",
        tamanho_bytes=10,
        enviado_por_usuario_id=usuario.id,
    )
    session.add(foto)
    session.flush()
    usuario.foto_arquivo_id = foto.id
    session.commit()
    assert client.get(ME, headers=headers).json()["foto_arquivo_id"] == str(foto.id)


def test_contas_sem_tipo_so_consultam_e_nao_contornam_conta_compartilhada(client, session):
    predio = montar_predio(session)
    session.commit()
    for perfil in ("morador", "administracao", "funcionario", "plataforma"):
        headers = predio.cabecalho_de(perfil)
        resposta = client.get(ME, headers=headers)
        assert resposta.status_code == 200 and resposta.json()["tipo_cadastro"] is None
        assert client.put(ME, headers=headers, json=editar(conta())).status_code == 403


def test_edicao_global_nao_depende_do_condominio_selecionado(client, session):
    headers, sessao, dados = cadastrar(client, "administracao")
    usuario = session.get(Usuario, uuid.UUID(sessao["usuario"]["id"]))
    predio = montar_predio(session)
    from tests.isolamento.cenario import cabecalho, token_de, vincular

    vincular(session, usuario, predio.condominio, perfil="administracao")
    session.commit()
    headers = cabecalho(token_de(usuario, predio.condominio.id, perfil="administracao"))
    assert (
        client.put(ME, headers=headers, json=editar(dados, nome="Outra Razão Social")).status_code
        == 200
    )
    assert eventos(session, usuario.id)[-1].condominio_id is None
    assert eventos(session, usuario.id)[-1].perfil is None
