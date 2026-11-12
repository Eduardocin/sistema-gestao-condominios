"""Storage HTTP com autenticação real e metadados em PostgreSQL migrado."""

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db.session import get_session
from app.main import create_app
from app.modules.storage.models import Arquivo
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session

pytestmark = pytest.mark.postgres


@pytest.fixture
def adapter():
    class Adapter:
        def __init__(self):
            self.objects = {}

        def put(self, key, data, content_type):
            self.objects[key] = data

        def sign(self, key, seconds):
            return f"https://storage.exemplo.test/{key}?expires={seconds}"

        def remove(self, key):
            self.objects.pop(key, None)

    return Adapter()


@pytest.fixture
def client(session, adapter):
    from app.modules.storage.router import get_storage_adapter

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage_adapter] = lambda: adapter
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def imagem():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


def enviar(client, p, perfil="funcionario", modulo="encomendas", **params):
    return client.post(
        f"/api/v1/arquivos/{modulo}",
        params={"nome": "foto.png", **params},
        content=imagem(),
        headers={**p.cabecalho_de(perfil), "Content-Type": "image/png"},
    )


def test_upload_persiste_apenas_metadados_e_download_assinado(client, session, adapter):
    p = montar_predio(session)
    response = enviar(client, p)
    assert response.status_code == 201, response.text
    data = response.json()
    arquivo = session.get(Arquivo, uuid.UUID(data["id"]))
    assert arquivo.condominio_id == p.condominio.id
    assert arquivo.enviado_por_usuario_id == p.funcionario.id
    assert arquivo.tamanho_bytes == len(imagem())
    assert arquivo.chave_storage in adapter.objects
    assert "chave_storage" not in data
    assert "condominio_id" not in data
    download = client.get(data["download_url"], headers=p.cabecalho_de("funcionario"))
    assert download.status_code == 200, download.text
    assert download.json()["expires_in"] == 60


def test_download_cruzado_e_desconhecido_sao_404_iguais(client, session):
    a, b = montar_predio(session), montar_predio(session, "Outro condomínio")
    data = enviar(client, a).json()
    cruzado = client.get(data["download_url"], headers=b.cabecalho_de("funcionario"))
    ausente = client.get(
        f"/api/v1/arquivos/{uuid.uuid4()}/download", headers=b.cabecalho_de("funcionario")
    )
    assert cruzado.status_code == ausente.status_code == 404
    assert cruzado.json() == ausente.json()


def test_mesmo_condominio_nao_libera_upload_nao_vinculado_de_outro_usuario(client, session):
    p = montar_predio(session)
    data = enviar(client, p).json()
    response = client.get(data["download_url"], headers=p.cabecalho_de("morador"))
    assert response.status_code == 404


@pytest.mark.parametrize("perfil", ["morador", "administracao", "plataforma"])
def test_foto_encomenda_so_portaria_pode_enviar(client, session, perfil):
    assert enviar(client, montar_predio(session), perfil=perfil).status_code == 403


def test_token_obrigatorio_e_tipo_invalido_nao_persistem(client, session, adapter):
    p = montar_predio(session)
    assert client.post("/api/v1/arquivos/encomendas?nome=foto.png").status_code == 401
    response = client.post(
        "/api/v1/arquivos/encomendas?nome=foto.png",
        content=b"nao e imagem",
        headers={**p.cabecalho_de("funcionario"), "Content-Type": "image/png"},
    )
    assert response.status_code == 422
    assert not adapter.objects
    assert session.scalar(select(Arquivo).where(Arquivo.condominio_id == p.condominio.id)) is None


def test_condominio_cliente_rejeitado(client, session):
    p = montar_predio(session)
    response = enviar(client, p, condominio_id=str(uuid.uuid4()))
    assert response.status_code == 422


def test_morador_precisa_unidade_e_aba_para_anexar_ocorrencia(client, session):
    from app.modules.unidades.models import PermissaoAba

    p = montar_predio(session)
    assert enviar(client, p, "morador", "ocorrencias").status_code == 422
    args = {"unidade_id": str(p.unidade_101.id)}
    assert enviar(client, p, "morador", "ocorrencias", **args).status_code == 403
    session.add(
        PermissaoAba(
            condominio_id=p.condominio.id,
            morador_unidade_id=p.morador_unidade.id,
            aba="ocorrencias",
            com_acesso=True,
        )
    )
    session.flush()
    assert enviar(client, p, "morador", "ocorrencias", **args).status_code == 201
    args["unidade_id"] = str(p.unidade_102.id)
    assert enviar(client, p, "morador", "ocorrencias", **args).status_code == 404


def test_falha_persistencia_compensa_objeto(client, session, adapter, monkeypatch):
    p = montar_predio(session)

    def falhar():
        raise RuntimeError("Falha fictícia de commit")

    monkeypatch.setattr(session, "commit", falhar)
    assert enviar(client, p).status_code == 500
    assert not adapter.objects


def test_limpeza_nao_depende_banco_disponivel_apos_falha(client, session, adapter, monkeypatch):
    from app.modules.unidades.models import PermissaoAba

    p = montar_predio(session)
    session.add(
        PermissaoAba(
            condominio_id=p.condominio.id,
            morador_unidade_id=p.morador_unidade.id,
            aba="ocorrencias",
            com_acesso=True,
        )
    )
    session.flush()

    def indisponivel(*args, **kwargs):
        raise RuntimeError("Banco indisponível fictício")

    def commit_falho():
        monkeypatch.setattr(session, "scalar", indisponivel)
        monkeypatch.setattr(session, "rollback", indisponivel)
        indisponivel()

    monkeypatch.setattr(session, "commit", commit_falho)
    response = enviar(client, p, "morador", "ocorrencias", unidade_id=str(p.unidade_101.id))
    assert response.status_code == 500
    assert not adapter.objects


def test_arquivo_vinculado_respeita_unidade_e_revogacao_mesmo_para_autor(client, session):
    from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo
    from app.modules.unidades.models import PermissaoAba

    p = montar_predio(session)
    aba = PermissaoAba(
        condominio_id=p.condominio.id,
        morador_unidade_id=p.morador_unidade.id,
        aba="ocorrencias",
        com_acesso=True,
    )
    session.add(aba)
    session.flush()
    data = enviar(client, p, "morador", "ocorrencias", unidade_id=str(p.unidade_101.id)).json()
    ocorrencia = Ocorrencia(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        aberta_por_usuario_id=p.morador.id,
        titulo="Exemplo",
        detalhe="Dado fictício",
    )
    session.add(ocorrencia)
    session.flush()
    session.add(
        OcorrenciaAnexo(
            ocorrencia_id=ocorrencia.id,
            condominio_id=p.condominio.id,
            arquivo_id=uuid.UUID(data["id"]),
        )
    )
    session.flush()
    headers = p.cabecalho_de("morador")
    assert client.get(data["download_url"], headers=headers).status_code == 200
    aba.com_acesso = False
    session.flush()
    assert client.get(data["download_url"], headers=headers).status_code == 404
    assert (
        client.get(data["download_url"], headers=p.cabecalho_de("administracao")).status_code == 200
    )
    assert (
        client.get(data["download_url"], headers=p.cabecalho_de("funcionario")).status_code == 404
    )
    aba.com_acesso = True
    ocorrencia.unidade_id = p.unidade_102.id
    session.flush()
    assert client.get(data["download_url"], headers=headers).status_code == 404


def test_limite_real_antes_de_gravar(client, session, adapter):
    from app.modules.storage.validation import IMAGE_LIMIT

    p = montar_predio(session)
    response = client.post(
        "/api/v1/arquivos/encomendas?nome=foto.png",
        content=b"x" * (IMAGE_LIMIT + 1),
        headers={**p.cabecalho_de("funcionario"), "Content-Type": "image/png"},
    )
    assert response.status_code == 422
    assert not adapter.objects


@pytest.mark.storage
def test_api_com_token_banco_e_minio_reais(session):
    import os
    from urllib.error import HTTPError
    from urllib.request import urlopen

    from app.core.config import Settings
    from app.modules.storage.router import get_storage_adapter
    from app.modules.storage.s3 import S3Adapter

    endpoint = os.getenv("TEST_STORAGE_ENDPOINT")
    if not endpoint:
        pytest.skip("Defina TEST_STORAGE_ENDPOINT para integração MinIO")
    settings = Settings(
        _env_file=None,
        storage_endpoint=endpoint,
        storage_public_endpoint=endpoint,
        storage_access_key=os.environ["TEST_STORAGE_ACCESS_KEY"],
        storage_secret_key=os.environ["TEST_STORAGE_SECRET_KEY"],
        storage_bucket=f"teste-{uuid.uuid4().hex}",
    )
    adapter = S3Adapter(settings)
    adapter.ensure_private_bucket()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage_adapter] = lambda: adapter
    p, b = montar_predio(session), montar_predio(session, "Outro prédio")
    try:
        with TestClient(app) as client:
            data = enviar(client, p).json()
            response = client.get(data["download_url"], headers=p.cabecalho_de("funcionario"))
            url = response.json()["url"]
            with urlopen(url, timeout=10) as download:
                assert download.read() == imagem()
            with pytest.raises(HTTPError) as erro:
                urlopen(url.split("?")[0], timeout=10)
            assert erro.value.code == 403
            assert (
                client.get(data["download_url"], headers=b.cabecalho_de("funcionario")).status_code
                == 404
            )
    finally:
        for obj in adapter.client.list_objects(settings.storage_bucket, recursive=True):
            adapter.client.remove_object(settings.storage_bucket, obj.object_name)
        adapter.client.remove_bucket(settings.storage_bucket)
