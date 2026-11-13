"""Consultas reais de encomendas com isolamento de condomínio e permissão por unidade."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import MoradorUnidade, PermissaoAba
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session
from tests.isolamento.cenario import criar_usuario

pytestmark = pytest.mark.postgres


@pytest.fixture
def adapter():
    class Adapter:
        def __init__(self):
            self.objects: dict[str, bytes] = {}

        def put(self, key, data, content_type):
            self.objects[key] = data

        def sign(self, key, seconds):
            return f"https://storage.exemplo.test/{key}?expires={seconds}"

        def remove(self, key):
            self.objects.pop(key, None)

    return Adapter()


@pytest.fixture
def client(session: Session, adapter):
    from app.modules.storage.router import get_storage_adapter

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_storage_adapter] = lambda: adapter
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def criar_funcionario(session: Session, predio, *, ativo: bool = True) -> Funcionario:
    funcionario = Funcionario(
        condominio_id=predio.condominio.id,
        nome=f"Porteiro {uuid4().hex[:8]}",
        funcao="porteiro",
        telefone=None,
        email=f"porteiro-{uuid4().hex}@exemplo.test",
        foto_arquivo_id=None,
        ativo=ativo,
        desligado_em=None if ativo else datetime.now(UTC),
    )
    session.add(funcionario)
    session.flush()
    return funcionario


def criar_encomenda(
    session: Session,
    predio,
    funcionario: Funcionario,
    *,
    descricao: str,
    unidade_id: UUID | None = None,
    status: str = "aguardando_retirada",
) -> Encomenda:
    arquivo_id = uuid4()
    session.add(
        Arquivo(
            id=arquivo_id,
            condominio_id=predio.condominio.id,
            chave_storage=f"condominio/{predio.condominio.id}/encomendas/{arquivo_id}",
            nome_original="foto.png",
            tipo_mime="image/png",
            tamanho_bytes=68,
            enviado_por_usuario_id=predio.funcionario.id,
        )
    )
    session.flush()
    encomenda = Encomenda(
        condominio_id=predio.condominio.id,
        unidade_id=unidade_id or predio.unidade_101.id,
        destinatario_morador_unidade_id=predio.morador_unidade.id,
        descricao=descricao,
        foto_nota_arquivo_id=arquivo_id,
        recebido_por_funcionario_id=funcionario.id,
    )
    if status == "retirada_confirmada":
        agora = datetime.now(UTC)
        encomenda.status = status
        encomenda.registrada_em = agora - timedelta(seconds=10)
        encomenda.entregue_em = agora
        encomenda.recebedor_morador_unidade_id = predio.morador_unidade.id
        encomenda.entregue_por_funcionario_id = funcionario.id
        encomenda.confirmada_em = agora
        encomenda.confirmado_por_usuario_id = predio.morador.id
    session.add(encomenda)
    session.flush()
    return encomenda


def permitir_aba_encomendas(session: Session, predio) -> PermissaoAba:
    permissao = PermissaoAba(
        condominio_id=predio.condominio.id,
        morador_unidade_id=predio.morador_unidade.id,
        aba="encomendas",
        com_acesso=True,
    )
    session.add(permissao)
    session.flush()
    return permissao


def test_listar_encomendas_filtra_status_busca_pagina_e_condominio(client, session):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")
    funcionario_a = criar_funcionario(session, a)
    funcionario_b = criar_funcionario(session, b)
    pacote_a1 = criar_encomenda(
        session, a, funcionario_a, descricao="Caixa de livro 1", status="aguardando_retirada"
    )
    pacote_a2 = criar_encomenda(
        session, a, funcionario_a, descricao="Caixa de livro 2", status="aguardando_retirada"
    )
    criar_encomenda(
        session,
        a,
        funcionario_a,
        descricao="Caixa de livro confirmada",
        status="retirada_confirmada",
    )
    criar_encomenda(session, b, funcionario_b, descricao="Caixa de livro de outro condomínio")

    pagina_1 = client.get(
        "/api/v1/encomendas",
        headers=a.cabecalho_de("funcionario"),
        params={
            "status": "aguardando_retirada",
            "busca": "Caixa de livro",
            "page": 1,
            "page_size": 1,
        },
    )
    pagina_2 = client.get(
        "/api/v1/encomendas",
        headers=a.cabecalho_de("funcionario"),
        params={
            "status": "aguardando_retirada",
            "busca": "Caixa de livro",
            "page": 2,
            "page_size": 1,
        },
    )
    confirmadas = client.get(
        "/api/v1/encomendas",
        headers=a.cabecalho_de("funcionario"),
        params={"status": "retirada_confirmada", "page": 1, "page_size": 20},
    )

    assert pagina_1.status_code == pagina_2.status_code == confirmadas.status_code == 200
    assert pagina_1.json()["total"] == 2
    assert pagina_1.json()["page_size"] == 1
    assert len(pagina_1.json()["items"]) == len(pagina_2.json()["items"]) == 1
    ids = {pagina_1.json()["items"][0]["id"], pagina_2.json()["items"][0]["id"]}
    assert ids == {str(pacote_a1.id), str(pacote_a2.id)}
    assert confirmadas.json()["total"] == 1
    assert confirmadas.json()["items"][0]["status"] == "retirada_confirmada"
    assert str(b.condominio.id) not in pagina_1.text


def test_morador_lista_somente_unidades_ativas_com_aba(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    da_unidade = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Acesso autorizado",
        unidade_id=predio.unidade_101.id,
    )
    de_outra_unidade = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Sem vínculo ativo",
        unidade_id=predio.unidade_102.id,
    )

    resposta = client.get("/api/v1/encomendas", headers=predio.cabecalho_de("morador"))
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["total"] == 1
    assert [item["id"] for item in resposta.json()["items"]] == [str(da_unidade.id)]
    assert str(de_outra_unidade.id) not in resposta.text


def test_detalhe_de_outro_condominio_retorna_404(client, session):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")
    funcionario_a = criar_funcionario(session, a)
    funcionario_b = criar_funcionario(session, b)
    encomenda_a = criar_encomenda(session, a, funcionario_a, descricao="Da Aurora")
    encomenda_b = criar_encomenda(session, b, funcionario_b, descricao="Privada")

    propria = client.get(
        f"/api/v1/encomendas/{encomenda_a.id}", headers=a.cabecalho_de("funcionario")
    )
    cruzada = client.get(
        f"/api/v1/encomendas/{encomenda_b.id}", headers=a.cabecalho_de("funcionario")
    )
    ausente = client.get(f"/api/v1/encomendas/{uuid4()}", headers=a.cabecalho_de("funcionario"))
    assert propria.status_code == 200, propria.text
    assert cruzada.status_code == ausente.status_code == 404
    assert cruzada.json() == ausente.json()


def test_detalhe_de_morador_sem_aba_retorna_403(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Aba desativada")

    resposta = client.get(
        f"/api/v1/encomendas/{encomenda.id}", headers=predio.cabecalho_de("morador")
    )
    assert resposta.status_code == 403


def test_download_foto_respeita_vinculo_e_aba(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permissao = permitir_aba_encomendas(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Foto restrita")
    rota = f"/api/v1/arquivos/{encomenda.foto_nota_arquivo_id}/download"

    autorizado = client.get(rota, headers=predio.cabecalho_de("morador"))
    assert autorizado.status_code == 200, autorizado.text
    assert autorizado.json()["url"].startswith("https://storage.exemplo.test/")

    permissao.com_acesso = False
    negado_por_aba = client.get(rota, headers=predio.cabecalho_de("morador"))
    assert negado_por_aba.status_code == 404

    permissao.com_acesso = True
    predio.morador_unidade.status = "desvinculado"
    predio.morador_unidade.desvinculado_em = datetime.now(UTC)
    negado_por_vinculo = client.get(rota, headers=predio.cabecalho_de("morador"))
    assert negado_por_vinculo.status_code == 404


def test_opcoes_da_portaria_omitem_unidade_e_moradores_inativos(client, session):
    predio = montar_predio(session)
    predio.unidade_102.ativo = False
    usuario_desvinculado = criar_usuario(session)
    session.add(
        MoradorUnidade(
            condominio_id=predio.condominio.id,
            unidade_id=predio.unidade_101.id,
            usuario_id=usuario_desvinculado.id,
            status="desvinculado",
            origem="cadastro",
            desvinculado_em=datetime.now(UTC),
        )
    )
    criar_funcionario(session, predio)

    unidades = client.get("/api/v1/portaria/unidades", headers=predio.cabecalho_de("funcionario"))
    moradores = client.get(
        f"/api/v1/portaria/unidades/{predio.unidade_101.id}/moradores",
        headers=predio.cabecalho_de("funcionario"),
    )
    proibido_ao_morador = client.get(
        "/api/v1/portaria/unidades", headers=predio.cabecalho_de("morador")
    )

    assert unidades.status_code == moradores.status_code == 200
    assert [item["id"] for item in unidades.json()["items"]] == [str(predio.unidade_101.id)]
    assert [item["id"] for item in moradores.json()["items"]] == [str(predio.morador_unidade.id)]
    assert proibido_ao_morador.status_code == 403
