"""US-804: o ADM envia comunicados às Administrações dos condomínios ativos."""

import uuid

import pytest
from sqlalchemy import select

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.avisos.models import Comunicado, ComunicadoDestinatario
from tests.autorizacao.cenario import montar_predio

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]
URL = "/api/v1/plataforma/comunicados"


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.PLATAFORMA)


def corpo(**campos):
    base = {"titulo": "Manutenção do sistema", "texto": "Sábado, das 2h às 4h."}
    base.update(campos)
    return base


def enviar(client, adm, **campos):
    resposta = client.post(URL, headers=adm, json=corpo(**campos))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def destinatarios(session, comunicado_id):
    return set(
        session.scalars(
            select(ComunicadoDestinatario.condominio_id).where(
                ComunicadoDestinatario.comunicado_id == uuid.UUID(comunicado_id)
            )
        )
    )


# --- perfis e 401 -----------------------------------------------------------------------------


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_so_o_adm_envia_e_lista(client, session, predio, indice):
    headers = predio.cabecalho_de(PERFIS[indice])
    permitido = PERFIS[indice] == Perfil.PLATAFORMA
    session.commit()
    assert client.post(URL, headers=headers, json=corpo()).status_code == (
        201 if permitido else 403
    )
    session.commit()
    assert client.get(URL, headers=headers).status_code == (200 if permitido else 403)


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_so_a_administracao_le_os_comunicados_do_condominio(client, session, predio, indice):
    headers = predio.cabecalho_de(PERFIS[indice])
    session.commit()
    esperado = 200 if PERFIS[indice] == Perfil.ADMINISTRACAO else 403
    assert client.get("/api/v1/comunicados", headers=headers).status_code == esperado


def test_sem_token_e_401(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={}).status_code == 401
    assert client.get("/api/v1/comunicados").status_code == 401


# --- envio ------------------------------------------------------------------------------------


def test_envio_vai_para_os_condominios_ativos_e_audita(client, session, predio, outro_predio, adm):
    outro_predio.condominio.status = "desativado"
    ativo = montar_predio(session, "Condomínio ativo")
    session.flush()

    dados = enviar(client, adm)

    esperados = destinatarios(session, dados["id"])
    assert predio.condominio.id in esperados
    assert ativo.condominio.id in esperados
    assert outro_predio.condominio.id not in esperados  # só `ativo` recebe
    assert dados["total_destinatarios"] == len(esperados)
    assert dados["enviado_por"]["id"] == str(predio.adm.id)
    [evento] = session.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.acao == "comunicado.enviar")
    )
    assert evento.recurso_id == uuid.UUID(dados["id"])
    assert evento.perfil == "plataforma"
    assert evento.condominio_id is None
    assert evento.depois["total_destinatarios"] == len(esperados)


def test_condominio_criado_depois_nao_ve_comunicado_antigo(client, session, predio, adm):
    antigo = enviar(client, adm, titulo="Antigo")
    novo = montar_predio(session, "Condomínio novo")
    session.flush()

    assert novo.condominio.id not in destinatarios(session, antigo["id"])
    lista = client.get("/api/v1/comunicados", headers=novo.cabecalho_de(Perfil.ADMINISTRACAO))
    assert lista.status_code == 200
    assert lista.json()["items"] == []


@pytest.mark.parametrize(
    "campos",
    [
        {"titulo": ""},
        {"titulo": "   "},
        {"titulo": "x" * 121},
        {"texto": ""},
        {"texto": "x" * 4001},
        {"destinatarios": []},
    ],
)
def test_entrada_invalida_e_422(client, adm, campos):
    assert client.post(URL, headers=adm, json=corpo(**campos)).status_code == 422


def test_titulo_e_texto_sao_aparados(client, adm):
    dados = enviar(client, adm, titulo="  Aviso  ", texto="  Texto  ")
    assert (dados["titulo"], dados["texto"]) == ("Aviso", "Texto")


# --- consulta ---------------------------------------------------------------------------------


def test_lista_do_adm_com_total_de_destinatarios_do_mais_recente_ao_mais_antigo(
    client, session, adm
):
    primeiro = enviar(client, adm, titulo="Primeiro")
    segundo = enviar(client, adm, titulo="Segundo")
    primeiro_gravado = session.get(Comunicado, uuid.UUID(primeiro["id"]))
    primeiro_gravado.criado_em = primeiro_gravado.criado_em.replace(year=2020)
    session.flush()
    dados = client.get(URL, headers=adm).json()
    ids = [i["id"] for i in dados["items"]]
    assert ids[:2] == [segundo["id"], primeiro["id"]]
    assert dados["items"][0]["total_destinatarios"] == segundo["total_destinatarios"]
    assert dados["total"] >= 2


def test_paginacao(client, adm):
    for i in range(3):
        enviar(client, adm, titulo=f"Aviso {i}")
    dados = client.get(URL, headers=adm, params={"page": 2, "page_size": 2}).json()
    assert (dados["page"], dados["page_size"], len(dados["items"])) == (2, 2, dados["total"] - 2)
    assert client.get(URL, headers=adm, params={"page_size": 101}).status_code == 422


def test_detalhe_traz_os_condominios_destinatarios(client, session, predio, adm):
    dados = enviar(client, adm)
    detalhe = client.get(f"{URL}/{dados['id']}", headers=adm).json()
    assert str(predio.condominio.id) in {d["id"] for d in detalhe["destinatarios"]}
    assert len(detalhe["destinatarios"]) == dados["total_destinatarios"]
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=adm).status_code == 404


def test_administracao_so_ve_o_que_foi_enviado_ao_seu_condominio(
    client, session, predio, outro_predio, adm
):
    enviado = enviar(client, adm, titulo="Para todos")
    # Um comunicado direcionado só ao outro condomínio (o caso que a matriz protege).
    reservado = Comunicado(titulo="Só do outro", texto="x", enviado_por_usuario_id=predio.adm.id)
    session.add(reservado)
    session.flush()
    session.add(
        ComunicadoDestinatario(comunicado_id=reservado.id, condominio_id=outro_predio.condominio.id)
    )
    session.flush()

    meus = client.get("/api/v1/comunicados", headers=predio.cabecalho_de(Perfil.ADMINISTRACAO))
    ids = {i["id"] for i in meus.json()["items"]}
    assert enviado["id"] in ids
    assert str(reservado.id) not in ids
    item = meus.json()["items"][0]
    assert set(item) == {"id", "titulo", "texto", "criado_em"}  # sem lista de destinatários

    dele = client.get(
        "/api/v1/comunicados", headers=outro_predio.cabecalho_de(Perfil.ADMINISTRACAO)
    )
    assert str(reservado.id) in {i["id"] for i in dele.json()["items"]}
