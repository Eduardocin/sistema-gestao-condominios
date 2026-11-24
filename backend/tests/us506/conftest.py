from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import Andar, Bloco
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from tests.autorizacao.cenario import montar_predio
from tests.autorizacao.conftest import session as session
from tests.test_contas_funcionarios_api import client as client

ROTAS = ("/api/v1/relatorios/visitantes", "/api/v1/relatorios/veiculos")
MOMENTO = datetime(2030, 4, 2, 12, tzinfo=UTC)


@pytest.fixture
def caso(session):
    a, b = montar_predio(session, "Relatórios A"), montar_predio(session, "Relatórios B")
    bloco = Bloco(condominio_id=a.condominio.id, nome="Bloco histórico")
    session.add(bloco)
    session.flush()
    andar = Andar(condominio_id=a.condominio.id, bloco_id=bloco.id, nome="Primeiro", ordem=1)
    session.add(andar)
    session.flush()
    a.unidade_101.andar_id = andar.id
    entrada = Funcionario(condominio_id=a.condominio.id, nome="Entrada", funcao="porteiro")
    saida = Funcionario(condominio_id=a.condominio.id, nome="Saída", funcao="seguranca")
    externo = Funcionario(condominio_id=b.condominio.id, nome="Externo", funcao="porteiro")
    session.add_all([entrada, saida, externo])
    session.commit()
    return SimpleNamespace(a=a, b=b, entrada=entrada, saida=saida, externo=externo)


def visita(
    session,
    caso,
    *,
    predio=None,
    unidade=None,
    entrada=MOMENTO,
    saida=None,
    visitante=None,
    avulso=False,
):
    predio = predio or caso.a
    if visitante is None:
        visitante = Visitante(
            condominio_id=predio.condominio.id,
            unidade_id=(unidade or predio.unidade_101).id,
            nome="Visitante do relatório",
            cpf="12345678909",
            idade=35,
            observacoes="Informação pessoal que não deve sair",
            entrada_prevista=date(2029, 1, 1),
            saida_prevista=date(2029, 1, 2),
            cadastrado_por_usuario_id=predio.morador.id,
            avulso=avulso,
        )
        session.add(visitante)
        session.flush()
    funcionario = caso.entrada if predio is caso.a else caso.externo
    funcionario_saida = caso.saida if predio is caso.a else caso.externo
    item = RegistroVisita(
        condominio_id=predio.condominio.id,
        visitante_id=visitante.id,
        entrada_em=entrada,
        entrada_por_funcionario_id=funcionario.id,
        saida_em=saida,
        saida_por_funcionario_id=funcionario_saida.id if saida is not None else None,
        evidencia={
            "contato": {
                "morador_id": str(predio.morador_unidade.id),
                "canal": "interfone",
                "resposta": "autorizou",
            }
        },
    )
    session.add(item)
    session.flush()
    return item, visitante


def veiculo(
    session,
    caso,
    *,
    predio=None,
    unidade=None,
    criado=MOMENTO,
    placa="ABC1D23",
    removido=None,
):
    predio = predio or caso.a
    item = Veiculo(
        condominio_id=predio.condominio.id,
        unidade_id=(unidade or predio.unidade_101).id,
        placa=placa,
        marca="Fiat",
        modelo="Argo",
        cor="Prata",
        criado_em=criado,
        ativo=removido is None,
        removido_em=removido,
    )
    session.add(item)
    session.flush()
    return item


def consultar(client, caso, rota, **params):
    resposta = client.get(rota, headers=caso.a.cabecalho_de("administracao"), params=params)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()
