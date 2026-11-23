from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.tempo import FUSO_CONDOMINIO, get_relogio
from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import Andar, Bloco, PermissaoAba
from app.modules.visitantes.models import RegistroVisita, Visitante
from tests.auditoria.conftest import cenario as cenario
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session

pytestmark = pytest.mark.postgres


@pytest.fixture
def portaria(session):
    predio = montar_predio(session)
    funcionario = Funcionario(
        condominio_id=predio.condominio.id, nome="Porteiro de teste", funcao="porteiro"
    )
    session.add_all(
        [
            funcionario,
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=predio.morador_unidade.id,
                aba="visitantes",
                com_acesso=True,
            ),
        ]
    )
    session.flush()
    momento = datetime(2030, 4, 2, 10, tzinfo=FUSO_CONDOMINIO)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_relogio] = lambda: lambda: momento
    with TestClient(app) as client:
        yield client, predio, funcionario


def cadastrar_visitante_para_contato(client, predio):
    cadastro = client.post(
        "/api/v1/visitantes",
        headers=predio.cabecalho_de("morador"),
        json={
            "unidade_id": str(predio.unidade_101.id),
            "nome": "Camila Exemplo",
            "cpf": "12345678909",
            "entrada_prevista": "2030-04-01",
            "saida_prevista": "2030-04-03",
        },
    )
    assert cadastro.status_code == 201, cadastro.text
    return cadastro.json()["id"]


def test_cancelamento_revoga_autorizacao_previa_e_permite_novo_contato(portaria):
    client, predio, funcionario = portaria
    visitante = cadastrar_visitante_para_contato(client, predio)
    porteiro = predio.cabecalho_de("funcionario")
    unidade = str(predio.unidade_101.id)
    alvo = {"visitante_id": visitante, "unidade_id": unidade}
    dados = {**alvo, "funcionario_id": str(funcionario.id)}
    morador = {"morador_id": str(predio.morador_unidade.id), "canal": "interfone"}

    autorizar = "/api/v1/portaria/autorizacoes"
    assert client.get(autorizar, headers=porteiro, params=alvo).json()[0]["id"] == visitante
    cancelado = client.post(
        f"/api/v1/visitantes/{visitante}/cancelamento", headers=predio.cabecalho_de("morador")
    )
    assert cancelado.status_code == 200, cancelado.text

    por_nome = client.get(
        "/api/v1/portaria/visitantes", headers=porteiro, params={"busca": "Camila"}
    )
    por_cpf = client.post(
        "/api/v1/portaria/visitantes/busca-documento",
        headers=porteiro,
        json={"unidade_id": unidade, "cpf": "12345678909"},
    )
    for resultado in (por_nome, por_cpf):
        assert resultado.status_code == 200, resultado.text
        assert [item["id"] for item in resultado.json()["items"]] == [visitante]

    assert client.get(autorizar, headers=porteiro, params=alvo).json() == []
    anterior = client.post(
        "/api/v1/visitas",
        headers=porteiro,
        json={
            **dados,
            "autorizacao_id": visitante,
        },
    )
    assert (
        anterior.status_code == 409 and anterior.json()["error"]["reason"] == "autorizacao_invalida"
    )
    for resposta in ("negou", "sem_resposta"):
        contato = client.post(
            "/api/v1/portaria/contatos",
            headers=porteiro,
            json={
                **dados,
                **morador,
                "resposta": resposta,
            },
        )
        assert contato.status_code == 201, contato.text
        assert contato.json()["resposta"] == resposta
    assert client.get("/api/v1/visitas", headers=porteiro).json()["total"] == 0

    nova = client.post(
        "/api/v1/visitas",
        headers=porteiro,
        json={
            **dados,
            "contato": {**morador, "resposta": "autorizou"},
        },
    )
    assert nova.status_code == 201, nova.text
    assert nova.json()["autorizacao"] is None and nova.json()["contato"]["resposta"] == "autorizou"
    assert client.get(autorizar, headers=porteiro, params=alvo).json() == []


def test_historico_de_contatos_identifica_bloco_e_andar(portaria, session):
    client, predio, funcionario = portaria
    bloco = Bloco(condominio_id=predio.condominio.id, nome="Bloco B")
    session.add(bloco)
    session.flush()
    andar = Andar(condominio_id=predio.condominio.id, bloco_id=bloco.id, nome="1º andar", ordem=1)
    session.add(andar)
    session.flush()
    predio.unidade_101.andar_id = andar.id
    predio.unidade_101.identificacao = "101"
    session.flush()

    visitante = cadastrar_visitante_para_contato(client, predio)
    porteiro = predio.cabecalho_de("funcionario")
    rota = "/api/v1/portaria/contatos"
    contato = client.post(
        rota,
        headers=porteiro,
        json={
            "visitante_id": visitante,
            "unidade_id": str(predio.unidade_101.id),
            "funcionario_id": str(funcionario.id),
            "morador_id": str(predio.morador_unidade.id),
            "canal": "telefone",
            "resposta": "negou",
        },
    )
    assert contato.status_code == 201, contato.text
    unidade = {"id": str(predio.unidade_101.id), "nome": "Bloco B / 1º andar / 101"}
    assert contato.json()["unidade"] == unidade
    historico = client.get(rota, headers=porteiro)
    assert historico.status_code == 200, historico.text
    assert historico.json()["items"][0]["unidade"] == unidade


def test_busca_por_cpf_distingue_cadastro_ativo_de_copia_cancelada(portaria):
    client, predio, _ = portaria
    cancelado = cadastrar_visitante_para_contato(client, predio)
    resposta = client.post(
        f"/api/v1/visitantes/{cancelado}/cancelamento", headers=predio.cabecalho_de("morador")
    )
    assert resposta.status_code == 200, resposta.text
    vigente = cadastrar_visitante_para_contato(client, predio)
    porteiro = predio.cabecalho_de("funcionario")
    busca = client.post(
        "/api/v1/portaria/visitantes/busca-documento",
        headers=porteiro,
        json={"unidade_id": str(predio.unidade_101.id), "cpf": "12345678909"},
    )
    assert busca.status_code == 200, busca.text
    assert {item["id"]: (item["ambigua"], item["cancelado"]) for item in busca.json()["items"]} == {
        cancelado: (False, True),
        vigente: (False, False),
    }
    por_nome = client.get(
        "/api/v1/portaria/visitantes", headers=porteiro, params={"busca": "Camila"}
    )
    assert por_nome.status_code == 200, por_nome.text
    assert [item["ambigua"] for item in por_nome.json()["items"]] == [True, True]


def test_visita_reutiliza_autorizacao_e_contato_negado_nao_abre_visita(session):
    predio = montar_predio(session)
    outro = montar_predio(session, "Outro prédio")
    funcionario = Funcionario(
        condominio_id=predio.condominio.id, nome="Porteiro de teste", funcao="porteiro"
    )
    session.add(funcionario)
    aba = PermissaoAba(
        condominio_id=predio.condominio.id,
        morador_unidade_id=predio.morador_unidade.id,
        aba="visitantes",
        com_acesso=True,
    )
    session.add(aba)
    session.flush()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    momento = datetime(2030, 4, 2, 10, tzinfo=FUSO_CONDOMINIO)
    app.dependency_overrides[get_relogio] = lambda: lambda: momento
    morador = predio.cabecalho_de("morador")
    porteiro = predio.cabecalho_de("funcionario")
    unidade = str(predio.unidade_101.id)

    with TestClient(app) as client:
        cadastro = client.post(
            "/api/v1/visitantes",
            headers=morador,
            json={
                "unidade_id": unidade,
                "nome": "Carlos Exemplo",
                "cpf": "12345678909",
                "entrada_prevista": "2030-04-01",
                "saida_prevista": "2030-04-02",
            },
        )
        assert cadastro.status_code == 201, cadastro.text
        visitante_id = cadastro.json()["id"]
        homonimo = client.post(
            "/api/v1/visitantes",
            headers=morador,
            json={
                "unidade_id": unidade,
                "nome": "Carlos Exemplo",
                "entrada_prevista": "2030-04-01",
                "saida_prevista": "2030-04-02",
            },
        )
        assert homonimo.status_code == 201
        por_nome = client.get(
            "/api/v1/portaria/visitantes",
            headers=porteiro,
            params={"busca": "Carlos Exemplo", "page_size": 1},
        )
        assert por_nome.json()["items"][0]["ambigua"] is True
        dados = {
            "visitante_id": visitante_id,
            "unidade_id": unidade,
            "funcionario_id": str(funcionario.id),
        }
        busca = client.post(
            "/api/v1/portaria/visitantes/busca-documento",
            headers=porteiro,
            json={"unidade_id": unidade, "cpf": "12345678909"},
        )
        assert busca.status_code == 200 and busca.json()["items"][0]["id"] == visitante_id
        assert busca.json()["items"][0]["ambigua"] is False
        assert "12345678909" not in busca.text
        entrada = client.post(
            "/api/v1/visitas", headers=porteiro, json={**dados, "autorizacao_id": visitante_id}
        )
        assert entrada.status_code == 201, entrada.text
        visita_id = entrada.json()["id"]
        assert (
            client.post(
                "/api/v1/visitas", headers=porteiro, json={**dados, "autorizacao_id": visitante_id}
            ).status_code
            == 409
        )
        saida = f"/api/v1/visitas/{visita_id}/saida"
        for esperado in (200, 409):
            assert (
                client.post(
                    saida, headers=porteiro, json={"funcionario_id": str(funcionario.id)}
                ).status_code
                == esperado
            )
        assert (
            client.post(
                "/api/v1/visitas", headers=porteiro, json={**dados, "autorizacao_id": visitante_id}
            ).status_code
            == 201
        )
        contato = client.post(
            "/api/v1/portaria/contatos",
            headers=porteiro,
            json={
                **dados,
                "morador_id": str(predio.morador_unidade.id),
                "canal": "interfone",
                "resposta": "negou",
            },
        )
        assert contato.status_code == 201, contato.text
        sem_resposta = client.post(
            "/api/v1/portaria/contatos",
            headers=porteiro,
            json={
                **dados,
                "morador_id": str(predio.morador_unidade.id),
                "canal": "interfone",
                "resposta": "sem_resposta",
            },
        )
        assert sem_resposta.status_code == 201, sem_resposta.text
        assert (
            client.get(
                "/api/v1/visitas", headers=porteiro, params={"status": "em_andamento"}
            ).json()["total"]
            == 1
        )
        assert client.get(f"/api/v1/visitas/{uuid4()}", headers=porteiro).status_code == 404
        assert (
            client.get(
                f"/api/v1/visitas/{visita_id}", headers=outro.cabecalho_de("funcionario")
            ).status_code
            == 404
        )
        assert client.get(f"/api/v1/visitas/{visita_id}", headers=morador).status_code == 403
        assert (
            client.post(
                f"/api/v1/visitantes/{visitante_id}/cancelamento", headers=morador
            ).status_code
            == 409
        )

        # Uma visita antiga sem evidência continua fechável depois de a autorização expirar.
        legado = RegistroVisita(
            condominio_id=predio.condominio.id,
            visitante_id=UUID(homonimo.json()["id"]),
            entrada_em=momento,
            entrada_por_funcionario_id=funcionario.id,
        )
        session.add(legado)
        session.flush()
        for evidencia in (
            {"autorizacao": {}},
            {"contato": None},
            {"contato": {"canal": "telefone"}},
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                legado.evidencia = evidencia
                session.flush()
        momento += timedelta(days=1)
        assert (
            client.get(f"/api/v1/visitas/{legado.id}", headers=porteiro).json()["autorizacao"]
            is None
        )
        assert (
            client.post(
                f"/api/v1/visitas/{legado.id}/saida",
                headers=porteiro,
                json={"funcionario_id": str(funcionario.id)},
            ).status_code
            == 200
        )

        dados_homonimo = {**dados, "visitante_id": homonimo.json()["id"]}
        assert (
            client.post(
                "/api/v1/visitas",
                headers=porteiro,
                json={
                    **dados_homonimo,
                    "autorizacao_id": homonimo.json()["id"],
                },
            ).status_code
            == 409
        )
        momento -= timedelta(days=1)
        aba.com_acesso = False
        session.flush()
        tentativa = client.post(
            "/api/v1/visitas",
            headers=porteiro,
            json={
                **dados_homonimo,
                "autorizacao_id": homonimo.json()["id"],
            },
        )
        assert tentativa.status_code == 409
        assert tentativa.json()["error"]["reason"] == "autorizacao_invalida"
        assert (
            client.get(
                "/api/v1/visitantes", headers=morador, params={"unidade_id": unidade}
            ).status_code
            == 403
        )
        contato_autorizado = client.post(
            "/api/v1/visitas",
            headers=porteiro,
            json={
                **dados_homonimo,
                "contato": {
                    "morador_id": str(predio.morador_unidade.id),
                    "canal": "telefone",
                    "resposta": "autorizou",
                },
            },
        )
        assert contato_autorizado.status_code == 201, contato_autorizado.text
        assert contato_autorizado.json()["contato"]["canal"] == "telefone"
        funcionario.ativo = False
        funcionario.desligado_em = momento
        session.flush()
        assert (
            client.post(
                f"/api/v1/visitas/{contato_autorizado.json()['id']}/saida",
                headers=porteiro,
                json={"funcionario_id": str(funcionario.id)},
            ).status_code
            == 404
        )


def test_duas_requisicoes_simultaneas_so_gravam_uma_entrada_e_uma_saida(cenario):
    app = create_app()
    momento = datetime(2030, 4, 2, 10, tzinfo=FUSO_CONDOMINIO)
    app.dependency_overrides[get_relogio] = lambda: lambda: momento
    predio = cenario.a
    with cenario.fabrica.begin() as session:
        session.add(
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=predio.morador_unidade.id,
                aba="visitantes",
                com_acesso=True,
            )
        )

    with TestClient(app) as client:
        criado = client.post(
            "/api/v1/visitantes",
            headers=predio.cabecalho_de("morador"),
            json={
                "nome": "Visitante Concorrente",
                "unidade_id": str(predio.unidade_101.id),
                "entrada_prevista": "2030-04-02",
                "saida_prevista": "2030-04-02",
            },
        )
        assert criado.status_code == 201, criado.text
        id_ = criado.json()["id"]
        funcionario_id = str(cenario.funcionario.id)
        porteiro = predio.cabecalho_de("funcionario")

        def simultaneas(rota, dados):
            barreira = Barrier(2, timeout=10)

            def enviar(_):
                barreira.wait()
                return client.post(rota, headers=porteiro, json=dados)

            with ThreadPoolExecutor(max_workers=2) as pool:
                return sorted(pool.map(enviar, (0, 1)), key=lambda r: r.status_code)

        try:
            entradas = simultaneas(
                "/api/v1/visitas",
                {
                    "funcionario_id": funcionario_id,
                    "visitante_id": id_,
                    "unidade_id": str(predio.unidade_101.id),
                    "autorizacao_id": id_,
                },
            )
            assert [r.status_code for r in entradas] == [201, 409]
            visita = entradas[0].json()["id"]
            saidas = simultaneas(
                f"/api/v1/visitas/{visita}/saida", {"funcionario_id": funcionario_id}
            )
            assert [r.status_code for r in saidas] == [200, 409]
            with cenario.fabrica() as session:
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(RegistroVisita)
                        .where(RegistroVisita.visitante_id == UUID(id_))
                    )
                    == 1
                )
                acoes = session.scalars(
                    select(RegistroAuditoria.acao).where(
                        RegistroAuditoria.recurso_id == UUID(visita)
                    )
                ).all()
                assert sorted(acoes) == ["visita.entrar", "visita.sair"]
        finally:
            with cenario.fabrica.begin() as session:
                session.execute(
                    delete(RegistroVisita).where(RegistroVisita.visitante_id == UUID(id_))
                )
                session.execute(delete(Visitante).where(Visitante.id == UUID(id_)))
