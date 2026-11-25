"""US-901 e US-902: chamados de suporte da Administração e atendimento pelo ADM."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.storage.models import Arquivo
from app.modules.suporte.models import Chamado, ChamadoAnexo, ChamadoMensagem

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]
ANTES = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.PLATAFORMA)


@pytest.fixture
def administracao(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


def arquivo(session, predio, *, modulo="suporte", dono=None, condominio=None):
    condominio = condominio or predio.condominio
    item = Arquivo(
        condominio_id=condominio.id,
        chave_storage=f"condominio/{condominio.id}/{modulo}/{uuid.uuid4().hex}.png",
        nome_original="print.png",
        tipo_mime="image/png",
        tamanho_bytes=10,
        enviado_por_usuario_id=(dono or predio.administracao).id,
    )
    session.add(item)
    session.flush()
    return item


def chamado(session, predio, *, status="aberto", titulo="Erro na estrutura", criado_em=None):
    campos = {}
    if status != "aberto":
        campos["atendido_por_usuario_id"] = predio.adm.id
    if status == "encerrado":
        campos["encerrado_em"] = datetime.now(UTC)
    item = Chamado(
        condominio_id=predio.condominio.id,
        titulo=titulo,
        descricao="Não consigo salvar.",
        status=status,
        aberto_por_usuario_id=predio.administracao.id,
        **campos,
    )
    if criado_em is not None:
        item.criado_em = criado_em
    session.add(item)
    session.flush()
    session.refresh(item)
    return item


def corpo(**campos):
    base = {"titulo": "Não consigo cadastrar a estrutura", "descricao": "Dá erro ao salvar."}
    base.update(campos)
    return base


def erro(resposta):
    return resposta.json()["error"]


def eventos(session, acao):
    return list(session.scalars(select(RegistroAuditoria).where(RegistroAuditoria.acao == acao)))


# --- perfis e 401 -----------------------------------------------------------------------------


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_rotas_da_administracao_por_perfil(client, session, predio, indice):
    existente = chamado(session, predio)
    headers = predio.cabecalho_de(PERFIS[indice])
    permitido = PERFIS[indice] == Perfil.ADMINISTRACAO
    esperado = {
        "abrir": 201,
        "listar": 200,
        "obter": 200,
        "mensagem": 201,
    }
    chamadas = {
        "abrir": lambda: client.post("/api/v1/chamados", headers=headers, json=corpo()),
        "listar": lambda: client.get("/api/v1/chamados", headers=headers),
        "obter": lambda: client.get(f"/api/v1/chamados/{existente.id}", headers=headers),
        "mensagem": lambda: client.post(
            f"/api/v1/chamados/{existente.id}/mensagens", headers=headers, json={"texto": "Oi"}
        ),
    }
    for nome, chamada in chamadas.items():
        session.commit()  # um 403 desfaz a sessão do teste; o que veio antes precisa sobreviver
        resposta = chamada()
        assert resposta.status_code == (esperado[nome] if permitido else 403), (nome, resposta.text)


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_rotas_do_adm_por_perfil(client, session, predio, indice):
    existente = chamado(session, predio)
    headers = predio.cabecalho_de(PERFIS[indice])
    permitido = PERFIS[indice] == Perfil.PLATAFORMA
    base = "/api/v1/plataforma/chamados"
    chamadas = {
        "listar": (lambda: client.get(base, headers=headers), 200),
        "obter": (lambda: client.get(f"{base}/{existente.id}", headers=headers), 200),
        "mensagem": (
            lambda: client.post(
                f"{base}/{existente.id}/mensagens", headers=headers, json={"texto": "Oi"}
            ),
            201,
        ),
        "encerrar": (
            lambda: client.post(f"{base}/{existente.id}/encerramento", headers=headers, json={}),
            200,
        ),
    }
    for nome, (chamada, ok) in chamadas.items():
        session.commit()
        resposta = chamada()
        assert resposta.status_code == (ok if permitido else 403), (nome, resposta.text)


def test_sem_token_e_401(client):
    assert client.get("/api/v1/chamados").status_code == 401
    assert client.get("/api/v1/plataforma/chamados").status_code == 401
    assert client.post("/api/v1/chamados", json={}).status_code == 401


# --- Administração ----------------------------------------------------------------------------


def test_abrir_chamado_com_anexos(client, session, predio, administracao):
    anexos = [arquivo(session, predio), arquivo(session, predio)]
    resposta = client.post(
        "/api/v1/chamados",
        headers=administracao,
        json=corpo(anexos=[str(a.id) for a in anexos]),
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["status"] == "aberto"
    assert dados["aberto_por"]["id"] == str(predio.administracao.id)
    assert dados["atendido_por"] is None
    assert dados["encerrado_em"] is None
    assert set(dados["anexos"]) == {str(a.id) for a in anexos}
    assert dados["mensagens"] == []
    assert "condominio" not in {k for k, v in dados.items() if v is not None}  # só nas rotas do ADM
    gravado = session.get(Chamado, uuid.UUID(dados["id"]))
    assert gravado.condominio_id == predio.condominio.id


@pytest.mark.parametrize(
    "campos",
    [
        {"titulo": ""},
        {"titulo": "x" * 121},
        {"descricao": ""},
        {"descricao": "x" * 4001},
        {"anexos": [str(uuid.uuid4())] * 2},
        {"anexos": [str(uuid.uuid4()) for _ in range(6)]},
        {"anexos": ["nao-e-uuid"]},
        {"status": "encerrado"},
    ],
)
def test_abertura_invalida_e_422(client, administracao, campos):
    assert (
        client.post("/api/v1/chamados", headers=administracao, json=corpo(**campos)).status_code
        == 422
    )


def test_anexo_de_outro_modulo_dono_ou_condominio_e_422(
    client, session, predio, outro_predio, administracao
):
    invalidos = [
        arquivo(session, predio, modulo="ocorrencias"),
        arquivo(session, predio, dono=predio.morador),
        arquivo(
            session,
            outro_predio,
            condominio=outro_predio.condominio,
            dono=outro_predio.administracao,
        ),
        None,
    ]
    for item in invalidos:
        anexo = str(item.id) if item else str(uuid.uuid4())
        session.commit()  # o 422 desfaz a sessão do teste; o que veio antes precisa sobreviver
        resposta = client.post(
            "/api/v1/chamados", headers=administracao, json=corpo(anexos=[anexo])
        )
        assert resposta.status_code == 422, resposta.text
    assert session.scalar(select(func.count()).select_from(Chamado)) == 0


def test_lista_so_do_proprio_condominio_do_mais_recente_ao_mais_antigo(
    client, session, predio, outro_predio, administracao
):
    velho = chamado(session, predio, titulo="Velho", criado_em=ANTES)
    novo = chamado(session, predio, titulo="Novo", criado_em=ANTES + timedelta(days=1))
    chamado(session, outro_predio, titulo="Alheio")
    dados = client.get("/api/v1/chamados", headers=administracao).json()
    assert [i["id"] for i in dados["items"]] == [str(novo.id), str(velho.id)]
    assert dados["total"] == 2
    assert all(i["condominio"] is None for i in dados["items"])


def test_filtro_de_status_e_paginacao(client, session, predio, administracao):
    for dia in range(3):
        chamado(session, predio, criado_em=ANTES + timedelta(days=dia))
    chamado(session, predio, status="encerrado", criado_em=ANTES + timedelta(days=9))
    encerrados = client.get(
        "/api/v1/chamados", headers=administracao, params={"status": "encerrado"}
    )
    assert encerrados.json()["total"] == 1
    pagina = client.get(
        "/api/v1/chamados", headers=administracao, params={"page": 2, "page_size": 3}
    ).json()
    assert (pagina["total"], len(pagina["items"])) == (4, 1)
    assert (
        client.get("/api/v1/chamados", headers=administracao, params={"status": "x"}).status_code
        == 422
    )


def test_chamado_de_outro_condominio_e_404(client, session, outro_predio, administracao):
    alheio = chamado(session, outro_predio)
    session.commit()
    assert client.get(f"/api/v1/chamados/{alheio.id}", headers=administracao).status_code == 404
    resposta = client.post(
        f"/api/v1/chamados/{alheio.id}/mensagens", headers=administracao, json={"texto": "Oi"}
    )
    assert resposta.status_code == 404
    assert session.scalar(select(func.count()).select_from(ChamadoMensagem)) == 0


def test_detalhe_traz_as_mensagens_em_ordem_e_o_tipo_do_autor(
    client, session, predio, administracao
):
    item = chamado(session, predio, status="em_atendimento")
    for quando, autor, texto in [
        (ANTES + timedelta(minutes=2), predio.adm, "Segunda"),
        (ANTES + timedelta(minutes=1), predio.administracao, "Primeira"),
    ]:
        session.add(
            ChamadoMensagem(
                condominio_id=predio.condominio.id,
                chamado_id=item.id,
                autor_usuario_id=autor.id,
                texto=texto,
                criado_em=quando,
            )
        )
    session.flush()
    dados = client.get(f"/api/v1/chamados/{item.id}", headers=administracao).json()
    assert [(m["texto"], m["autor"]["tipo"]) for m in dados["mensagens"]] == [
        ("Primeira", "administracao"),
        ("Segunda", "plataforma"),
    ]
    assert dados["atendido_por"]["id"] == str(predio.adm.id)


def test_administracao_responde_sem_mudar_o_status(client, session, predio, administracao):
    item = chamado(session, predio)
    resposta = client.post(
        f"/api/v1/chamados/{item.id}/mensagens",
        headers=administracao,
        json={"texto": " Mais detalhes "},
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["texto"] == "Mais detalhes"
    assert resposta.json()["autor"]["tipo"] == "administracao"
    session.refresh(item)
    assert item.status == "aberto"
    assert eventos(session, "chamado.atender") == []


@pytest.mark.parametrize("texto", ["", "   ", "x" * 4001])
def test_mensagem_invalida_e_422(client, session, predio, administracao, texto):
    item = chamado(session, predio)
    resposta = client.post(
        f"/api/v1/chamados/{item.id}/mensagens", headers=administracao, json={"texto": texto}
    )
    assert resposta.status_code == 422


def test_mensagem_em_chamado_encerrado_e_409(client, session, predio, administracao, adm):
    item = chamado(session, predio, status="encerrado")
    session.commit()
    for headers, base in [(administracao, "chamados"), (adm, "plataforma/chamados")]:
        resposta = client.post(
            f"/api/v1/{base}/{item.id}/mensagens", headers=headers, json={"texto": "Oi"}
        )
        assert resposta.status_code == 409
        assert erro(resposta)["reason"] == "chamado_encerrado"
    assert session.scalar(select(func.count()).select_from(ChamadoMensagem)) == 0


# --- ADM --------------------------------------------------------------------------------------


def test_fila_padrao_so_nao_encerrados_do_mais_antigo_ao_mais_novo(
    client, session, predio, outro_predio, adm
):
    novo = chamado(session, predio, titulo="Novo", criado_em=ANTES + timedelta(days=2))
    velho = chamado(session, outro_predio, titulo="Velho", criado_em=ANTES)
    meio = chamado(
        session, predio, status="em_atendimento", titulo="Meio", criado_em=ANTES + timedelta(days=1)
    )
    chamado(session, predio, status="encerrado", titulo="Fechado")
    dados = client.get("/api/v1/plataforma/chamados", headers=adm).json()
    ids = [i["id"] for i in dados["items"]]
    assert ids == [str(velho.id), str(meio.id), str(novo.id)]
    assert {i["condominio"]["nome"] for i in dados["items"]} == {
        predio.condominio.nome,
        outro_predio.condominio.nome,
    }


def test_encerrados_vem_do_mais_recente_ao_mais_antigo(client, session, predio, adm):
    antigo = chamado(session, predio, status="encerrado", criado_em=ANTES)
    recente = chamado(session, predio, status="encerrado", criado_em=ANTES + timedelta(days=1))
    dados = client.get(
        "/api/v1/plataforma/chamados", headers=adm, params={"status": "encerrado"}
    ).json()
    assert [i["id"] for i in dados["items"]] == [str(recente.id), str(antigo.id)]


def test_filtros_da_fila(client, session, predio, outro_predio, adm):
    a = chamado(session, predio, titulo="Senha esquecida", criado_em=ANTES)
    b = chamado(
        session, outro_predio, titulo="Estrutura quebrada", criado_em=ANTES + timedelta(days=10)
    )

    def ids(**params):
        dados = client.get("/api/v1/plataforma/chamados", headers=adm, params=params).json()
        return {i["id"] for i in dados["items"]}

    assert ids(condominio_id=str(outro_predio.condominio.id)) == {str(b.id)}
    assert ids(busca="senha") == {str(a.id)}
    assert ids(busca="100%") == set()  # o curinga é literal
    assert ids(de="2020-01-05") == {str(b.id)}
    assert ids(ate="2020-01-01") == {str(a.id)}
    assert ids(status="em_atendimento") == set()
    assert (
        client.get("/api/v1/plataforma/chamados", headers=adm, params={"de": "ontem"}).status_code
        == 422
    )


def test_adm_ve_o_chamado_de_qualquer_condominio(client, session, outro_predio, adm):
    alheio = chamado(session, outro_predio)
    dados = client.get(f"/api/v1/plataforma/chamados/{alheio.id}", headers=adm).json()
    assert dados["condominio"]["id"] == str(outro_predio.condominio.id)
    assert client.get(f"/api/v1/plataforma/chamados/{uuid.uuid4()}", headers=adm).status_code == 404


def test_primeira_mensagem_do_adm_move_para_em_atendimento_uma_vez(client, session, predio, adm):
    item = chamado(session, predio)
    base = f"/api/v1/plataforma/chamados/{item.id}/mensagens"
    primeira = client.post(base, headers=adm, json={"texto": "Estamos vendo."})
    assert primeira.status_code == 201, primeira.text
    assert primeira.json()["autor"]["tipo"] == "plataforma"
    session.refresh(item)
    assert (item.status, item.atendido_por_usuario_id) == ("em_atendimento", predio.adm.id)
    assert client.post(base, headers=adm, json={"texto": "Resolvido?"}).status_code == 201
    [evento] = eventos(session, "chamado.atender")
    assert evento.recurso_id == item.id
    assert evento.condominio_id == predio.condominio.id
    assert evento.perfil == "plataforma"
    assert (evento.antes, evento.depois) == ({"status": "aberto"}, {"status": "em_atendimento"})


def test_encerrar_grava_data_audita_e_preserva_o_historico(client, session, predio, adm):
    item = chamado(session, predio)
    client.post(
        f"/api/v1/plataforma/chamados/{item.id}/mensagens", headers=adm, json={"texto": "Oi"}
    )
    resposta = client.post(
        f"/api/v1/plataforma/chamados/{item.id}/encerramento", headers=adm, json={}
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["status"] == "encerrado"
    assert dados["encerrado_em"]
    assert len(dados["mensagens"]) == 1
    [evento] = eventos(session, "chamado.encerrar")
    assert (evento.antes, evento.depois) == ({"status": "em_atendimento"}, {"status": "encerrado"})


def test_encerrar_chamado_aberto_registra_o_adm_no_atendimento(client, session, predio, adm):
    item = chamado(session, predio)
    assert (
        client.post(
            f"/api/v1/plataforma/chamados/{item.id}/encerramento", headers=adm, json={}
        ).status_code
        == 200
    )
    session.refresh(item)
    assert item.atendido_por_usuario_id == predio.adm.id


def test_encerrar_duas_vezes_e_409(client, session, predio, adm):
    item = chamado(session, predio, status="encerrado")
    session.commit()
    resposta = client.post(
        f"/api/v1/plataforma/chamados/{item.id}/encerramento", headers=adm, json={}
    )
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "chamado_ja_encerrado"
    assert eventos(session, "chamado.encerrar") == []


def test_encerramento_recusa_corpo_com_campos(client, session, predio, adm):
    item = chamado(session, predio)
    resposta = client.post(
        f"/api/v1/plataforma/chamados/{item.id}/encerramento", headers=adm, json={"status": "x"}
    )
    assert resposta.status_code == 422


def test_anexos_aparecem_nas_duas_visoes(client, session, predio, administracao, adm):
    item = chamado(session, predio)
    anexo = arquivo(session, predio)
    session.add(
        ChamadoAnexo(chamado_id=item.id, arquivo_id=anexo.id, condominio_id=predio.condominio.id)
    )
    session.flush()
    for headers, base in [(administracao, "chamados"), (adm, "plataforma/chamados")]:
        dados = client.get(f"/api/v1/{base}/{item.id}", headers=headers).json()
        assert dados["anexos"] == [str(anexo.id)]
