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
from app.modules.unidades.models import MoradorUnidade, PermissaoAba
from app.modules.visitantes.models import RegistroVisita, Visitante
from tests.auditoria.conftest import cenario as cenario
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de, vincular

pytestmark = pytest.mark.postgres


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


def test_rotas_complementares_e_comorador_mesma_unidade(session):
    predio = montar_predio(session)
    comorador = criar_usuario(session)
    vincular(session, comorador, predio.condominio, perfil="morador")
    vinculo_comorador = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=predio.unidade_101.id,
        usuario_id=comorador.id,
        origem="chave",
    )
    funcionario = Funcionario(
        condominio_id=predio.condominio.id, nome="Porteiro Turno B", funcao="porteiro"
    )
    session.add_all([vinculo_comorador, funcionario])
    session.flush()
    session.add_all(
        [
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=predio.morador_unidade.id,
                aba="visitantes",
                com_acesso=True,
            ),
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=vinculo_comorador.id,
                aba="visitantes",
                com_acesso=True,
            ),
        ]
    )
    session.flush()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    momento = datetime(2030, 4, 2, 10, tzinfo=FUSO_CONDOMINIO)
    app.dependency_overrides[get_relogio] = lambda: lambda: momento

    autor_h = predio.cabecalho_de("morador")
    comorador_h = cabecalho(token_de(comorador, predio.condominio.id, perfil="morador"))
    porteiro_h = predio.cabecalho_de("funcionario")
    unidade = str(predio.unidade_101.id)

    with TestClient(app) as client:
        criado = client.post(
            "/api/v1/visitantes",
            headers=autor_h,
            json={
                "unidade_id": unidade,
                "nome": "Marina Costa",
                "cpf": "52998224725",
                "observacoes": "Chega às 10h",
                "entrada_prevista": "2030-04-02",
                "saida_prevista": "2030-04-03",
            },
        )
        assert criado.status_code == 201
        vid = criado.json()["id"]

        # Co-morador da mesma unidade consulta CPF/observações e edita antes do uso
        detalhe = client.get(f"/api/v1/visitantes/{vid}", headers=comorador_h)
        assert detalhe.status_code == 200
        assert detalhe.json()["cpf"] == "52998224725"

        editado = client.put(
            f"/api/v1/visitantes/{vid}",
            headers=comorador_h,
            json={
                "nome": "Marina Alves Costa",
                "cpf": "52998224725",
                "observacoes": "Chega às 11h",
                "entrada_prevista": "2030-04-02",
                "saida_prevista": "2030-04-03",
            },
        )
        assert editado.status_code == 200
        assert editado.json()["nome"] == "Marina Alves Costa"

        # Autorizações vigentes na portaria e busca vazia sem 422
        autorizacoes = client.get(
            "/api/v1/portaria/autorizacoes",
            headers=porteiro_h,
            params={"visitante_id": vid, "unidade_id": unidade},
        )
        assert autorizacoes.status_code == 200
        assert len(autorizacoes.json()) == 1
        assert (
            client.get(
                "/api/v1/portaria/visitantes", headers=porteiro_h, params={"busca": ""}
            ).status_code
            == 200
        )

        # Após visita registrada, PUT retorna 409 visitante_ja_utilizado
        entrada = client.post(
            "/api/v1/visitas",
            headers=porteiro_h,
            json={
                "visitante_id": vid,
                "unidade_id": unidade,
                "funcionario_id": str(funcionario.id),
                "autorizacao_id": vid,
            },
        )
        assert entrada.status_code == 201
        visita_id = entrada.json()["id"]
        assert (
            client.get("/api/v1/visitas", headers=porteiro_h, params={"busca": "101"}).json()[
                "total"
            ]
            >= 1
        )
        assert (
            client.post(
                f"/api/v1/visitas/{visita_id}/saida",
                headers=porteiro_h,
                json={"funcionario_id": str(funcionario.id)},
            ).status_code
            == 200
        )
        bloqueado = client.put(
            f"/api/v1/visitantes/{vid}",
            headers=comorador_h,
            json={
                "nome": "Marina Alves",
                "entrada_prevista": "2030-04-02",
                "saida_prevista": "2030-04-03",
            },
        )
        assert bloqueado.status_code == 409
        assert bloqueado.json()["error"]["reason"] == "visitante_ja_utilizado"

        # Listagem de contatos e cancelamento por co-morador
        assert (
            client.post(
                "/api/v1/portaria/contatos",
                headers=porteiro_h,
                json={
                    "visitante_id": vid,
                    "unidade_id": unidade,
                    "funcionario_id": str(funcionario.id),
                    "morador_id": str(predio.morador_unidade.id),
                    "canal": "interfone",
                    "resposta": "sem_resposta",
                },
            ).status_code
            == 201
        )
        contatos = client.get("/api/v1/portaria/contatos", headers=porteiro_h)
        assert contatos.status_code == 200 and contatos.json()["total"] == 1
        assert (
            client.post(f"/api/v1/visitantes/{vid}/cancelamento", headers=comorador_h).status_code
            == 200
        )
