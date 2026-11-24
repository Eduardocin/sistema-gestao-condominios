"""Consultas reais de encomendas com isolamento de condomínio e permissão por unidade."""

import io
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.notificacoes.models import EnvioEmail
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Andar, Bloco, MoradorUnidade, PermissaoAba
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de, vincular

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
    recebedor_morador_unidade_id: UUID | None = None,
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
    if status in {"entregue_aguardando_confirmacao", "retirada_confirmada"}:
        agora = datetime.now(UTC)
        encomenda.status = status
        encomenda.registrada_em = agora - timedelta(seconds=10)
        encomenda.entregue_em = agora
        encomenda.recebedor_morador_unidade_id = (
            recebedor_morador_unidade_id or predio.morador_unidade.id
        )
        encomenda.entregue_por_funcionario_id = funcionario.id
    if status == "retirada_confirmada":
        agora = datetime.now(UTC)
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


def foto_png() -> bytes:
    imagem = Image.new("RGB", (2, 2), color="white")
    conteudo = io.BytesIO()
    imagem.save(conteudo, format="PNG")
    return conteudo.getvalue()


def contar(session: Session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo)) or 0


def receber_encomenda(
    client,
    predio,
    funcionario: Funcionario,
    *,
    unidade_id=None,
    morador_id=None,
    campos_extras: dict[str, str] | None = None,
):
    campos = {
        "unidade_id": str(unidade_id or predio.unidade_101.id),
        "destinatario_morador_unidade_id": str(morador_id or predio.morador_unidade.id),
        "descricao": "Caixa de livros",
        "recebido_por_funcionario_id": str(funcionario.id),
    }
    if campos_extras:
        campos.update(campos_extras)
    return client.post(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("funcionario"),
        data=campos,
        files={"foto": ("nota.png", foto_png(), "image/png")},
    )


def entregar_encomenda(
    client,
    predio,
    encomenda: Encomenda,
    funcionario: Funcionario,
    *,
    recebedor_id: UUID | None = None,
):
    return client.post(
        f"/api/v1/encomendas/{encomenda.id}/entrega",
        headers=predio.cabecalho_de("funcionario"),
        json={
            "recebedor_morador_unidade_id": str(recebedor_id or predio.morador_unidade.id),
            "entregue_por_funcionario_id": str(funcionario.id),
        },
    )


def confirmar_encomenda(client, predio, encomenda: Encomenda, *, usuario=None):
    usuario = usuario or predio.morador
    token = token_de(usuario, predio.condominio.id, perfil="morador")
    return client.post(
        f"/api/v1/encomendas/{encomenda.id}/confirmacao",
        headers=cabecalho(token),
        json={},
    )


@pytest.mark.parametrize(
    ("informada", "esperada"),
    [
        (None, None),
        ("   ", None),
        ("  Entrega Expressa  ", "Entrega Expressa"),
        ("A" * 120, "A" * 120),
    ],
)
def test_recebimento_persiste_transportadora_opcional(client, session, informada, esperada):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    campos = {"transportadora": informada} if informada is not None else None
    resposta = receber_encomenda(client, predio, funcionario, campos_extras=campos)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["transportadora"] == esperada
    dados = client.get(resposta.headers["Location"], headers=predio.cabecalho_de("funcionario"))
    assert dados.status_code == 200, dados.text
    assert dados.json()["transportadora"] == esperada


def test_recebimento_rejeita_transportadora_acima_do_limite(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    resposta = receber_encomenda(
        client, predio, funcionario, campos_extras={"transportadora": "A" * 121}
    )
    assert resposta.status_code == 422, resposta.text
    assert contar(session, Encomenda) == 0
    assert contar(session, Arquivo) == 0


def test_portaria_registra_foto_e_morador_confirma_apos_entrega(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    cadastro = receber_encomenda(
        client, predio, funcionario, campos_extras={"transportadora": "Entrega Expressa"}
    )
    assert cadastro.status_code == 201, cadastro.text
    encomenda = cadastro.json()
    assert encomenda["foto_arquivo_id"]

    lista = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("morador"),
        params={"unidade_id": str(predio.unidade_101.id), "status": "aguardando_retirada"},
    )
    assert lista.status_code == 200, lista.text
    assert [(item["id"], item["transportadora"]) for item in lista.json()["items"]] == [
        (encomenda["id"], "Entrega Expressa"),
    ]

    registro = session.get(Encomenda, UUID(encomenda["id"]))
    assert registro is not None
    entrega = entregar_encomenda(client, predio, registro, funcionario)
    assert entrega.status_code == 200, entrega.text
    assert entrega.json()["status"] == "entregue_aguardando_confirmacao"

    confirmacao = confirmar_encomenda(client, predio, registro)
    assert confirmacao.status_code == 200, confirmacao.text
    assert confirmacao.json()["status"] == "retirada_confirmada"


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


def test_opcoes_diferenciam_unidades_de_blocos_distintos(client, session):
    predio = montar_predio(session)
    condominio_id = predio.condominio.id
    for unidade, nome in [(predio.unidade_101, "Bloco A"), (predio.unidade_102, "Bloco B")]:
        bloco = Bloco(condominio_id=condominio_id, nome=nome)
        session.add(bloco)
        session.flush()
        andar = Andar(condominio_id=condominio_id, bloco_id=bloco.id, nome="1º andar", ordem=1)
        session.add(andar)
        session.flush()
        unidade.andar_id = andar.id
        unidade.identificacao = "101"

    resposta = client.get(
        "/api/v1/portaria/unidades",
        params={"busca": "101"},
        headers=predio.cabecalho_de("funcionario"),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["total"] == 2
    assert resposta.json()["items"] == [
        {
            "id": str(predio.unidade_101.id),
            "identificacao": "101",
            "bloco": "Bloco A",
            "andar": "1º andar",
        },
        {
            "id": str(predio.unidade_102.id),
            "identificacao": "101",
            "bloco": "Bloco B",
            "andar": "1º andar",
        },
    ]


def test_entrega_exige_recebedor_com_aba_encomendas_ativa(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    morador_com_acesso = criar_usuario(session)
    vincular(session, morador_com_acesso, predio.condominio)
    vinculo_com_acesso = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=predio.unidade_101.id,
        usuario_id=morador_com_acesso.id,
        status="ativo",
        origem="cadastro",
    )
    session.add(vinculo_com_acesso)
    session.flush()
    session.add(
        PermissaoAba(
            condominio_id=predio.condominio.id,
            morador_unidade_id=vinculo_com_acesso.id,
            aba="encomendas",
            com_acesso=True,
        )
    )
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Entrega com permissão")

    opcoes = client.get(
        f"/api/v1/portaria/unidades/{predio.unidade_101.id}/moradores",
        params={"somente_confirmaveis": "true"},
        headers=predio.cabecalho_de("funcionario"),
    )
    entrega_sem_aba = entregar_encomenda(client, predio, encomenda, funcionario)
    entrega_com_aba = entregar_encomenda(
        client,
        predio,
        encomenda,
        funcionario,
        recebedor_id=vinculo_com_acesso.id,
    )

    assert opcoes.status_code == 200
    assert [item["id"] for item in opcoes.json()["items"]] == [str(vinculo_com_acesso.id)]
    assert entrega_sem_aba.status_code == 404
    assert entrega_com_aba.status_code == 200, entrega_com_aba.text


def test_recebimento_multipart_grava_encomenda_foto_auditoria_e_outbox(client, session, adapter):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    totais_antes = {
        modelo: contar(session, modelo)
        for modelo in (Encomenda, Arquivo, RegistroAuditoria, EnvioEmail)
    }
    conteudo_foto = foto_png()

    resposta = receber_encomenda(client, predio, funcionario)

    assert resposta.status_code == 201, resposta.text
    pacote_id = UUID(resposta.json()["id"])
    assert resposta.headers["location"] == f"/api/v1/encomendas/{pacote_id}"
    pacote = session.get(Encomenda, pacote_id)
    assert pacote is not None
    arquivo = session.get(Arquivo, pacote.foto_nota_arquivo_id)
    assert arquivo is not None
    assert arquivo.condominio_id == predio.condominio.id
    assert arquivo.nome_original == "nota.png"
    assert arquivo.tipo_mime == "image/png"
    assert adapter.objects == {arquivo.chave_storage: conteudo_foto}
    assert pacote.status == "aguardando_retirada"
    assert pacote.registrada_em is not None
    assert contar(session, Encomenda) == totais_antes[Encomenda] + 1
    assert contar(session, Arquivo) == totais_antes[Arquivo] + 1

    auditoria = session.scalar(
        select(RegistroAuditoria).where(
            RegistroAuditoria.acao == "encomenda.receber",
            RegistroAuditoria.recurso_id == pacote_id,
        )
    )
    assert auditoria is not None
    assert auditoria.condominio_id == predio.condominio.id
    assert auditoria.usuario_id == predio.funcionario.id
    assert auditoria.responsavel_nome == funcionario.nome
    assert auditoria.perfil == "funcionario"
    assert contar(session, RegistroAuditoria) == totais_antes[RegistroAuditoria] + 1

    notificacao = session.scalar(
        select(EnvioEmail).where(
            EnvioEmail.evento == "encomenda_registrada",
            EnvioEmail.recurso_id == pacote_id,
        )
    )
    assert notificacao is not None
    assert notificacao.condominio_id == predio.condominio.id
    assert notificacao.destinatario == predio.morador.email
    assert notificacao.status == "pendente"
    assert notificacao.enviado_em is None
    assert contar(session, EnvioEmail) == totais_antes[EnvioEmail] + 1


def test_recebimento_rejeita_referencias_de_outro_condominio(client, session, adapter):
    predio_a = montar_predio(session, "Residencial Aurora")
    predio_b = montar_predio(session, "Residencial Boreal")
    funcionario_b = criar_funcionario(session, predio_b)
    totais_antes = tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo))

    resposta = receber_encomenda(
        client,
        predio_a,
        funcionario_b,
        unidade_id=predio_b.unidade_101.id,
        morador_id=predio_b.morador_unidade.id,
    )

    assert resposta.status_code == 404, resposta.text
    assert tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo)) == totais_antes
    assert adapter.objects == {}


def test_recebimento_rejeita_condominio_id_enviado_pelo_cliente(client, session, adapter):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    totais_antes = tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo))

    resposta = receber_encomenda(
        client,
        predio,
        funcionario,
        campos_extras={"condominio_id": str(predio.condominio.id)},
    )

    assert resposta.status_code == 422, resposta.text
    assert tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo)) == totais_antes
    assert adapter.objects == {}


def test_recebimento_rejeita_funcionario_inativo(client, session, adapter):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio, ativo=False)
    totais_antes = tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo))

    resposta = receber_encomenda(client, predio, funcionario)

    assert resposta.status_code == 404, resposta.text
    assert tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo)) == totais_antes
    assert adapter.objects == {}


def test_recebimento_rejeita_destinatario_sem_vinculo_ativo_na_unidade(client, session, adapter):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    outro_morador = Usuario(
        nome="Morador da unidade vizinha",
        email=f"vizinho-{uuid4().hex}@exemplo.test",
        tipo_cadastro="morador",
        ativo=True,
    )
    session.add(outro_morador)
    session.flush()
    vinculo_outra_unidade = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=predio.unidade_102.id,
        usuario_id=outro_morador.id,
        status="ativo",
        origem="cadastro",
    )
    session.add(vinculo_outra_unidade)
    session.flush()
    totais_antes = tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo))

    resposta = receber_encomenda(
        client,
        predio,
        funcionario,
        unidade_id=predio.unidade_101.id,
        morador_id=vinculo_outra_unidade.id,
    )

    assert resposta.status_code == 404, resposta.text
    assert tuple(contar(session, modelo) for modelo in (Encomenda, Arquivo)) == totais_antes
    assert adapter.objects == {}


def test_falha_no_storage_nao_grava_encomenda(client, session, adapter):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    totais_antes = tuple(
        contar(session, modelo) for modelo in (Encomenda, Arquivo, RegistroAuditoria, EnvioEmail)
    )

    def falhar_upload(key, data, content_type):
        raise OSError("falha simulada do storage")

    adapter.put = falhar_upload
    resposta = receber_encomenda(client, predio, funcionario)

    assert resposta.status_code == 503, resposta.text
    assert (
        tuple(
            contar(session, modelo)
            for modelo in (Encomenda, Arquivo, RegistroAuditoria, EnvioEmail)
        )
        == totais_antes
    )
    assert adapter.objects == {}


def test_falha_no_commit_compensa_objeto_recente(client, session, adapter, monkeypatch):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    totais_antes = tuple(
        contar(session, modelo) for modelo in (Encomenda, Arquivo, RegistroAuditoria, EnvioEmail)
    )

    def falhar_commit():
        raise RuntimeError("falha simulada de commit")

    monkeypatch.setattr(session, "commit", falhar_commit)
    resposta = receber_encomenda(client, predio, funcionario)

    assert resposta.status_code == 500, resposta.text
    assert (
        tuple(
            contar(session, modelo)
            for modelo in (Encomenda, Arquivo, RegistroAuditoria, EnvioEmail)
        )
        == totais_antes
    )
    assert adapter.objects == {}


def test_entrega_grava_ator_data_e_estado_pendente(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Entrega registrada")
    auditorias_antes = contar(session, RegistroAuditoria)

    resposta = entregar_encomenda(client, predio, encomenda, funcionario)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "entregue_aguardando_confirmacao"
    assert resposta.json()["entrega"]["funcionario_id"] == str(funcionario.id)
    assert resposta.json()["entrega"]["recebedor_id"] == str(predio.morador_unidade.id)
    assert resposta.json()["pode_confirmar"] is False
    session.refresh(encomenda)
    assert encomenda.status == "entregue_aguardando_confirmacao"
    assert encomenda.entregue_em is not None
    assert encomenda.entregue_em >= encomenda.registrada_em
    auditoria = session.scalar(
        select(RegistroAuditoria).where(
            RegistroAuditoria.acao == "encomenda.entregar",
            RegistroAuditoria.recurso_id == encomenda.id,
        )
    )
    assert auditoria is not None
    assert auditoria.usuario_id == predio.funcionario.id
    assert auditoria.responsavel_nome == funcionario.nome
    assert auditoria.perfil == "funcionario"
    assert contar(session, RegistroAuditoria) == auditorias_antes + 1


def test_entrega_repetida_retorna_409_sem_auditoria_duplicada(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Entrega única")
    primeira = entregar_encomenda(client, predio, encomenda, funcionario)
    auditorias_apos_primeira = contar(session, RegistroAuditoria)

    repetida = entregar_encomenda(client, predio, encomenda, funcionario)

    assert primeira.status_code == 200, primeira.text
    assert repetida.status_code == 409, repetida.text
    assert contar(session, RegistroAuditoria) == auditorias_apos_primeira
    session.refresh(encomenda)
    assert encomenda.status == "entregue_aguardando_confirmacao"


def test_morador_confirmador_deve_ser_o_recebedor_ativo(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    outro_usuario = criar_usuario(session)
    vincular(session, outro_usuario, predio.condominio, perfil="morador")
    outro_vinculo = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=predio.unidade_101.id,
        usuario_id=outro_usuario.id,
        status="ativo",
        origem="cadastro",
    )
    session.add(outro_vinculo)
    session.flush()
    session.add(
        PermissaoAba(
            condominio_id=predio.condominio.id,
            morador_unidade_id=outro_vinculo.id,
            aba="encomendas",
            com_acesso=True,
        )
    )
    session.flush()
    encomenda = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Confirmação do recebedor",
        status="entregue_aguardando_confirmacao",
    )

    recebedor = client.get(
        f"/api/v1/encomendas/{encomenda.id}", headers=predio.cabecalho_de("morador")
    )
    outro_morador = client.get(
        f"/api/v1/encomendas/{encomenda.id}",
        headers=cabecalho(token_de(outro_usuario, predio.condominio.id, perfil="morador")),
    )
    negada_a_outro_morador = confirmar_encomenda(client, predio, encomenda, usuario=outro_usuario)
    predio.morador_unidade.status = "desvinculado"
    predio.morador_unidade.desvinculado_em = datetime.now(UTC)
    negada_ao_vinculo_inativo = confirmar_encomenda(client, predio, encomenda)

    assert recebedor.status_code == outro_morador.status_code == 200
    assert recebedor.json()["pode_confirmar"] is True
    assert outro_morador.json()["pode_confirmar"] is False
    assert negada_a_outro_morador.status_code == 404
    assert negada_ao_vinculo_inativo.status_code == 404
    session.refresh(encomenda)
    assert encomenda.status == "entregue_aguardando_confirmacao"


def test_morador_sem_aba_nao_consulta_encomenda(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    encomenda = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Aba sem acesso",
        status="entregue_aguardando_confirmacao",
    )

    leitura = client.get(
        f"/api/v1/encomendas/{encomenda.id}", headers=predio.cabecalho_de("morador")
    )
    confirmacao = confirmar_encomenda(client, predio, encomenda)

    assert leitura.status_code == confirmacao.status_code == 403
    session.refresh(encomenda)
    assert encomenda.status == "entregue_aguardando_confirmacao"


def test_admin_nao_pode_entregar_ou_confirmar(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Ação de funcionário")
    headers_admin = predio.cabecalho_de("administracao")

    entrega = client.post(
        f"/api/v1/encomendas/{encomenda.id}/entrega",
        headers=headers_admin,
        json={
            "recebedor_morador_unidade_id": str(predio.morador_unidade.id),
            "entregue_por_funcionario_id": str(funcionario.id),
        },
    )
    confirmacao = client.post(
        f"/api/v1/encomendas/{encomenda.id}/confirmacao", headers=headers_admin, json={}
    )

    assert entrega.status_code == confirmacao.status_code == 403
    session.refresh(encomenda)
    assert encomenda.status == "aguardando_retirada"


def test_funcionario_nao_pode_confirmar(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    encomenda = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Confirmação do morador",
        status="entregue_aguardando_confirmacao",
    )
    resposta = client.post(
        f"/api/v1/encomendas/{encomenda.id}/confirmacao",
        headers=predio.cabecalho_de("funcionario"),
        json={},
    )

    assert resposta.status_code == 403
    # O middleware audita a negação, mas a ação de negócio não pode ser gravada.
    evento_confirmacao = session.scalar(
        select(RegistroAuditoria.id).where(
            RegistroAuditoria.recurso_id == encomenda.id,
            RegistroAuditoria.acao == "encomenda.confirmar",
        )
    )
    assert evento_confirmacao is None
    session.refresh(encomenda)
    assert encomenda.status == "entregue_aguardando_confirmacao"


def test_confirmacao_nao_pode_ser_desfeita(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    encomenda = criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Confirmação única",
        status="entregue_aguardando_confirmacao",
    )
    auditorias_antes = contar(session, RegistroAuditoria)

    primeira = confirmar_encomenda(client, predio, encomenda)
    auditorias_apos_primeira = contar(session, RegistroAuditoria)
    repetida = confirmar_encomenda(client, predio, encomenda)

    assert primeira.status_code == 200, primeira.text
    assert primeira.json()["status"] == "retirada_confirmada"
    assert primeira.json()["confirmacao"]["morador_id"] == str(predio.morador.id)
    assert primeira.json()["pode_confirmar"] is False
    assert repetida.status_code == 409
    assert auditorias_apos_primeira == auditorias_antes + 1
    assert contar(session, RegistroAuditoria) == auditorias_apos_primeira
    session.refresh(encomenda)
    assert encomenda.status == "retirada_confirmada"


def test_transicao_de_outro_condominio_retorna_404(client, session):
    predio_a = montar_predio(session, "Residencial Aurora")
    predio_b = montar_predio(session, "Residencial Boreal")
    funcionario_a = criar_funcionario(session, predio_a)
    funcionario_b = criar_funcionario(session, predio_b)
    encomenda_b = criar_encomenda(
        session,
        predio_b,
        funcionario_b,
        descricao="Privada da Boreal",
        status="entregue_aguardando_confirmacao",
    )

    entrega = entregar_encomenda(client, predio_a, encomenda_b, funcionario_a)
    confirmacao = client.post(
        f"/api/v1/encomendas/{encomenda_b.id}/confirmacao",
        headers=predio_a.cabecalho_de("morador"),
        json={},
    )

    assert entrega.status_code == confirmacao.status_code == 404
    session.refresh(encomenda_b)
    assert encomenda_b.status == "entregue_aguardando_confirmacao"


def test_morador_filtra_a_lista_por_unidade(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    da_unidade = criar_encomenda(session, predio, funcionario, descricao="Da 101")
    criar_encomenda(
        session, predio, funcionario, descricao="Da 102", unidade_id=predio.unidade_102.id
    )

    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("morador"),
        params={"unidade_id": str(predio.unidade_101.id)},
    )
    assert resposta.status_code == 200, resposta.text
    assert [item["id"] for item in resposta.json()["items"]] == [str(da_unidade.id)]
    assert resposta.json()["total"] == 1


def test_morador_filtra_por_unidade_alheia_retorna_404(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    criar_encomenda(
        session, predio, funcionario, descricao="Da 102", unidade_id=predio.unidade_102.id
    )

    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("morador"),
        params={"unidade_id": str(predio.unidade_102.id)},
    )
    assert resposta.status_code == 404
    assert "Da 102" not in resposta.text


def test_morador_sem_aba_filtra_por_unidade_e_recebe_403(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    criar_encomenda(session, predio, funcionario, descricao="Da 101")

    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("morador"),
        params={"unidade_id": str(predio.unidade_101.id)},
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


def test_morador_filtra_por_unidade_de_outro_condominio_retorna_404(client, session):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")
    permitir_aba_encomendas(session, a)

    resposta = client.get(
        "/api/v1/encomendas",
        headers=a.cabecalho_de("morador"),
        params={"unidade_id": str(b.unidade_101.id)},
    )
    assert resposta.status_code == 404


@pytest.mark.parametrize("perfil", ["funcionario", "administracao"])
def test_equipe_filtra_a_lista_por_unidade_sem_exigi_la(client, session, perfil):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    da_101 = criar_encomenda(session, predio, funcionario, descricao="Da 101")
    da_102 = criar_encomenda(
        session, predio, funcionario, descricao="Da 102", unidade_id=predio.unidade_102.id
    )
    headers = predio.cabecalho_de(perfil)

    todas = client.get("/api/v1/encomendas", headers=headers)
    so_102 = client.get(
        "/api/v1/encomendas", headers=headers, params={"unidade_id": str(predio.unidade_102.id)}
    )
    assert {i["id"] for i in todas.json()["items"]} == {str(da_101.id), str(da_102.id)}
    assert [i["id"] for i in so_102.json()["items"]] == [str(da_102.id)]


@pytest.mark.parametrize("perfil", ["funcionario", "administracao"])
def test_equipe_filtra_por_unidade_de_outro_condominio_retorna_404(client, session, perfil):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")

    resposta = client.get(
        "/api/v1/encomendas",
        headers=a.cabecalho_de(perfil),
        params={"unidade_id": str(b.unidade_101.id)},
    )
    assert resposta.status_code == 404


def test_filtro_de_unidade_combina_com_status_e_busca(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    alvo = criar_encomenda(session, predio, funcionario, descricao="Caixa azul")
    criar_encomenda(
        session, predio, funcionario, descricao="Caixa vermelha", status="retirada_confirmada"
    )
    criar_encomenda(
        session, predio, funcionario, descricao="Caixa azul", unidade_id=predio.unidade_102.id
    )

    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("funcionario"),
        params={
            "unidade_id": str(predio.unidade_101.id),
            "status": "aguardando_retirada",
            "busca": "azul",
        },
    )
    assert [i["id"] for i in resposta.json()["items"]] == [str(alvo.id)]
    assert resposta.json()["total"] == 1


# --- período na lista e relatório (US-404) ----------------------------------------------------

FUSO_SP = timezone(timedelta(hours=-3))


def registrada_em(session, encomenda, momento: datetime):
    encomenda.registrada_em = momento
    session.flush()
    return encomenda


def test_lista_filtra_por_periodo_inclusivo_no_fuso_do_condominio(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    antes = registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Antes"),
        datetime(2030, 6, 9, 23, 59, tzinfo=FUSO_SP),
    )
    no_dia_10 = registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Dia 10 à noite"),
        # 23:30 em São Paulo já é dia 11 em UTC: tem de contar como dia 10.
        datetime(2030, 6, 10, 23, 30, tzinfo=FUSO_SP),
    )
    no_dia_11 = registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Dia 11"),
        datetime(2030, 6, 11, 0, 30, tzinfo=FUSO_SP),
    )
    headers = predio.cabecalho_de("funcionario")

    def ids(**params):
        resposta = client.get("/api/v1/encomendas", headers=headers, params=params)
        assert resposta.status_code == 200, resposta.text
        return {item["id"] for item in resposta.json()["items"]}

    assert ids(data_de="2030-06-10", data_ate="2030-06-10") == {str(no_dia_10.id)}
    assert ids(data_de="2030-06-10") == {str(no_dia_10.id), str(no_dia_11.id)}
    assert ids(data_ate="2030-06-10") == {str(antes.id), str(no_dia_10.id)}
    assert ids(data_de="2030-06-12") == set()


def test_lista_com_periodo_invertido_retorna_422(client, session):
    predio = montar_predio(session)
    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("funcionario"),
        params={"data_de": "2030-06-11", "data_ate": "2030-06-10"},
    )
    assert resposta.status_code == 422


def test_morador_filtra_a_propria_lista_por_periodo(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    permitir_aba_encomendas(session, predio)
    velha = registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Velha"),
        datetime(2030, 1, 5, 12, tzinfo=FUSO_SP),
    )
    nova = registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Nova"),
        datetime(2030, 6, 5, 12, tzinfo=FUSO_SP),
    )
    resposta = client.get(
        "/api/v1/encomendas",
        headers=predio.cabecalho_de("morador"),
        params={"data_de": "2030-06-01"},
    )
    assert [i["id"] for i in resposta.json()["items"]] == [str(nova.id)]
    assert str(velha.id) not in resposta.text


@pytest.mark.parametrize(
    ("perfil", "esperado"),
    [("administracao", 200), ("morador", 403), ("funcionario", 403), ("plataforma", 403)],
)
def test_relatorio_e_so_da_administracao(client, session, perfil, esperado):
    predio = montar_predio(session)
    permitir_aba_encomendas(session, predio)
    resposta = client.get("/api/v1/encomendas/relatorio", headers=predio.cabecalho_de(perfil))
    assert resposta.status_code == esperado, resposta.text
    if esperado == 403:
        assert resposta.json()["error"]["code"] == "forbidden"


def test_relatorio_sem_token_retorna_401(client):
    assert client.get("/api/v1/encomendas/relatorio").status_code == 401


def test_relatorio_conta_por_status_e_por_unidade(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    for _ in range(2):
        criar_encomenda(session, predio, funcionario, descricao="Pendente 101")
    criar_encomenda(
        session,
        predio,
        funcionario,
        descricao="Entregue 101",
        status="entregue_aguardando_confirmacao",
    )
    criar_encomenda(
        session, predio, funcionario, descricao="Retirada 101", status="retirada_confirmada"
    )
    criar_encomenda(
        session, predio, funcionario, descricao="Pendente 102", unidade_id=predio.unidade_102.id
    )

    resposta = client.get(
        "/api/v1/encomendas/relatorio", headers=predio.cabecalho_de("administracao")
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["periodo"] == {"de": None, "ate": None}
    assert dados["totais"] == {
        "registradas": 5,
        "aguardando_retirada": 3,
        "entregue_aguardando_confirmacao": 1,
        "retirada_confirmada": 1,
    }
    # Mais encomendas primeiro.
    assert [(i["unidade"]["identificacao"], i["registradas"]) for i in dados["por_unidade"]] == [
        (predio.unidade_101.identificacao, 4),
        (predio.unidade_102.identificacao, 1),
    ]
    da_101 = dados["por_unidade"][0]
    assert da_101["unidade"]["id"] == str(predio.unidade_101.id)
    assert (
        da_101["aguardando_retirada"],
        da_101["entregue_aguardando_confirmacao"],
        da_101["retirada_confirmada"],
    ) == (2, 1, 1)


def test_relatorio_respeita_periodo_e_unidade(client, session):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Fora"),
        datetime(2030, 1, 5, 12, tzinfo=FUSO_SP),
    )
    registrada_em(
        session,
        criar_encomenda(session, predio, funcionario, descricao="Dentro 101"),
        datetime(2030, 6, 5, 12, tzinfo=FUSO_SP),
    )
    registrada_em(
        session,
        criar_encomenda(
            session, predio, funcionario, descricao="Dentro 102", unidade_id=predio.unidade_102.id
        ),
        datetime(2030, 6, 6, 12, tzinfo=FUSO_SP),
    )
    headers = predio.cabecalho_de("administracao")

    periodo = client.get(
        "/api/v1/encomendas/relatorio",
        headers=headers,
        params={"data_de": "2030-06-01", "data_ate": "2030-06-30"},
    ).json()
    assert periodo["periodo"] == {"de": "2030-06-01", "ate": "2030-06-30"}
    assert periodo["totais"]["registradas"] == 2

    so_102 = client.get(
        "/api/v1/encomendas/relatorio",
        headers=headers,
        params={"data_de": "2030-06-01", "unidade_id": str(predio.unidade_102.id)},
    ).json()
    assert so_102["totais"]["registradas"] == 1
    assert [i["unidade"]["id"] for i in so_102["por_unidade"]] == [str(predio.unidade_102.id)]


@pytest.mark.parametrize("recurso", ["/encomendas", "/encomendas/relatorio"])
def test_consultas_aceitam_ultima_data_do_calendario(client, session, recurso):
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    criar_encomenda(session, predio, funcionario, descricao="Caixa para consultar")
    resposta = client.get(
        f"/api/v1{recurso}",
        headers=predio.cabecalho_de("administracao"),
        params={"data_ate": "9999-12-31"},
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    total = dados["totais"]["registradas"] if recurso.endswith("/relatorio") else dados["total"]
    assert total == 1


@pytest.mark.parametrize("perfil", ["morador", "funcionario"])
def test_relatorio_registra_negacao_por_perfil(client, session, caplog, perfil):
    predio = montar_predio(session)
    resposta = client.get(
        "/api/v1/encomendas/relatorio",
        headers=predio.cabecalho_de(perfil),
    )
    assert resposta.status_code == 403
    assert "permissao=encomendas:relatorio" in caplog.text


def test_relatorio_vazio_devolve_zeros(client, session):
    predio = montar_predio(session)
    dados = client.get(
        "/api/v1/encomendas/relatorio", headers=predio.cabecalho_de("administracao")
    ).json()
    assert dados["totais"] == {
        "registradas": 0,
        "aguardando_retirada": 0,
        "entregue_aguardando_confirmacao": 0,
        "retirada_confirmada": 0,
    }
    assert dados["por_unidade"] == []


def test_relatorio_nunca_conta_encomenda_de_outro_condominio(client, session):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")
    criar_encomenda(session, a, criar_funcionario(session, a), descricao="De A")
    criar_encomenda(session, b, criar_funcionario(session, b), descricao="De B 1")
    criar_encomenda(session, b, criar_funcionario(session, b), descricao="De B 2")

    dados = client.get(
        "/api/v1/encomendas/relatorio", headers=a.cabecalho_de("administracao")
    ).json()
    assert dados["totais"]["registradas"] == 1
    assert str(b.unidade_101.id) not in str(dados)


def test_relatorio_com_unidade_de_outro_condominio_retorna_404(client, session):
    a = montar_predio(session, "Residencial Aurora")
    b = montar_predio(session, "Residencial Boreal")
    resposta = client.get(
        "/api/v1/encomendas/relatorio",
        headers=a.cabecalho_de("administracao"),
        params={"unidade_id": str(b.unidade_101.id)},
    )
    assert resposta.status_code == 404


def test_relatorio_com_periodo_invertido_retorna_422(client, session):
    predio = montar_predio(session)
    resposta = client.get(
        "/api/v1/encomendas/relatorio",
        headers=predio.cabecalho_de("administracao"),
        params={"data_de": "2030-06-11", "data_ate": "2030-06-10"},
    )
    assert resposta.status_code == 422


def test_relatorio_nao_engole_o_detalhe_por_id(client, session):
    """`/relatorio` não pode ser lido como UUID, e um UUID continua indo para o detalhe."""
    predio = montar_predio(session)
    funcionario = criar_funcionario(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Detalhe")
    headers = predio.cabecalho_de("funcionario")
    assert client.get(f"/api/v1/encomendas/{encomenda.id}", headers=headers).status_code == 200
