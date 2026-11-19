"""TASK-28: cadastro completo e listagem do vínculo, em PostgreSQL migrado."""

import copy
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios import repository
from app.modules.condominios.models import Condominio, CondominioAnalise, VinculoCondominio
from app.modules.unidades.models import Andar, Bloco, ChaveAcesso, Unidade
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import montar_predio
from tests.isolamento.cenario import cabecalho, token_de
from tests.test_contas_perfil_api import cadastrar as cadastrar_conta
from tests.test_contas_perfil_api import client as cliente_postgres
from tests.test_contas_perfil_api import session as sessao_postgres

client = cliente_postgres
session = sessao_postgres
pytestmark = pytest.mark.postgres
BASE = "/api/v1/condominios"
CNPJ = "11222333000181"
OUTRO_CNPJ = "11444777000161"


def corpo(**campos):
    return {
        "nome": "Residencial Aurora",
        "cnpj": CNPJ,
        "endereco": {
            "cep": "50030230",
            "logradouro": "Rua da Aurora",
            "numero": "100",
            "complemento": None,
            "bairro": "Boa Vista",
            "cidade": "Recife",
            "uf": "pe",
        },
        "logo_arquivo_id": None,
        "documentos": [],
        "blocos": [
            {
                "nome": "Bloco A",
                "andares": [
                    {"nome": "Térreo", "ordem": 0, "unidades": ["Loja A", "9-B"]},
                    {"nome": "Cobertura", "ordem": 200, "unidades": ["Cob/7"]},
                ],
            },
            {
                "nome": "Torre B",
                "andares": [
                    {"nome": "Térreo", "ordem": 0, "unidades": ["Loja A", "301", "901"]},
                ],
            },
        ],
        **campos,
    }


def totais(session):
    return {
        modelo.__tablename__: session.scalar(select(func.count()).select_from(modelo))
        for modelo in (
            Usuario,
            Condominio,
            Bloco,
            Andar,
            Unidade,
            VinculoCondominio,
            CondominioAnalise,
            RegistroAuditoria,
            ChaveAcesso,
        )
    }


def test_cadastro_completo_pendente_e_auditoria(client, session):
    headers, conta, _ = cadastrar_conta(client, "administracao")
    usuario_id = uuid.UUID(conta["usuario"]["id"])
    usuarios_antes = session.scalar(select(func.count()).select_from(Usuario))
    resposta = client.post(BASE, headers=headers, json=corpo())
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert resposta.headers["Location"] == f"{BASE}/meus"
    assert dados == {
        "id": dados["id"],
        "nome": "Residencial Aurora",
        "cnpj": CNPJ,
        "status": "pendente",
        "enviado_em": dados["enviado_em"],
        "estrutura": {"blocos": 2, "andares": 3, "unidades": 6},
    }
    id_ = uuid.UUID(dados["id"])
    condominio = session.get(Condominio, id_)
    assert condominio.status == "pendente" and condominio.aprovado_em is None
    assert condominio.criado_por_usuario_id == usuario_id and condominio.enviado_em is not None
    assert (
        condominio.cep,
        condominio.logradouro,
        condominio.numero,
        condominio.bairro,
        condominio.cidade,
        condominio.uf,
    ) == ("50030230", "Rua da Aurora", "100", "Boa Vista", "Recife", "PE")
    linhas = session.execute(
        select(
            Bloco.nome,
            Andar.nome,
            Andar.ordem,
            Unidade.identificacao,
            Bloco.ativo,
            Andar.ativo,
            Unidade.ativo,
        )
        .join(Andar, Andar.bloco_id == Bloco.id)
        .join(Unidade, Unidade.andar_id == Andar.id)
        .where(Bloco.condominio_id == id_)
    ).all()
    esperado = {
        (b["nome"], a["nome"], a["ordem"], u, True, True, True)
        for b in corpo()["blocos"]
        for a in b["andares"]
        for u in a["unidades"]
    }
    assert set(linhas) == esperado
    vinculo = session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.condominio_id == id_)
    ).one()
    assert vinculo.usuario_id == usuario_id and vinculo.perfil == "administracao" and vinculo.ativo
    assert vinculo.unidade_id is None
    analise = session.scalars(
        select(CondominioAnalise).where(CondominioAnalise.condominio_id == id_)
    ).one()
    assert analise.evento == "enviado" and analise.usuario_id == usuario_id
    assert analise.criado_em == condominio.enviado_em and analise.motivo is None
    evento = session.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.condominio_id == id_)
    ).one()
    assert evento.acao == "condominio.enviar" and evento.recurso_tipo == "condominio"
    assert evento.recurso_id == id_ and evento.usuario_id == usuario_id
    assert evento.perfil is None and evento.responsavel_nome is None
    assert str(evento.ip) == "203.0.113.27"
    assert evento.antes == {} and evento.depois == {
        "status": "pendente",
        "estrutura": dados["estrutura"],
    }
    assert CNPJ not in json.dumps(evento.depois)
    assert (
        session.scalar(
            select(func.count()).select_from(ChaveAcesso).where(ChaveAcesso.condominio_id == id_)
        )
        == 0
    )
    assert session.scalar(select(func.count()).select_from(Usuario)) == usuarios_antes
    # O service confirmou tudo, inclusive os filhos, em uma transação só.
    session.rollback()
    assert session.get(Condominio, id_) is not None


@pytest.mark.parametrize(
    "caminho,valor",
    [
        (("nome",), " "),
        (("nome",), "ab"),
        (("nome",), "a" * 121),
        (("cnpj",), "52998224725"),
        (("cnpj",), "11222333000182"),
        (("cnpj",), "11111111111111"),
        (("cnpj",), "11.222.333/0001-81"),
        (("endereco",), {}),
        (("endereco", "cep"), "1234567"),
        (("endereco", "cep"), "12345-678"),
        (("endereco", "logradouro"), " "),
        (("endereco", "logradouro"), "a" * 151),
        (("endereco", "numero"), ""),
        (("endereco", "numero"), "a" * 21),
        (("endereco", "bairro"), ""),
        (("endereco", "cidade"), "a" * 81),
        (("endereco", "uf"), "Pernambuco"),
        (("endereco", "complemento"), "a" * 81),
        (("blocos",), []),
        (("blocos", 0, "nome"), ""),
        (("blocos", 0, "nome"), "a" * 51),
        (("blocos", 0, "andares"), []),
        (("blocos", 0, "andares", 0, "nome"), ""),
        (("blocos", 0, "andares", 0, "nome"), "a" * 51),
        (("blocos", 0, "andares", 0, "ordem"), -1),
        (("blocos", 0, "andares", 0, "ordem"), 201),
        (("blocos", 0, "andares", 0, "ordem"), True),
        (("blocos", 0, "andares", 0, "ordem"), "1"),
        (("blocos", 0, "andares", 0, "unidades"), []),
        (("blocos", 0, "andares", 0, "unidades"), ["101", " 101 "]),
        (("blocos", 0, "andares", 0, "unidades"), ["A_1"]),
        (("blocos", 0, "andares", 0, "unidades"), ["a" * 21]),
        (("blocos", 0, "andares", 0, "unidades"), [" "]),
        (("blocos", 0, "andares", 0, "unidades"), [str(i) for i in range(61)]),
        (
            ("blocos", 0, "andares"),
            [{"nome": str(i), "ordem": i, "unidades": ["1"]} for i in range(101)],
        ),
        (
            ("blocos",),
            [
                {"nome": str(i), "andares": [{"nome": "1", "ordem": 1, "unidades": ["1"]}]}
                for i in range(21)
            ],
        ),
        (("blocos", 1, "nome"), " Bloco A "),
        (("blocos", 0, "andares", 1, "nome"), " Térreo "),
        (("criado_por_usuario_id",), str(uuid.uuid4())),
        (("condominio_id",), str(uuid.uuid4())),
        (("status",), "ativo"),
        (("id",), str(uuid.uuid4())),
        (("blocos", 0, "id"), str(uuid.uuid4())),
        (("blocos", 0, "andares", 0, "condominio_id"), str(uuid.uuid4())),
        (("logo_arquivo_id",), str(uuid.uuid4())),
        (("documentos",), [str(uuid.uuid4())]),
        (("documentos",), [str(uuid.uuid4()) for _ in range(6)]),
    ],
)
def test_rejeita_estrutura_invalida_sem_persistir(client, session, caminho, valor):
    headers, _, _ = cadastrar_conta(client, "administracao")
    dados = corpo()
    item = dados
    for parte in caminho[:-1]:
        item = item[parte]
    item[caminho[-1]] = copy.deepcopy(valor)
    antes = totais(session)
    resposta = client.post(BASE, headers=headers, json=dados)
    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["error"]["code"] == "validation_error"
    assert totais(session) == antes


def test_detalhes_apontam_campo_sem_ecoar_entrada(client):
    headers, _, _ = cadastrar_conta(client, "administracao")
    dados = corpo()
    segredo = "SEGREDO_DO_CLIENTE" * 5
    dados["blocos"][0]["andares"][0]["unidades"][1] = segredo
    dados[segredo] = segredo
    resposta = client.post(BASE, headers=headers, json=dados)
    assert resposta.status_code == 422 and segredo not in resposta.text
    assert "blocos[0].andares[0].unidades[1]" in {
        erro["campo"] for erro in resposta.json()["error"]["details"]
    }


def test_limite_total_2000_e_estrutura_maxima(client, session):
    headers, _, _ = cadastrar_conta(client, "administracao")
    dados = corpo(
        blocos=[
            {
                "nome": f"Bloco {b}",
                "andares": [{"nome": str(a), "ordem": a, "unidades": ["1"]} for a in range(100)],
            }
            for b in range(20)
        ]
    )
    dados["blocos"][0]["andares"][0]["unidades"].append("2")
    assert client.post(BASE, headers=headers, json=dados).status_code == 422
    dados["blocos"][0]["andares"][0]["unidades"].pop()
    resposta = client.post(BASE, headers=headers, json=dados)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["estrutura"] == {"blocos": 20, "andares": 2000, "unidades": 2000}


def test_cnpj_duplicado_usa_constraint_sem_criacao_parcial(client, session):
    headers, _, _ = cadastrar_conta(client, "administracao")
    assert client.post(BASE, headers=headers, json=corpo()).status_code == 201
    antes = totais(session)
    resposta = client.post(BASE, headers=headers, json=corpo(nome="Outro prédio"))
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "cnpj_ja_cadastrado"
    assert totais(session) == antes


def test_multiplos_condominios_listagem_e_bloqueio_operacional(client, session):
    headers, conta, _ = cadastrar_conta(client, "administracao")
    respostas = [
        client.post(BASE, headers=headers, json=corpo()),
        client.post(BASE, headers=headers, json=corpo(nome="Outro prédio", cnpj=OUTRO_CNPJ)),
    ]
    assert all(r.status_code == 201 for r in respostas)
    ids = [r.json()["id"] for r in respostas]
    assert client.get(f"{BASE}/meus", headers=headers).json() == [
        {"id": ids[1], "nome": "Outro prédio", "status": "pendente", "perfil": "administracao"},
        {
            "id": ids[0],
            "nome": "Residencial Aurora",
            "status": "pendente",
            "perfil": "administracao",
        },
    ]
    selecao = client.post(
        "/api/v1/auth/selecionar-condominio", headers=headers, json={"condominio_id": ids[0]}
    )
    assert selecao.status_code == 200
    selecionado = {"Authorization": f"Bearer {selecao.json()['access_token']}"}
    for rota in ("/api/v1/avisos", "/api/v1/reservas", "/api/v1/areas-comuns"):
        assert client.get(rota, headers=selecionado).status_code == 403
    assert client.get(f"{BASE}/meus", headers=selecionado).status_code == 200
    vinculo = session.scalars(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == uuid.UUID(conta["usuario"]["id"]),
            VinculoCondominio.condominio_id == uuid.UUID(ids[0]),
        )
    ).one()
    vinculo.ativo = False
    session.commit()
    assert [p["id"] for p in client.get(f"{BASE}/meus", headers=headers).json()] == [ids[1]]


@pytest.mark.parametrize("status", ["pendente", "ativo", "rejeitado", "desativado"])
def test_listagem_isola_vinculos_e_inclui_todos_status(client, session, status):
    headers, _, _ = cadastrar_conta(client, "administracao")
    meus = client.post(BASE, headers=headers, json=corpo()).json()
    outro_headers, _, _ = cadastrar_conta(
        client, "administracao", telefone="11987654322", documento="11222333000181"
    )
    outro = client.post(BASE, headers=outro_headers, json=corpo(cnpj=OUTRO_CNPJ)).json()
    condominio = session.get(Condominio, uuid.UUID(meus["id"]))
    condominio.status = status
    if status == "rejeitado":
        condominio.motivo_rejeicao = "Ajustar cadastro"
    session.commit()
    resultado = client.get(
        f"{BASE}/meus",
        headers={**headers, "X-Condominio-Id": outro["id"]},
        params={"usuario_id": outro["id"], "condominio_id": outro["id"]},
    ).json()
    assert resultado == [
        {"id": meus["id"], "nome": meus["nome"], "status": status, "perfil": "administracao"}
    ]


@pytest.mark.parametrize("perfil", [None, "morador", "funcionario", "administracao", "plataforma"])
def test_so_cadastro_de_administracao_acessa_as_rotas(client, session, perfil):
    predio = montar_predio(session)
    predio.morador.tipo_cadastro = "morador"
    session.commit()
    headers = predio.cabecalho_de(perfil) if perfil else {}
    # A Administração legada/compartilhada sem tipo de cadastro não cria prédios.
    esperado = 403 if perfil else 401
    assert client.post(BASE, headers=headers, json=corpo()).status_code == esperado
    assert client.get(f"{BASE}/meus", headers=headers).status_code == esperado
    if perfil == "morador":
        forjado = cabecalho(token_de(predio.morador, predio.condominio.id, perfil="administracao"))
        assert client.post(BASE, headers=forjado, json=corpo()).status_code == 403


@pytest.mark.parametrize("etapa", ["estrutura", "vinculo", "historico", "auditoria", "commit"])
def test_falha_reverte_todo_cadastro(client, session, monkeypatch, etapa):
    headers, _, _ = cadastrar_conta(client, "administracao")
    antes = totais(session)
    alvo, nome = {
        "estrutura": (repository, "criar_estrutura"),
        "vinculo": (repository, "vincular_criador"),
        "historico": (repository, "registrar_envio"),
        "auditoria": (auditoria, "registrar_acao"),
        "commit": (session, "commit"),
    }[etapa]
    original = getattr(alvo, nome)

    def falhar(*args, **kwargs):
        if etapa != "commit":
            original(*args, **kwargs)
        raise RuntimeError("Falha controlada durante o cadastro")

    with monkeypatch.context() as patch:
        patch.setattr(alvo, nome, falhar)
        resposta = client.post(BASE, headers=headers, json=corpo())
    assert resposta.status_code == 500
    assert totais(session) == antes
    # O rollback também liberou o CNPJ para uma tentativa válida.
    assert client.post(BASE, headers=headers, json=corpo()).status_code == 201
