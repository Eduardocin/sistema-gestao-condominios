import json
from datetime import timedelta

import pytest

from app.modules.unidades.models import Unidade
from app.modules.visitantes.models import ContatoPortaria
from tests.us506.conftest import MOMENTO, ROTAS, consultar, veiculo, visita

pytestmark = pytest.mark.postgres


def test_visitas_efetivas_multiplas_avulsas_e_dados_minimos(client, session, caso):
    concluida, visitante = visita(session, caso, saida=MOMENTO + timedelta(days=2))
    repetida, _ = visita(session, caso, visitante=visitante, entrada=MOMENTO + timedelta(days=3))
    avulsa, _ = visita(session, caso, unidade=caso.a.unidade_102, avulso=True)
    # Cadastro sem entrada e contato negado não são linhas de visita.
    sem_entrada, sem_visita = visita(session, caso)
    session.delete(sem_entrada)
    session.add(
        ContatoPortaria(
            condominio_id=caso.a.condominio.id,
            visitante_id=sem_visita.id,
            unidade_id=sem_visita.unidade_id,
            funcionario_id=caso.entrada.id,
            morador_id=caso.a.morador_unidade.id,
            canal="telefone",
            resposta="negou",
        )
    )
    session.flush()
    pagina = consultar(client, caso, ROTAS[0])
    assert pagina["total"] == 3
    itens = {item["id"]: item for item in pagina["items"]}
    assert itens[str(concluida.id)]["status"] == "encerrada"
    assert itens[str(concluida.id)]["saida"]["funcionario"]["id"] == str(caso.saida.id)
    assert itens[str(repetida.id)]["status"] == "em_andamento"
    assert itens[str(repetida.id)]["saida"] is None
    assert itens[str(avulsa.id)]["avulso"] is True
    assert itens[str(concluida.id)]["avulso"] is False
    assert itens[str(concluida.id)]["visitante"] == itens[str(repetida.id)]["visitante"]
    assert itens[str(concluida.id)]["unidade"] == {
        "id": str(caso.a.unidade_101.id),
        "identificacao": caso.a.unidade_101.identificacao,
        "bloco": "Bloco histórico",
        "andar": "Primeiro",
    }
    assert itens[str(avulsa.id)]["unidade"]["bloco"] is None
    assert all(
        f'"{campo}"' not in json.dumps(pagina)
        for campo in (
            "cpf",
            "idade",
            "observacoes",
            "evidencia",
            "morador_id",
            "autorizacao",
            "contato",
        )
    )
    assert "12345678909" not in json.dumps(pagina)
    filtrada = consultar(
        client,
        caso,
        ROTAS[0],
        unidade_id=str(caso.a.unidade_101.id),
        de="2030-04-02",
        ate="2030-04-02",
    )
    assert filtrada["total"] == 1
    assert filtrada["items"][0]["id"] == str(concluida.id)
    assert filtrada["items"][0]["saida"] is not None  # Saída fora do período continua visível.


def test_visitante_cancelado_unidade_inativa_e_funcionarios_desligados(client, session, caso):
    registro, visitante = visita(session, caso, saida=MOMENTO + timedelta(hours=2))
    visitante.cancelado_em = MOMENTO + timedelta(days=1)
    visitante.nome = "Nome atual do visitante"
    caso.a.unidade_101.ativo = False
    caso.a.unidade_101.identificacao = "Identificação atual"
    for funcionario in (caso.entrada, caso.saida):
        funcionario.ativo = False
        funcionario.desligado_em = MOMENTO + timedelta(days=1)
    caso.entrada.nome = "Nome atual da entrada"
    session.flush()
    for params in ({}, {"unidade_id": str(caso.a.unidade_101.id)}):
        pagina = consultar(client, caso, ROTAS[0], **params)
        assert pagina["total"] == 1
        item = pagina["items"][0]
        assert item["id"] == str(registro.id)
        assert item["visitante"]["nome"] == visitante.nome
        assert item["unidade"]["identificacao"] == caso.a.unidade_101.identificacao
        assert item["entrada"]["funcionario"]["nome"] == caso.entrada.nome
        assert item["saida"]["funcionario"]["id"] == str(caso.saida.id)


def test_veiculos_ativos_removidos_e_unidades_inativas(client, session, caso):
    ativo = veiculo(session, caso)
    removido = veiculo(session, caso, placa="DEF2A34", removido=MOMENTO + timedelta(days=5))
    inativo = veiculo(session, caso, unidade=caso.a.unidade_102, placa="GHI3B45")
    caso.a.unidade_102.ativo = False
    ativo.modelo, ativo.cor = "Modelo atual", "Azul"
    session.flush()
    pagina = consultar(client, caso, ROTAS[1], de="2030-04-02", ate="2030-04-02")
    assert pagina["total"] == 3
    itens = {item["id"]: item for item in pagina["items"]}
    assert itens[str(ativo.id)]["ativo"] is True
    assert itens[str(ativo.id)]["modelo"] == "Modelo atual"
    assert itens[str(ativo.id)]["cor"] == "Azul"
    assert itens[str(ativo.id)]["removido_em"] is None
    assert itens[str(removido.id)]["ativo"] is False
    assert itens[str(removido.id)]["removido_em"] is not None
    assert all(item["criado_em"] is not None for item in itens.values())
    assert itens[str(ativo.id)]["unidade"]["andar"] == "Primeiro"
    historico = consultar(client, caso, ROTAS[1], unidade_id=str(caso.a.unidade_102.id))
    assert historico["total"] == 1 and historico["items"][0]["id"] == str(inativo.id)


def test_duplicidade_atual_independe_dos_filtros_e_exclui_removidos_e_unidades_inativas(
    client, session, caso
):
    primeiro = veiculo(session, caso)
    segundo = veiculo(
        session, caso, unidade=caso.a.unidade_102, criado=MOMENTO - timedelta(days=10)
    )
    removido = veiculo(session, caso, removido=MOMENTO + timedelta(days=1))
    veiculo(session, caso, predio=caso.b)  # Mesma placa no outro condomínio é irrelevante.
    unidade = Unidade(condominio_id=caso.a.condominio.id, identificacao="Inativa", ativo=False)
    session.add(unidade)
    session.flush()
    veiculo(session, caso, unidade=unidade)
    params = {"unidade_id": str(caso.a.unidade_101.id), "de": "2030-04-02", "ate": "2030-04-02"}
    pagina = consultar(client, caso, ROTAS[1], **params)
    assert pagina["total"] == 2
    assert {item["id"] for item in pagina["items"]} == {str(primeiro.id), str(removido.id)}
    assert all(item["placa_duplicada"] is True for item in pagina["items"])
    # O indicador é da placa atual, inclusive nas linhas históricas dessa placa.
    segundo.ativo = False
    segundo.removido_em = MOMENTO + timedelta(days=2)
    session.flush()
    assert all(
        item["placa_duplicada"] is False for item in consultar(client, caso, ROTAS[1])["items"]
    )
    segundo.ativo, segundo.removido_em = True, None
    caso.a.unidade_102.ativo = False
    session.flush()
    assert all(
        item["placa_duplicada"] is False for item in consultar(client, caso, ROTAS[1])["items"]
    )
    outra = client.get(ROTAS[1], headers=caso.b.cabecalho_de("administracao"))
    assert outra.status_code == 200 and outra.json()["items"][0]["placa_duplicada"] is False
