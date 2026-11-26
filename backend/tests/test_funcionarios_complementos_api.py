"""Complementos US-209: detalhe, edição e histórico limitados ao funcionário."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from tests.autorizacao.cenario import montar_predio
from tests.task29.conftest import arquivo
from tests.test_contas_funcionarios_api import funcionario, responsavel
from tests.test_contas_perfil_api import client as client
from tests.test_contas_perfil_api import session as session
from tests.test_encomendas_api import criar_encomenda

pytestmark = pytest.mark.postgres
BASE = "/api/v1/funcionarios"


@pytest.fixture
def caso(client, session):
    a, b = montar_predio(session), montar_predio(session, "Outro condomínio")
    ra, rb = responsavel(client, a), responsavel(client, b)
    ids = []
    for predio, responsavel_id in ((a, ra), (b, rb)):
        resposta = client.post(
            BASE, headers=predio.cabecalho_de("administracao"), json=funcionario(responsavel_id)
        )
        assert resposta.status_code == 201, resposta.text
        ids.append(resposta.json()["id"])
    return SimpleNamespace(
        a=a, b=b, responsavel_id=ra, outro_responsavel_id=rb, id=ids[0], outro_id=ids[1]
    )


def edicoes(session, caso):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
                RegistroAuditoria.recurso_tipo == "funcionario",
                RegistroAuditoria.recurso_id == uuid.UUID(caso.id),
                RegistroAuditoria.acao == "funcionario.editar",
            )
        )
    )


def test_detalhe_autorizado_reutiliza_resposta_do_cadastro(client, caso):
    headers = caso.a.cabecalho_de("administracao")
    resposta = client.get(f"{BASE}/{caso.id}", headers=headers)
    assert resposta.status_code == 200
    lista = client.get(BASE, headers=headers).json()["items"]
    item = next(item for item in lista if item["id"] == caso.id)
    # TASK-54: a lista mascara o telefone; o detalhe traz o número completo.
    completo = resposta.json()["telefone"]
    assert item == resposta.json() | {"telefone": "*" * (len(completo) - 4) + completo[-4:]}
    assert set(resposta.json()) == {
        "id",
        "nome",
        "funcao",
        "telefone",
        "email",
        "foto_arquivo_id",
        "ativo",
        "desligado_em",
    }


def test_edicao_normaliza_persiste_e_audita_somente_mudancas(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    antes = client.get(f"{BASE}/{caso.id}", headers=headers).json()
    foto = arquivo(session, caso.a)
    dados = funcionario(
        caso.responsavel_id,
        nome="  Nome   Editado  ",
        funcao="seguranca",
        telefone="11923456789",
        email="  PESSOA.EDITADA@EXEMPLO.TEST ",
        foto_arquivo_id=str(foto.id),
    )
    resposta = client.put(f"{BASE}/{caso.id}", headers=headers, json=dados)
    assert resposta.status_code == 200, resposta.text
    esperado = {
        "nome": "Nome Editado",
        "funcao": "seguranca",
        "telefone": "11923456789",
        "email": "pessoa.editada@exemplo.test",
        "foto_arquivo_id": str(foto.id),
    }
    assert resposta.json() == antes | esperado
    session.expire_all()
    registro = session.get(Funcionario, uuid.UUID(caso.id))
    assert registro.id == uuid.UUID(caso.id) and registro.nome == esperado["nome"]
    assert registro.foto_arquivo_id == foto.id
    [evento] = edicoes(session, caso)
    assert evento.antes == {campo: antes[campo] for campo in esperado}
    assert evento.depois == esperado
    assert evento.usuario_id == caso.a.administracao.id
    assert evento.responsavel_nome == "Síndica Fictícia"
    assert evento.perfil == "administracao"
    assert str(evento.ip) == "203.0.113.27"
    # Mesmos valores normalizados não criam um evento de alteração vazio.
    assert client.put(f"{BASE}/{caso.id}", headers=headers, json=dados).status_code == 200
    assert len(edicoes(session, caso)) == 1


def test_put_sem_foto_remove_referencia_e_nao_funciona_como_patch(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    foto = arquivo(session, caso.a)
    dados = funcionario(caso.responsavel_id, foto_arquivo_id=str(foto.id))
    assert client.put(f"{BASE}/{caso.id}", headers=headers, json=dados).status_code == 200
    del dados["foto_arquivo_id"]
    resposta = client.put(f"{BASE}/{caso.id}", headers=headers, json=dados)
    assert resposta.status_code == 200 and resposta.json()["foto_arquivo_id"] is None
    assert (
        client.put(
            f"{BASE}/{caso.id}",
            headers=headers,
            json={"nome": "Parcial", "responsavel_id": caso.responsavel_id},
        ).status_code
        == 422
    )
    registros = edicoes(session, caso)
    assert len(registros) == 2
    assert registros[-1].antes == {"foto_arquivo_id": str(foto.id)}
    assert registros[-1].depois == {"foto_arquivo_id": None}


def test_put_rejeita_campos_protegidos_e_validacao_do_cadastro(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    extras = [
        {"ativo": False},
        {"desligado_em": "2026-11-21T12:00:00Z"},
        {"condominio_id": str(caso.b.condominio.id)},
        {"id": str(uuid.uuid4())},
        {"funcao": "administrador"},
        {"email": "email-invalido"},
        {"telefone": "123"},
        {"nome": " "},
    ]
    for alteracao in extras:
        resposta = client.put(
            f"{BASE}/{caso.id}",
            headers=headers,
            json=funcionario(caso.responsavel_id, **alteracao),
        )
        assert resposta.status_code == 422, resposta.text
    assert edicoes(session, caso) == []


@pytest.mark.parametrize("tipo", ["ausente", "inativo", "outro_condominio"])
def test_edicao_exige_responsavel_valido(client, session, caso, tipo):
    dados = funcionario(caso.responsavel_id, nome="Alteração recusada")
    if tipo == "ausente":
        del dados["responsavel_id"]
    elif tipo == "inativo":
        pessoa = session.get(ResponsavelAdministracao, uuid.UUID(caso.responsavel_id))
        pessoa.ativo = False
        session.commit()
    else:
        dados["responsavel_id"] = caso.outro_responsavel_id
    resposta = client.put(
        f"{BASE}/{caso.id}", headers=caso.a.cabecalho_de("administracao"), json=dados
    )
    assert resposta.status_code == (422 if tipo == "ausente" else 404)
    session.expire_all()
    assert session.get(Funcionario, uuid.UUID(caso.id)).nome == "Porteiro Fictício"
    assert edicoes(session, caso) == []


@pytest.mark.parametrize("tipo", ["outro_condominio", "outro_autor", "outro_modulo"])
def test_edicao_reutiliza_validacao_de_fotos(client, session, caso, tipo):
    if tipo == "outro_condominio":
        foto = arquivo(session, caso.b)
    elif tipo == "outro_autor":
        foto = arquivo(session, caso.a, autor=caso.a.funcionario.id)
    else:
        foto = arquivo(session, caso.a, modulo="ocorrencias")
    resposta = client.put(
        f"{BASE}/{caso.id}",
        headers=caso.a.cabecalho_de("administracao"),
        json=funcionario(
            caso.responsavel_id, nome="Alteração recusada", foto_arquivo_id=str(foto.id)
        ),
    )
    assert resposta.status_code == 404
    session.expire_all()
    registro = session.get(Funcionario, uuid.UUID(caso.id))
    assert registro.nome == "Porteiro Fictício" and registro.foto_arquivo_id is None
    assert edicoes(session, caso) == []


def test_detalhe_edicao_e_historico_isolam_condominio_e_inexistentes(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    for id_ in (caso.outro_id, str(uuid.uuid4())):
        assert client.get(f"{BASE}/{id_}", headers=headers).status_code == 404
        assert client.get(f"{BASE}/{id_}/historico", headers=headers).status_code == 404
        assert (
            client.put(
                f"{BASE}/{id_}",
                headers=headers,
                json=funcionario(caso.responsavel_id, nome="Não deve persistir"),
            ).status_code
            == 404
        )
    session.expire_all()
    assert session.get(Funcionario, uuid.UUID(caso.outro_id)).nome == "Porteiro Fictício"
    assert edicoes(session, caso) == []


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma", None])
def test_novos_endpoints_exclusivos_da_administracao(client, session, caso, perfil):
    headers = caso.a.cabecalho_de(perfil) if perfil else {}
    esperado = 403 if perfil else 401
    assert client.get(f"{BASE}/{caso.id}", headers=headers).status_code == esperado
    assert client.get(f"{BASE}/{caso.id}/historico", headers=headers).status_code == esperado
    assert (
        client.put(
            f"{BASE}/{caso.id}", headers=headers, json=funcionario(caso.responsavel_id)
        ).status_code
        == esperado
    )
    assert edicoes(session, caso) == []


def test_novas_rotas_nao_liberam_condominio_rejeitado(client, session, caso):
    caso.a.condominio.status = "rejeitado"
    caso.a.condominio.motivo_rejeicao = "Cadastro rejeitado"
    session.commit()
    headers = caso.a.cabecalho_de("administracao")
    assert client.get(f"{BASE}/{caso.id}", headers=headers).status_code == 403
    assert client.get(f"{BASE}/{caso.id}/historico", headers=headers).status_code == 403
    assert (
        client.put(
            f"{BASE}/{caso.id}", headers=headers, json=funcionario(caso.responsavel_id)
        ).status_code
        == 403
    )


def test_desligado_pode_ser_consultado_e_editado_sem_reativar_ou_perder_registros(
    client, session, caso
):
    headers = caso.a.cabecalho_de("administracao")
    pessoa = session.get(Funcionario, uuid.UUID(caso.id))
    encomenda = criar_encomenda(session, caso.a, pessoa, descricao="Registro anterior à edição")
    session.commit()
    id_encomenda = encomenda.id
    desligamento = client.post(
        f"{BASE}/{caso.id}/desligamento",
        headers=headers,
        json={"responsavel_id": caso.responsavel_id},
    )
    assert desligamento.status_code == 200
    antes = client.get(f"{BASE}/{caso.id}", headers=headers).json()
    resposta = client.put(
        f"{BASE}/{caso.id}",
        headers=headers,
        json=funcionario(caso.responsavel_id, nome="Nome corrigido no histórico"),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["id"] == caso.id
    assert resposta.json()["ativo"] is False
    assert resposta.json()["desligado_em"] == antes["desligado_em"]
    session.expire_all()
    registro = session.get(Encomenda, id_encomenda)
    assert registro.recebido_por_funcionario_id == uuid.UUID(caso.id)
    assert registro.descricao == "Registro anterior à edição"
    assert registro.status == "aguardando_retirada"
    assert client.get(BASE, headers=caso.a.cabecalho_de("funcionario")).json()["items"] == []
    assert [
        e["acao"]
        for e in client.get(f"{BASE}/{caso.id}/historico", headers=headers).json()["items"]
    ] == ["funcionario.editar", "funcionario.desativar", "funcionario.cadastrar"]


def test_historico_paginado_expoe_somente_campos_e_eventos_permitidos(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    assert (
        client.put(
            f"{BASE}/{caso.id}",
            headers=headers,
            json=funcionario(caso.responsavel_id, nome="Nome atualizado"),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{BASE}/{caso.id}/desligamento",
            headers=headers,
            json={"responsavel_id": caso.responsavel_id},
        ).status_code
        == 200
    )
    # Registro legado permitido com metadados sensíveis e autor ausente.
    session.add(
        RegistroAuditoria(
            condominio_id=caso.a.condominio.id,
            recurso_tipo="funcionario",
            recurso_id=uuid.UUID(caso.id),
            acao="funcionario.editar",
            responsavel_nome="Responsável legado",
            antes={"senha": "SEGREDO_ANTES"},
            depois={"token": "SEGREDO_DEPOIS"},
        )
    )
    for condominio, recurso, id_, acao in (
        (caso.b.condominio.id, "funcionario", caso.id, "funcionario.editar"),
        (caso.a.condominio.id, "funcionario", caso.outro_id, "funcionario.editar"),
        (caso.a.condominio.id, "usuario", caso.id, "funcionario.editar"),
        (caso.a.condominio.id, "funcionario", caso.id, "funcionario.exportar"),
    ):
        session.add(
            RegistroAuditoria(
                condominio_id=condominio,
                recurso_tipo=recurso,
                recurso_id=uuid.UUID(id_),
                acao=acao,
            )
        )
    session.commit()
    rota = f"{BASE}/{caso.id}/historico"
    resposta = client.get(rota, headers=headers)
    assert resposta.status_code == 200, resposta.text
    pagina = resposta.json()
    assert set(pagina) == {"items", "page", "page_size", "total"}
    assert pagina["total"] == 4
    assert [e["acao"] for e in pagina["items"]] == [
        "funcionario.editar",
        "funcionario.desativar",
        "funcionario.editar",
        "funcionario.cadastrar",
    ]
    assert pagina["items"][0]["usuario"] is None
    for item in pagina["items"]:
        assert set(item) == {"acao", "criado_em", "responsavel_nome", "usuario"}
        if item["usuario"] is not None:
            assert item["usuario"] == {
                "id": str(caso.a.administracao.id),
                "nome": caso.a.administracao.nome,
            }
    assert "SEGREDO" not in resposta.text
    for page in range(1, 5):
        parcial = client.get(rota, headers=headers, params={"page": page, "page_size": 1}).json()
        assert parcial["total"] == 4 and parcial["page"] == page and parcial["page_size"] == 1
        assert parcial["items"] == [pagina["items"][page - 1]]
    assert (
        client.get(rota, headers=headers, params={"page": 5, "page_size": 1}).json()["items"] == []
    )
    assert client.get(rota, headers=headers, params={"page": 0}).status_code == 422
    assert client.get(rota, headers=headers, params={"page_size": 101}).status_code == 422
    assert client.get("/api/v1/plataforma/auditoria", headers=headers).status_code == 403


def test_historico_vazio_de_funcionario_existente(client, session, caso):
    pessoa = Funcionario(
        condominio_id=caso.a.condominio.id, nome="Legado sem eventos", funcao="porteiro"
    )
    session.add(pessoa)
    session.commit()
    resposta = client.get(
        f"{BASE}/{pessoa.id}/historico", headers=caso.a.cabecalho_de("administracao")
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


@pytest.mark.parametrize("falha", ["auditoria", "commit"])
def test_falha_reverte_edicao_e_evento(client, session, caso, monkeypatch, falha):
    if falha == "auditoria":
        original = auditoria.registrar_acao

        def falhar(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("Falha controlada após o flush da auditoria")

        monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    else:

        def falhar_commit():
            raise RuntimeError("Falha controlada antes do commit")

        monkeypatch.setattr(session, "commit", falhar_commit)
    resposta = client.put(
        f"{BASE}/{caso.id}",
        headers=caso.a.cabecalho_de("administracao"),
        json=funcionario(caso.responsavel_id, nome="Nome que deve ser revertido"),
    )
    assert resposta.status_code == 500
    session.expire_all()
    assert session.get(Funcionario, uuid.UUID(caso.id)).nome == "Porteiro Fictício"
    assert edicoes(session, caso) == []
