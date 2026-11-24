from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.tempo import FUSO_CONDOMINIO, get_relogio
from app.db.session import get_session
from app.main import create_app
from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import MoradorUnidade, PermissaoAba
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from tests.auditoria.conftest import Cenario
from tests.auditoria.conftest import cenario as cenario
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session

pytestmark = pytest.mark.postgres
VEICULOS = "/api/v1/veiculos"
AVULSOS = "/api/v1/portaria/visitantes/avulsos"


@pytest.fixture
def client(session: Session) -> Generator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_relogio] = lambda: (
        lambda: datetime(2030, 4, 2, 10, tzinfo=FUSO_CONDOMINIO)
    )
    with TestClient(app) as client:
        yield client


def test_veiculos_limite_duplicidade_e_perfis(client: TestClient, session: Session) -> None:
    predio = montar_predio(session)
    outro = montar_predio(session, "Outro condomínio")
    morador = predio.cabecalho_de("morador")
    porteiro = predio.cabecalho_de("funcionario")
    administracao = predio.cabecalho_de("administracao")
    unidade = str(predio.unidade_101.id)
    outra_unidade = str(predio.unidade_102.id)
    segundo_vinculo = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=predio.unidade_102.id,
        usuario_id=predio.morador.id,
        origem="cadastro",
    )
    session.add(segundo_vinculo)
    session.flush()
    abas = [
        PermissaoAba(
            condominio_id=predio.condominio.id,
            morador_unidade_id=vinculo.id,
            aba="veiculos",
            com_acesso=True,
        )
        for vinculo in (predio.morador_unidade, segundo_vinculo)
    ]
    session.add_all(abas)
    session.flush()
    carro = {"marca": "Fiat", "modelo": "Argo", "cor": "Prata", "placa": "abc-1d23"}
    dados = {**carro, "unidade_id": unidade}
    assert client.post(VEICULOS, headers=porteiro, json=dados).status_code == 403
    assert (
        client.post(VEICULOS, headers=morador, json={**dados, "placa": "inválida"}).status_code
        == 422
    )
    criado = client.post(VEICULOS, headers=morador, json=dados)
    assert criado.status_code == 201, criado.text
    assert criado.json()["placa"] == "ABC1D23"
    detalhe = f"{VEICULOS}/{criado.json()['id']}"
    assert criado.headers["Location"] == detalhe

    repetido = client.post(VEICULOS, headers=morador, json=dados)
    assert repetido.status_code == 409, repetido.text
    assert "placa_ja_cadastrada_na_unidade" in repetido.text
    outra = client.post(VEICULOS, headers=morador, json={**dados, "unidade_id": outra_unidade})
    assert outra.status_code == 201, outra.text
    assert "placa_duplicada" not in outra.json()
    consulta = client.get(VEICULOS, headers=porteiro, params={"busca": "Abc-1d23"})
    assert consulta.status_code == 200, consulta.text
    assert {item["unidade"]["id"] for item in consulta.json()["items"]} == {unidade, outra_unidade}
    assert all("placa_duplicada" not in item for item in consulta.json()["items"])
    assert client.get(detalhe, headers=administracao).json()["placa_duplicada"] is True
    assert client.get(detalhe, headers=outro.cabecalho_de("funcionario")).status_code == 404
    assert client.get(VEICULOS, headers=outro.cabecalho_de("administracao")).json()["total"] == 0
    assert client.get(VEICULOS, headers=morador).status_code == 422

    for numero in range(4):
        resposta = client.post(
            VEICULOS, headers=morador, json={**dados, "placa": f"DEF1A0{numero}"}
        )
        assert resposta.status_code == 201, resposta.text
    sexto = client.post(VEICULOS, headers=morador, json={**dados, "placa": "DEF1A04"})
    assert sexto.status_code == 409 and "limite_veiculos" in sexto.text
    repetido_com_cinco = client.post(VEICULOS, headers=morador, json=dados)
    assert repetido_com_cinco.status_code == 409
    assert "placa_ja_cadastrada_na_unidade" in repetido_com_cinco.text
    edicao = client.put(detalhe, headers=morador, json={**carro, "cor": "Azul"})
    assert edicao.status_code == 200 and edicao.json()["cor"] == "Azul"
    assert (
        client.put(detalhe, headers=morador, json={**dados, "placa": "DEF1A00"}).status_code == 409
    )
    assert client.post(f"{detalhe}/remocao", headers=porteiro, json={}).status_code == 403
    removido = client.post(f"{detalhe}/remocao", headers=morador, json={})
    assert removido.status_code == 200 and removido.json()["ativo"] is False
    assert client.get(detalhe, headers=porteiro).status_code == 404
    assert client.post(VEICULOS, headers=morador, json=dados).status_code == 201

    abas[0].com_acesso = False
    session.flush()
    assert client.get(VEICULOS, headers=morador, params={"unidade_id": unidade}).status_code == 403


def test_avulso_grava_entrada_e_preserva_dados_no_escopo(
    client: TestClient, session: Session
) -> None:
    predio = montar_predio(session)
    outro = montar_predio(session, "Outro condomínio")
    morador = predio.cabecalho_de("morador")
    porteiro = predio.cabecalho_de("funcionario")
    unidade = str(predio.unidade_101.id)
    funcionario = Funcionario(
        condominio_id=predio.condominio.id, nome="Porteiro de teste", funcao="porteiro"
    )
    session.add(funcionario)
    session.add(
        PermissaoAba(
            condominio_id=predio.condominio.id,
            morador_unidade_id=predio.morador_unidade.id,
            aba="visitantes",
            com_acesso=True,
        )
    )
    session.flush()
    contato = {
        "canal": "interfone",
        "resposta": "autorizou",
        "morador_id": str(predio.morador_unidade.id),
    }
    cpf = "12345678909"
    dados = {
        "nome": "Camila Exemplo",
        "cpf": cpf,
        "unidade_id": unidade,
        "funcionario_id": str(funcionario.id),
        "contato": contato,
    }
    url_moradores = "/api/v1/portaria/visitantes/moradores"
    opcoes = client.get(url_moradores, headers=porteiro, params={"unidade_id": unidade})
    assert opcoes.status_code == 200, opcoes.text
    assert [item["id"] for item in opcoes.json()] == [contato["morador_id"]]
    predio.vinculo_morador.ativo = False
    session.flush()
    opcoes = client.get(url_moradores, headers=porteiro, params={"unidade_id": unidade})
    assert opcoes.status_code == 200 and opcoes.json() == []
    assert client.post(AVULSOS, headers=porteiro, json=dados).status_code == 404
    predio.vinculo_morador.ativo = True
    session.flush()
    assert client.post(AVULSOS, headers=morador, json=dados).status_code == 403
    negado = client.post(
        AVULSOS, headers=porteiro, json={**dados, "contato": {**contato, "resposta": "negou"}}
    )
    assert negado.status_code == 422
    isolado = client.post(
        AVULSOS, headers=porteiro, json={**dados, "unidade_id": str(outro.unidade_101.id)}
    )
    assert isolado.status_code == 404
    for modelo in (Visitante, RegistroVisita):
        assert session.scalar(select(func.count()).select_from(modelo)) == 0

    resposta = client.post(AVULSOS, headers=porteiro, json=dados)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["status"] == "em_andamento"
    assert resposta.json()["contato"] == contato
    assert cpf not in resposta.text
    duplicada = client.post(AVULSOS, headers=porteiro, json=dados)
    assert duplicada.status_code == 409, duplicada.text
    visitante = resposta.json()["visitante"]["id"]
    leitura = client.get(f"/api/v1/visitantes/{visitante}", headers=morador)
    assert leitura.status_code == 200, leitura.text
    assert leitura.json()["avulso"] is True and cpf not in leitura.text
    busca = client.get(
        "/api/v1/portaria/visitantes", headers=porteiro, params={"unidade_id": unidade}
    )
    assert busca.status_code == 200 and busca.json()["total"] == 0
    saida = client.post(
        f"/api/v1/visitas/{resposta.json()['id']}/saida",
        headers=porteiro,
        json={"funcionario_id": str(funcionario.id)},
    )
    assert saida.status_code == 200 and saida.json()["status"] == "encerrada"
    assert client.post(AVULSOS, headers=porteiro, json=dados).status_code == 201


def test_dois_cadastros_simultaneos_disputam_quinta_vaga(cenario: Cenario) -> None:
    predio = cenario.a
    unidade = predio.unidade_101.id
    with cenario.fabrica.begin() as sessao:
        sessao.add(
            PermissaoAba(
                condominio_id=predio.condominio.id,
                morador_unidade_id=predio.morador_unidade.id,
                aba="veiculos",
                com_acesso=True,
            )
        )
        sessao.add_all(
            Veiculo(
                condominio_id=predio.condominio.id,
                unidade_id=unidade,
                placa=f"TST1A0{numero}",
                marca="Fiat",
                modelo="Argo",
                cor="Prata",
            )
            for numero in range(4)
        )

    dados = {"unidade_id": str(unidade), "marca": "Fiat", "modelo": "Argo", "cor": "Prata"}
    morador = predio.cabecalho_de("morador")
    barreira = Barrier(2, timeout=10)
    try:
        with TestClient(create_app()) as client, ThreadPoolExecutor(max_workers=2) as pool:

            def enviar(placa):
                barreira.wait()
                return client.post(VEICULOS, headers=morador, json={**dados, "placa": placa})

            respostas = sorted(
                pool.map(enviar, ("TST1A04", "TST1A05")), key=lambda r: r.status_code
            )
        assert [resposta.status_code for resposta in respostas] == [201, 409]
        assert respostas[1].json()["error"]["reason"] == "limite_veiculos"
        with cenario.fabrica() as sessao:
            total = sessao.scalar(
                select(func.count())
                .select_from(Veiculo)
                .where(
                    Veiculo.unidade_id == unidade,
                    Veiculo.ativo.is_(True),
                )
            )
            assert total == 5
    finally:
        with cenario.fabrica.begin() as sessao:
            sessao.execute(delete(Veiculo).where(Veiculo.unidade_id == unidade))
