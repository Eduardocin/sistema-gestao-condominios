"""TASK-54: a "revisão rápida" das respostas da API, automatizada.

1. Esquema: todo campo de dado pessoal ou segredo em um schema de RESPOSTA precisa estar na
   lista `PERMITIDOS`, com o motivo. Campo novo sem decisão do grupo faz o teste falhar.
2. Banco: listagens mascaram e o Morador nunca recebe o documento do proprietário.
3. Cabeçalhos de segurança, travas de produção e o filtro de logs.
"""

import json
import logging
import sys
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging_seguro import (
    FiltroAcessoSemQuery,
    FiltroDadosPessoais,
    instalar_filtros_de_log,
    redigir,
)
from app.core.mascaras import mascarar_documento, mascarar_email, mascarar_telefone
from app.main import create_app
from tests.test_contas_funcionarios_api import session as sessao_postgres

# Sessão PostgreSQL com rollback no fim (pula sem TEST_DATABASE_URL).
session = sessao_postgres

SENSIVEIS = frozenset(
    {
        "senha",
        "senha_hash",
        "password",
        "token_hash",
        "sessao_versao",
        "refresh_token",
        "documento",
        "cpf",
        "cnpj",
        "telefone",
        "email",
        "emails",
        "whatsapps",
        "codigo",
    }
)

# {schema de resposta: {campo: motivo}}. É assim que o grupo justifica cada dado que sai.
PERMITIDOS: dict[str, dict[str, str]] = {
    "ContaSaida": {
        "documento": "Só o titular, em /contas/me (nucleo.md 3.3).",
        "email": "Só o titular, em /contas/me.",
        "telefone": "Só o titular, em /contas/me.",
    },
    "UsuarioOut": {"email": "Dados do próprio usuário na sessão (login e /auth/me)."},
    "LoginResponse": {"refresh_token": "Sessão do próprio usuário, no login e na troca de senha."},
    "FuncionarioSaida": {
        "email": "Administração gere o cadastro do funcionário; contato exibido na lista.",
        "telefone": "Administração; mascarado na lista, completo só no detalhe/escrita.",
    },
    "ProprietarioSaida": {
        "documento": "Só a Administração, que gere o proprietário (US-207, decisão 5 do DER).",
        "emails": "Só a Administração (US-207).",
        "telefone": "Só a Administração (US-207).",
        "whatsapps": "Só a Administração (US-207).",
    },
    "ProprietarioPublico": {
        "emails": "Contato do proprietário ao Morador (nucleo.md, pendência), sem documento.",
        "telefone": "Contato do proprietário ao Morador, sem documento.",
        "whatsapps": "Contato do proprietário ao Morador, sem documento.",
    },
    "VisitanteMorador": {
        "cpf": "DECISÃO PENDENTE: o front do Morador edita o visitante com o CPF da lista.",
    },
    "AdministracaoSaida": {
        "email": "Só o ADM, na fila de análise do condomínio: contato de quem enviou.",
    },
    "ChaveSaida": {"codigo": "Só a Administração consulta a chave (US-207); nunca o Morador."},
    # CNPJ é do condomínio (pessoa jurídica), não dado pessoal; Administração e ADM.
    "CadastroCondominioSaida": {"cnpj": "CNPJ do condomínio (pessoa jurídica)."},
    "CondominioSaida": {"cnpj": "CNPJ do condomínio (pessoa jurídica)."},
    "DetalhePlataforma": {"cnpj": "CNPJ do condomínio (pessoa jurídica), só ADM."},
    "ItemFila": {"cnpj": "CNPJ do condomínio (pessoa jurídica), só ADM."},
    "ReenvioSaida": {"cnpj": "CNPJ do condomínio (pessoa jurídica)."},
}


# --- 1. esquema ----------------------------------------------------------------------------


def _refs(objeto: Any, saida: set[str]) -> None:
    if isinstance(objeto, dict):
        if "$ref" in objeto:
            saida.add(objeto["$ref"].rsplit("/", 1)[-1])
        for valor in objeto.values():
            _refs(valor, saida)
    elif isinstance(objeto, list):
        for valor in objeto:
            _refs(valor, saida)


def _propriedades(objeto: Any, saida: set[str]) -> None:
    """Nomes de propriedade em qualquer profundidade (objetos inline também contam)."""
    if isinstance(objeto, dict):
        for nome, valor in objeto.get("properties", {}).items():
            saida.add(nome)
            _propriedades(valor, saida)
        for chave, valor in objeto.items():
            if chave != "properties":
                _propriedades(valor, saida)
    elif isinstance(objeto, list):
        for valor in objeto:
            _propriedades(valor, saida)


def schemas_de_resposta() -> dict[str, set[str]]:
    """{schema: propriedades} de tudo que pode sair numa resposta, com as referências aninhadas."""
    especificacao = create_app().openapi()
    componentes = especificacao["components"]["schemas"]
    alcancados: set[str] = set()
    for operacoes in especificacao["paths"].values():
        for operacao in operacoes.values():
            _refs(operacao.get("responses", {}), alcancados)
    fila = list(alcancados)
    while fila:
        aninhados: set[str] = set()
        _refs(componentes.get(fila.pop(), {}), aninhados)
        for nome in aninhados - alcancados:
            alcancados.add(nome)
            fila.append(nome)
    resultado = {}
    for nome in alcancados:
        propriedades: set[str] = set()
        _propriedades(componentes.get(nome, {}), propriedades)
        resultado[nome] = propriedades
    return resultado


def test_nenhum_dado_pessoal_sai_sem_justificativa():
    vazamentos = {
        f"{schema}.{campo}"
        for schema, campos in schemas_de_resposta().items()
        for campo in campos & SENSIVEIS
        if campo not in PERMITIDOS.get(schema, {})
    }
    assert vazamentos == set(), (
        "Campo sensível em resposta sem decisão do grupo. Remova, mascare ou justifique em "
        f"PERMITIDOS: {sorted(vazamentos)}"
    )


def test_lista_de_permitidos_nao_tem_entrada_velha():
    """Cada exceção aponta para um campo que ainda existe: lista enxuta, motivo sempre atual."""
    atuais = schemas_de_resposta()
    velhos = {
        f"{schema}.{campo}"
        for schema, campos in PERMITIDOS.items()
        for campo in campos
        if campo not in atuais.get(schema, set())
    }
    assert velhos == set()
    assert all(motivo.strip() for campos in PERMITIDOS.values() for motivo in campos.values())


def test_hash_e_versao_de_sessao_nunca_saem():
    for schema, campos in schemas_de_resposta().items():
        assert not campos & {"senha", "senha_hash", "password", "token_hash", "sessao_versao"}, (
            schema
        )


# --- máscaras ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("52998224725", "***.982.247-**"),
        ("529.982.247-25", "***.982.247-**"),
        ("11222333000181", "**.***.333/0001-**"),
        ("11.222.333/0001-81", "**.***.333/0001-**"),
        ("***.982.247-**", "***.982.247-**"),
        ("123", "***"),
        (None, None),
    ],
)
def test_mascarar_documento(entrada, esperado):
    assert mascarar_documento(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("11987654321", "*******4321"), ("1133334444", "******4444"), ("123", "***"), (None, None)],
)
def test_mascarar_telefone(entrada, esperado):
    assert mascarar_telefone(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [("ana@exemplo.com", "a***@exemplo.com"), ("sem-arroba", "***"), (None, None)],
)
def test_mascarar_email(entrada, esperado):
    assert mascarar_email(entrada) == esperado


# --- cabeçalhos ----------------------------------------------------------------------------


@pytest.fixture
def cliente_sem_banco():
    app = create_app()

    def falha() -> None:
        raise RuntimeError("erro com ana@exemplo.com")

    app.add_api_route("/api/v1/teste-500", falha)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


SEGURANCA = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


@pytest.mark.parametrize(
    ("metodo", "rota", "corpo", "status"),
    [
        ("GET", "/api/v1/health", None, 200),
        ("GET", "/api/v1/contas/me", None, 401),
        ("GET", "/api/v1/nao-existe", None, 404),
        ("POST", "/api/v1/auth/login", {}, 422),
        ("GET", "/api/v1/teste-500", None, 500),
    ],
)
def test_cabecalhos_de_seguranca_inclusive_em_erros(cliente_sem_banco, metodo, rota, corpo, status):
    resposta = cliente_sem_banco.request(metodo, rota, json=corpo)
    assert resposta.status_code == status
    for nome, valor in SEGURANCA.items():
        assert resposta.headers.get(nome) == valor, nome
    assert "strict-transport-security" not in resposta.headers  # só em produção
    assert "ana@exemplo.com" not in resposta.text


def test_documentacao_em_dev_sem_csp(cliente_sem_banco):
    for rota in ("/docs", "/openapi.json"):
        resposta = cliente_sem_banco.get(rota)
        assert resposta.status_code == 200
        assert "content-security-policy" not in resposta.headers
        assert resposta.headers["x-content-type-options"] == "nosniff"


def configuracao_de_producao(**alteracoes: Any) -> Settings:
    valores: dict[str, Any] = {
        "app_env": "production",
        "jwt_secret_key": "x" * 40,
        "cors_origins": ["https://condominios.exemplo.test"],
        "frontend_base_url": "https://condominios.exemplo.test",
        "postgres_password": "senha-de-producao-ficticia",
        "storage_access_key": "chave-de-producao-ficticia",
        "storage_secret_key": "segredo-de-producao-ficticio",
    }
    return Settings(_env_file=None, **(valores | alteracoes))


def test_producao_sem_documentacao_e_com_hsts(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", configuracao_de_producao)
    with TestClient(create_app()) as client:
        for rota in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(rota).status_code == 404
        resposta = client.get("/api/v1/health")
        assert resposta.status_code == 200
        assert resposta.headers["strict-transport-security"].startswith("max-age=")


@pytest.mark.parametrize(
    "origens",
    [["*"], ["http://condominios.exemplo.test"], ["https://ok.test", "http://localhost:5173"]],
)
def test_cors_aberto_ou_http_e_recusado_em_producao(origens):
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        configuracao_de_producao(cors_origins=origens)


def test_cors_http_continua_valendo_em_desenvolvimento():
    assert Settings(_env_file=None).cors_origins[0].startswith("http://")


# --- logs ----------------------------------------------------------------------------------


def registro(mensagem: str, *args: Any, nome: str = "app.teste", exc: bool = False):
    exc_info = None
    if exc:
        try:
            raise ValueError("falhou para maria@exemplo.com com CPF 529.982.247-25")
        except ValueError:
            exc_info = sys.exc_info()
    return logging.LogRecord(nome, logging.ERROR, __file__, 1, mensagem, args, exc_info)


@pytest.mark.parametrize(
    ("mensagem", "segredo"),
    [
        ("cpf=%s", "52998224725"),
        ("cpf %s", "529.982.247-25"),
        ("cnpj %s", "11222333000181"),
        ("cnpj %s", "11.222.333/0001-81"),
        ("contato %s", "ana.silva+teste@exemplo.com.br"),
        ("jwt %s", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.assinatura"),
        ("cabecalho %s", "Bearer abc.def-ghi"),
        ("senha=%s", "MinhaSenha123"),
        ('{"password": "%s"}', "MinhaSenha123"),
        ("STORAGE_SECRET_KEY=%s", "valor-secreto"),
        ("Authorization: %s", "Basic dXNlcjpwYXNz"),
        ("cookie=%s", "sessao-abc"),
    ],
)
def test_filtro_redige_a_mensagem_formatada(mensagem, segredo):
    item = registro(mensagem, segredo)
    assert FiltroDadosPessoais().filter(item) is True  # redige, nunca descarta
    assert segredo not in logging.Formatter().format(item)


def test_filtro_redige_senha_sem_aspas_com_espacos():
    texto = redigir("login falhou: senha=Senha Secreta123, host=db.exemplo.test")

    assert "Senha" not in texto
    assert "Secreta123" not in texto
    assert "host=db.exemplo.test" in texto


def test_filtro_redige_o_traceback():
    item = registro("Falha não tratada em %s %s", "GET", "/api/v1/contas/me", exc=True)
    FiltroDadosPessoais().filter(item)
    texto = logging.Formatter().format(item)
    assert "Traceback" in texto and "ValueError" in texto
    assert "maria@exemplo.com" not in texto and "529.982.247-25" not in texto
    assert "/api/v1/contas/me" in texto  # o que não é dado pessoal continua útil


def test_filtro_nao_estraga_uuid_nem_ids():
    id_ = str(uuid.UUID("12345678-1234-1234-1234-123456789012"))
    assert redigir(f"arquivo_id={id_} status=500") == f"arquivo_id={id_} status=500"


def test_log_de_acesso_sem_query_string_e_redigido():
    from uvicorn.logging import AccessFormatter

    item = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1:5000",
            "GET",
            "/api/v1/visitantes?busca=ana@exemplo.com&cpf=52998224725",
            "1.1",
            200,
        ),
        None,
    )
    for filtro in (FiltroAcessoSemQuery(), FiltroDadosPessoais()):
        filtro.filter(item)
    texto = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s').format(item)
    assert "GET /api/v1/visitantes HTTP/1.1" in texto and "200" in texto
    assert "ana@exemplo.com" not in texto and "52998224725" not in texto


def test_filtros_instalados_na_raiz_e_no_uvicorn():
    acesso = logging.getLogger("uvicorn.access")
    handler = logging.StreamHandler()
    acesso.addHandler(handler)
    try:
        instalar_filtros_de_log()
        instalar_filtros_de_log()  # idempotente
        for alvo in (logging.getLogger(), acesso, handler, logging.getLogger("sqlalchemy")):
            tipos = [type(f) for f in alvo.filters]
            assert tipos.count(FiltroDadosPessoais) == 1, alvo
        assert [type(f) for f in acesso.filters].count(FiltroAcessoSemQuery) == 1
    finally:
        acesso.removeHandler(handler)


# --- banco: listagens mascaradas e proprietário para o Morador ------------------------------


@pytest.mark.postgres
def test_lista_de_funcionarios_mascara_telefone_e_detalhe_nao(session):
    from app.db.session import get_session
    from tests.autorizacao.cenario import montar_predio
    from tests.test_contas_funcionarios_api import funcionario, responsavel

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        predio = montar_predio(session)
        cabecalho = predio.cabecalho_de("administracao")
        criado = client.post(
            "/api/v1/funcionarios",
            headers=cabecalho,
            json=funcionario(responsavel(client, predio), telefone="11987654321"),
        )
        assert criado.status_code == 201, criado.text
        lista = client.get("/api/v1/funcionarios", headers=cabecalho)
        detalhe = client.get(f"/api/v1/funcionarios/{criado.json()['id']}", headers=cabecalho)

    assert lista.json()["items"][0]["telefone"] == "*******4321"
    assert "11987654321" not in lista.text
    assert detalhe.json()["telefone"] == "11987654321"


@pytest.mark.postgres
def test_morador_nunca_recebe_documento_do_proprietario(session):
    from app.db.session import get_session
    from app.modules.unidades.models import PermissaoAba, ProprietarioUnidade
    from tests.autorizacao.cenario import montar_predio

    predio = montar_predio(session)
    session.add_all(
        [
            ProprietarioUnidade(
                condominio_id=predio.condominio.id,
                unidade_id=predio.unidade_101.id,
                nome="Dono Fictício",
                documento="52998224725",
                emails=["dono@exemplo.test"],
                telefone="11912345678",
            ),
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=predio.morador_unidade.id,
                aba="unidades",
                com_acesso=True,
            ),
        ]
    )
    session.flush()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        respostas = [
            client.get("/api/v1/minhas-unidades", headers=predio.cabecalho_de("morador")),
            client.get(
                f"/api/v1/minhas-unidades/{predio.unidade_101.id}",
                headers=predio.cabecalho_de("morador"),
            ),
        ]
        da_administracao = client.get(
            f"/api/v1/unidades/{predio.unidade_101.id}",
            headers=predio.cabecalho_de("administracao"),
        )

    for resposta in respostas:
        assert resposta.status_code == 200, resposta.text
        texto = json.dumps(resposta.json())
        assert "documento" not in texto and "52998224725" not in texto
        assert "982.247" not in texto  # nem mascarado: o Morador não recebe o campo
    proprietario = respostas[1].json()["proprietario"]
    assert proprietario["nome"] == "Dono Fictício" and proprietario["telefone"] == "11912345678"
    # A Administração, que gere o proprietário, recebe o documento completo.
    assert da_administracao.json()["proprietario"]["documento"] == "52998224725"
