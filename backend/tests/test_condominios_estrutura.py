"""US-205/206: gestão mínima da estrutura, dados e logo sobre a base migrada."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.main import create_app
from app.modules.auditoria import service as auditoria
from app.modules.condominios.models import VinculoCondominio
from app.modules.encomendas.models import Encomenda
from app.modules.storage.models import Arquivo
from app.modules.storage.router import get_storage_adapter
from app.modules.unidades.models import Andar, Bloco, ChaveAcesso, Unidade
from app.modules.unidades.repository import RepositorioUnidades
from app.modules.unidades.service import gerar_chave
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from tests.auditoria.conftest import cenario as cenario
from tests.reservas.cenario import criar_area, criar_reserva
from tests.task29.conftest import arquivo
from tests.task29.conftest import caso as caso
from tests.task29.conftest import client as client
from tests.task29.conftest import session as session
from tests.test_condominios_reenvio import dados, escritas, eventos
from tests.test_encomendas_api import adapter as adapter
from tests.test_encomendas_api import criar_encomenda, criar_funcionario

pytestmark = pytest.mark.postgres
BASE = "/api/v1/estrutura"


def novas_escritas(c):
    r = {"responsavel_id": str(c.responsavel.id)}
    return [
        (BASE + "/blocos", r | {"nome": "Bloco novo"}),
        (f"{BASE}/blocos/{c.bloco.id}/andares", r | {"nome": "Novo andar", "ordem": 2}),
        (f"{BASE}/andares/{c.andar.id}/unidades", r | {"identificacao": "103"}),
        (f"{BASE}/unidades/{c.a.unidade_102.id}/desativacao", r.copy()),
        (f"{BASE}/unidades/{c.a.unidade_102.id}/reativacao", r.copy()),
    ]


def mudar(client, c, tipo, id_, acao):
    return client.post(
        f"{BASE}/{tipo}/{id_}/{acao}",
        headers=c.a.cabecalho_de("administracao"),
        json={"responsavel_id": str(c.responsavel.id)},
    )


def chaves(session, unidade_id):
    return list(session.scalars(select(ChaveAcesso).where(ChaveAcesso.unidade_id == unidade_id)))


@pytest.mark.parametrize("estado", ["pendente", "rejeitado", "ativo"])
def test_edicao_e_adicao_nos_estados_permitidos(client, session, caso, estado):
    c = caso
    c.a.condominio.status = estado
    c.a.condominio.motivo_rejeicao = "Corrigir" if estado == "rejeitado" else None
    session.commit()
    headers = c.a.cabecalho_de("administracao")
    ids = (c.bloco.id, c.andar.id, c.a.unidade_101.id, c.a.morador_unidade.id)
    for metodo, rota, corpo in escritas(c)[:4]:
        resposta = client.request(metodo, rota, headers=headers, json=corpo)
        assert resposta.status_code == 200, resposta.text
    criados = []
    for rota, corpo in novas_escritas(c)[:3]:
        resposta = client.post(rota, headers=headers, json=corpo)
        assert resposta.status_code == 201, resposta.text
        assert resposta.headers["Location"] == "/api/v1/condominio/estrutura"
        criados.append(uuid.UUID(resposta.json()["id"]))
    assert (c.bloco.id, c.andar.id, c.a.unidade_101.id, c.a.morador_unidade.id) == ids
    session.refresh(c.a.morador_unidade)
    assert c.a.morador_unidade.status == "ativo"
    session.refresh(c.a.condominio)
    assert c.a.condominio.status == estado
    novas_chaves = chaves(session, criados[-1])
    assert len(novas_chaves) == int(estado == "ativo")
    if novas_chaves:
        assert novas_chaves[0].revogada_em is None
    registros = eventos(session, c.a.condominio.id)
    assert len(registros) == 7
    for id_, tipo in zip(criados, ["bloco", "andar", "unidade"], strict=True):
        [evento] = [e for e in registros if e.recurso_id == id_]
        assert evento.acao == "estrutura.editar" and evento.recurso_tipo == tipo
        assert evento.antes == {} and evento.depois["ativo"] is True
        assert evento.responsavel_nome == c.responsavel.nome
        assert evento.usuario_id == c.a.administracao.id
        assert "codigo" not in str(evento.depois)
    arvore = client.get("/api/v1/condominio/estrutura", headers=headers).json()
    assert len(arvore["blocos"]) == 2


def test_condominio_desativado_bloqueia_edicao_criacao_e_status(client, session, caso):
    c = caso
    c.a.condominio.status = "desativado"
    session.commit()
    headers = c.a.cabecalho_de("administracao")
    for metodo, rota, corpo in escritas(c)[:4]:
        assert client.request(metodo, rota, headers=headers, json=corpo).status_code == 403
    for rota, corpo in novas_escritas(c):
        assert client.post(rota, headers=headers, json=corpo).status_code == 403
    assert client.get("/api/v1/condominio/estrutura", headers=headers).status_code == 200
    assert eventos(session, c.a.condominio.id) == []


@pytest.mark.parametrize("indice", range(3))
def test_criacao_rejeita_duplicata_sem_persistencia_parcial(client, session, caso, indice):
    rota, corpo = novas_escritas(caso)[indice]
    headers = caso.a.cabecalho_de("administracao")
    assert client.post(rota, headers=headers, json=corpo).status_code == 201
    resposta = client.post(rota, headers=headers, json=corpo)
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "nome_duplicado"
    assert len(eventos(session, caso.a.condominio.id)) == 1


@pytest.mark.parametrize("perfil", [None, "morador", "funcionario", "plataforma"])
def test_novas_operacoes_restritas_a_administracao(client, caso, perfil):
    headers = caso.a.cabecalho_de(perfil) if perfil else {}
    for rota, corpo in novas_escritas(caso):
        resposta = client.post(rota, headers=headers, json=corpo)
        assert resposta.status_code == (403 if perfil else 401), resposta.text


@pytest.mark.parametrize("responsavel", ["ausente", "outro", "inativo"])
def test_novas_operacoes_exigem_responsavel_ativo_local(client, session, caso, responsavel):
    if responsavel == "inativo":
        caso.responsavel.ativo = False
        session.commit()
    for rota, corpo in novas_escritas(caso):
        if responsavel == "ausente":
            corpo.pop("responsavel_id")
        elif responsavel == "outro":
            corpo["responsavel_id"] = str(caso.outro.id)
        resposta = client.post(rota, headers=caso.a.cabecalho_de("administracao"), json=corpo)
        assert resposta.status_code == (422 if responsavel == "ausente" else 404), resposta.text
    assert eventos(session, caso.a.condominio.id) == []


def test_elementos_e_pais_de_outro_condominio_nao_sao_acessiveis(client, session, caso):
    c = caso
    headers = c.b.cabecalho_de("administracao")
    for rota, corpo in novas_escritas(c)[1:]:
        corpo["responsavel_id"] = str(c.outro.id)
        assert client.post(rota, headers=headers, json=corpo).status_code == 404
    rota, corpo = novas_escritas(c)[1]
    inexistente = rota.replace(str(c.bloco.id), str(uuid.uuid4()))
    assert (
        client.post(inexistente, headers=c.a.cabecalho_de("administracao"), json=corpo).status_code
        == 404
    )
    assert eventos(session, c.a.condominio.id) == []


def test_desativacao_reativacao_respeitam_vinculos_pais_e_chaves(client, session, caso):
    c = caso
    for tipo, id_, motivo in [
        ("unidades", c.a.unidade_101.id, "unidade_com_vinculo_ativo"),
        ("andares", c.andar.id, "estrutura_com_unidades_ativas"),
        ("blocos", c.bloco.id, "estrutura_com_unidades_ativas"),
    ]:
        resposta = mudar(client, c, tipo, id_, "desativacao")
        assert resposta.status_code == 409
        assert resposta.json()["error"]["reason"] == motivo
    antiga = gerar_chave(session, c.a.unidade_102, datetime.now(UTC))
    session.commit()
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "desativacao").status_code == 200
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "desativacao").status_code == 409
    session.refresh(antiga)
    assert antiga.revogada_em is not None
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "reativacao").status_code == 200
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "reativacao").status_code == 409
    assert len(chaves(session, c.a.unidade_102.id)) == 2
    assert sum(k.revogada_em is None for k in chaves(session, c.a.unidade_102.id)) == 1
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "desativacao").status_code == 200
    c.a.morador_unidade.status = "desvinculado"
    c.a.morador_unidade.desvinculado_em = datetime.now(UTC)
    session.commit()
    assert mudar(client, c, "unidades", c.a.unidade_101.id, "desativacao").status_code == 200
    assert mudar(client, c, "andares", c.andar.id, "desativacao").status_code == 200
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "reativacao").status_code == 409
    rota, corpo = novas_escritas(c)[2]
    assert (
        client.post(rota, headers=c.a.cabecalho_de("administracao"), json=corpo).status_code == 409
    )
    assert mudar(client, c, "blocos", c.bloco.id, "desativacao").status_code == 200
    assert mudar(client, c, "andares", c.andar.id, "reativacao").status_code == 409
    rota, corpo = novas_escritas(c)[1]
    assert (
        client.post(rota, headers=c.a.cabecalho_de("administracao"), json=corpo).status_code == 409
    )
    assert mudar(client, c, "blocos", c.bloco.id, "reativacao").status_code == 200
    assert mudar(client, c, "andares", c.andar.id, "reativacao").status_code == 200
    assert mudar(client, c, "unidades", c.a.unidade_102.id, "reativacao").status_code == 200
    assert sum(k.revogada_em is None for k in chaves(session, c.a.unidade_102.id)) == 1
    registros = eventos(session, c.a.condominio.id)
    assert len(registros) == 9
    assert all(e.antes["ativo"] != e.depois["ativo"] for e in registros)
    assert all(e.responsavel_nome == c.responsavel.nome for e in registros)


def test_desativar_preserva_encomendas_visitas_veiculos_reservas_e_vinculo(client, session, caso):
    c = caso
    funcionario = criar_funcionario(session, c.a)
    encomenda = criar_encomenda(session, c.a, funcionario, descricao="Histórico preservado")
    visitante = Visitante(
        condominio_id=c.a.condominio.id,
        unidade_id=c.a.unidade_101.id,
        nome="Visitante histórico",
        entrada_prevista=date(2026, 11, 22),
        saida_prevista=date(2026, 11, 23),
        cadastrado_por_usuario_id=c.a.morador.id,
    )
    veiculo = Veiculo(
        condominio_id=c.a.condominio.id,
        unidade_id=c.a.unidade_101.id,
        placa="ABC1D23",
        marca="Marca",
        modelo="Modelo",
        cor="Branco",
    )
    session.add_all([visitante, veiculo])
    session.flush()
    visita = RegistroVisita(
        condominio_id=c.a.condominio.id,
        visitante_id=visitante.id,
        entrada_por_funcionario_id=funcionario.id,
    )
    session.add(visita)
    reserva = criar_reserva(
        session, c.a, criar_area(session, c.a), data=date(2026, 12, 10), hora=10
    )
    chave = gerar_chave(session, c.a.unidade_101, datetime.now(UTC))
    c.a.morador_unidade.status = "desvinculado"
    c.a.morador_unidade.desvinculado_em = datetime.now(UTC)
    session.commit()
    # Captura todos os campos, inclusive referências e datas dos registros existentes.
    registros = [encomenda, visitante, visita, veiculo, reserva, c.a.morador_unidade]
    antes = [
        {col.key: getattr(item, col.key) for col in item.__table__.columns} for item in registros
    ]
    resposta = mudar(client, c, "unidades", c.a.unidade_101.id, "desativacao")
    assert resposta.status_code == 200, resposta.text
    for item, campos in zip(registros, antes, strict=True):
        session.refresh(item)
        assert {col.key: getattr(item, col.key) for col in item.__table__.columns} == campos
    session.refresh(chave)
    session.refresh(c.a.unidade_101)
    assert chave.revogada_em is not None and not c.a.unidade_101.ativo


@pytest.mark.parametrize("operacao", range(5))
def test_falha_de_auditoria_reverte_criacao_status_e_chaves(
    client, session, caso, monkeypatch, operacao
):
    c = caso
    chave = gerar_chave(session, c.a.unidade_102, datetime.now(UTC))
    if operacao == 4:
        c.a.unidade_102.ativo = False
        chave.revogada_em = datetime.now(UTC)
    session.commit()
    antes = {
        modelo: list(session.scalars(select(modelo.id)))
        for modelo in (Bloco, Andar, Unidade, ChaveAcesso)
    }
    original = auditoria.registrar_acao

    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Falha controlada após gravar auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    rota, corpo = novas_escritas(c)[operacao]
    resposta = client.post(rota, headers=c.a.cabecalho_de("administracao"), json=corpo)
    assert resposta.status_code == 500, resposta.text
    for modelo, ids in antes.items():
        assert set(session.scalars(select(modelo.id))) == set(ids)
    session.refresh(c.a.unidade_102)
    session.refresh(chave)
    assert c.a.unidade_102.ativo == (operacao != 4)
    assert (chave.revogada_em is not None) == (operacao == 4)
    assert eventos(session, c.a.condominio.id) == []


def test_logo_associacao_substituicao_remocao_e_download_isolado(client, session, caso, adapter):
    c = caso
    client.app.dependency_overrides[get_storage_adapter] = lambda: adapter
    logos = [arquivo(session, c.a), arquivo(session, c.a)]
    headers = c.a.cabecalho_de("administracao")
    for logo in logos:
        resposta = client.put(
            "/api/v1/condominio",
            headers=headers,
            json=dados(c) | {"logo_arquivo_id": str(logo.id)},
        )
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["logo_arquivo_id"] == str(logo.id)
        rota = f"/api/v1/arquivos/{logo.id}/download"
        for perfil in ("administracao", "morador", "funcionario"):
            assert client.get(rota, headers=c.a.cabecalho_de(perfil)).status_code == 200
        assert client.get(rota, headers=c.b.cabecalho_de("administracao")).status_code == 404
        assert client.get(rota, headers=c.a.cabecalho_de("plataforma")).status_code == 404
    resposta = client.put("/api/v1/condominio", headers=headers, json=dados(c))
    assert resposta.json()["logo_arquivo_id"] == str(logos[-1].id)
    resposta = client.put(
        "/api/v1/condominio", headers=headers, json=dados(c) | {"logo_arquivo_id": None}
    )
    assert resposta.status_code == 200 and resposta.json()["logo_arquivo_id"] is None
    assert all(session.get(Arquivo, logo.id) is not None for logo in logos)
    assert any("logo_arquivo_id" in e.depois for e in eventos(session, c.a.condominio.id))


@pytest.mark.parametrize("tipo", ["outro", "autor", "mime", "modulo"])
def test_logo_rejeita_referencia_invalida_sem_alterar_dados(client, session, caso, tipo):
    c = caso
    logo = arquivo(
        session,
        c.b if tipo == "outro" else c.a,
        autor=c.a.morador.id if tipo == "autor" else None,
        mime="application/pdf" if tipo == "mime" else "image/png",
        modulo="encomendas" if tipo == "modulo" else "fotos",
    )
    nome = c.a.condominio.nome
    resposta = client.put(
        "/api/v1/condominio",
        headers=c.a.cabecalho_de("administracao"),
        json=dados(c) | {"logo_arquivo_id": str(logo.id)},
    )
    assert resposta.status_code == 404
    session.refresh(c.a.condominio)
    assert c.a.condominio.nome == nome and c.a.condominio.logo_arquivo_id is None
    assert eventos(session, c.a.condominio.id) == []


def test_alternancia_existente_seleciona_contexto_e_preserva_isolamento(client, session, caso):
    c = caso
    c.a.administracao.tipo_cadastro = "administracao"
    session.add(
        VinculoCondominio(
            usuario_id=c.a.administracao.id, condominio_id=c.b.condominio.id, perfil="administracao"
        )
    )
    session.commit()
    headers = c.a.cabecalho_de("administracao")
    lista = client.get("/api/v1/condominios/meus", headers=headers)
    assert lista.status_code == 200, lista.text
    assert {p["id"] for p in lista.json()} == {str(c.a.condominio.id), str(c.b.condominio.id)}
    selecao = client.post(
        "/api/v1/auth/selecionar-condominio",
        headers=headers,
        json={"condominio_id": str(c.b.condominio.id)},
    )
    assert selecao.status_code == 200, selecao.text
    selecionado = {"Authorization": f"Bearer {selecao.json()['access_token']}"}
    consulta = client.get("/api/v1/condominio", headers=selecionado)
    assert consulta.status_code == 200 and consulta.json()["id"] == str(c.b.condominio.id)
    resposta = client.put(
        f"{BASE}/blocos/{c.bloco.id}",
        headers=selecionado,
        json={"nome": "Indevido", "responsavel_id": str(c.outro.id)},
    )
    assert resposta.status_code == 404


def test_trava_da_estrutura_nao_bloqueia_fk_de_encomenda_concorrente(cenario, monkeypatch):
    c = cenario
    esperando_unidade = threading.Event()
    original = RepositorioUnidades.bloquear

    def bloquear(self, id_):
        esperando_unidade.set()
        return original(self, id_)

    monkeypatch.setattr(RepositorioUnidades, "bloquear", bloquear)

    def desativar():
        with TestClient(create_app()) as http:
            return http.post(
                f"{BASE}/unidades/{c.a.unidade_101.id}/desativacao",
                headers=c.a.cabecalho_de("administracao"),
                json={"responsavel_id": str(c.responsavel.id)},
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            with c.fabrica() as portaria:
                # Ordem já usada pelo cadastro de encomendas: unidade antes das FKs.
                portaria.scalar(
                    select(Unidade)
                    .where(Unidade.id == c.a.unidade_101.id)
                    .with_for_update(read=True)
                )
                futuro = executor.submit(desativar)
                assert esperando_unidade.wait(timeout=10)
                portaria.execute(text("SET LOCAL lock_timeout = '1s'"))
                encomenda = criar_encomenda(
                    portaria, c.a, c.funcionario, descricao="Operação concorrente"
                )
                id_encomenda = encomenda.id
                portaria.commit()
            resposta = futuro.result(timeout=10)
            assert resposta.status_code == 409, resposta.text
        with c.fabrica() as session:
            assert session.get(Encomenda, id_encomenda) is not None
            assert session.get(Unidade, c.a.unidade_101.id).ativo is True
    finally:
        # Apenas os dados deste teste confirmado; a fixture limpa seus demais UUIDs.
        with c.fabrica() as session:
            session.execute(delete(Encomenda).where(Encomenda.condominio_id == c.a.condominio.id))
            session.execute(delete(Arquivo).where(Arquivo.condominio_id == c.a.condominio.id))
            session.commit()
