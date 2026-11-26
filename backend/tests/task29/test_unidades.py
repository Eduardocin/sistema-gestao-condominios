import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.unidades import service
from app.modules.unidades.models import ChaveAcesso, ProprietarioUnidade
from tests.isolamento.cenario import cabecalho, token_de
from tests.task29.conftest import arquivo

pytestmark = pytest.mark.postgres
BASE = "/api/v1/unidades"


def rota(caso, acao=""):
    return f"{BASE}/{caso.a.unidade_101.id}{acao}"


def responsavel(caso):
    return {"responsavel_id": str(caso.responsavel.id)}


def proprietario(caso, **campos):
    return {
        "nome": " Maria Souza ",
        "documento": "52998224725",
        "emails": [" MARIA@EXEMPLO.TEST ", "maria.trabalho@exemplo.test"],
        "whatsapps": ["81988887777", "81999998888"],
        "telefone": "8133334444",
        "foto_arquivo_id": None,
        **responsavel(caso),
        **campos,
    }


def test_ciclo_de_chaves_sem_codigo_na_auditoria(client, session, caso, caplog):
    headers = caso.a.cabecalho_de("administracao")
    assert client.get(rota(caso, "/chave"), headers=headers).status_code == 404
    assert client.get(rota(caso), headers=headers).json()["chave"] is None
    gerada = client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso))
    assert gerada.status_code == 201, gerada.text
    assert gerada.headers["Location"] == rota(caso, "/chave")
    primeira = gerada.json()["codigo"]
    assert len(primeira) == 11 and primeira[5] == "-"
    assert client.get(rota(caso, "/chave"), headers=headers).json() == gerada.json()
    assert client.get(rota(caso), headers=headers).json()["chave"] == gerada.json()
    assert (
        client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso)).status_code
        == 409
    )
    nova = client.post(rota(caso, "/chave/regeneracao"), headers=headers, json=responsavel(caso))
    assert nova.status_code == 200 and nova.json()["codigo"] != primeira
    segunda = nova.json()["codigo"]
    antiga = session.scalars(
        select(ChaveAcesso).where(ChaveAcesso.codigo == primeira.replace("-", ""))
    ).one()
    assert antiga.revogada_em is not None
    vigente = session.scalars(
        select(ChaveAcesso).where(
            ChaveAcesso.unidade_id == caso.a.unidade_101.id, ChaveAcesso.revogada_em.is_(None)
        )
    ).one()
    assert vigente.codigo == segunda.replace("-", "")
    resposta = client.post(rota(caso, "/chave/revogacao"), headers=headers, json=responsavel(caso))
    assert resposta.status_code == 200 and resposta.json()["revogada_em"]
    assert client.get(rota(caso, "/chave"), headers=headers).status_code == 404
    assert (
        client.post(
            rota(caso, "/chave/revogacao"), headers=headers, json=responsavel(caso)
        ).status_code
        == 409
    )
    assert (
        client.post(
            rota(caso, "/chave/regeneracao"), headers=headers, json=responsavel(caso)
        ).status_code
        == 409
    )
    eventos = list(
        session.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
                RegistroAuditoria.acao.like("chave.%"),
            )
            .order_by(RegistroAuditoria.id)
        )
    )
    assert [e.acao for e in eventos] == ["chave.gerar", "chave.regenerar", "chave.revogar"]
    for evento in eventos:
        assert (
            evento.responsavel_nome == caso.responsavel.nome
            and evento.usuario_id == caso.a.administracao.id
        )
        assert evento.recurso_id == caso.a.unidade_101.id
        for codigo in (primeira, segunda, primeira.replace("-", ""), segunda.replace("-", "")):
            assert codigo not in json.dumps([evento.antes, evento.depois])
            assert codigo not in caplog.text
    assert (
        client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso)).status_code
        == 201
    )


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma"])
@pytest.mark.parametrize(
    "acao", ["lista", "detalhe", "proprietario", "consulta", "gerar", "regenerar", "revogar"]
)
def test_perfis_nao_autorizados(client, caso, perfil, acao):
    headers = caso.a.cabecalho_de(perfil)
    if acao == "lista":
        resposta = client.get(BASE, headers=headers)
    elif acao == "detalhe":
        resposta = client.get(rota(caso), headers=headers)
    elif acao == "proprietario":
        resposta = client.put(rota(caso, "/proprietario"), headers=headers, json=proprietario(caso))
    elif acao == "consulta":
        resposta = client.get(rota(caso, "/chave"), headers=headers)
    else:
        caminho = {
            "gerar": "/chave",
            "regenerar": "/chave/regeneracao",
            "revogar": "/chave/revogacao",
        }[acao]
        resposta = client.post(rota(caso, caminho), headers=headers, json=responsavel(caso))
    assert resposta.status_code == 403
    assert "codigo" not in resposta.text


@pytest.mark.parametrize("estado", ["pendente", "rejeitado", "desativado"])
def test_condominio_inativo_nao_acessa_operacoes(client, session, caso, estado):
    caso.a.condominio.status = estado
    caso.a.condominio.motivo_rejeicao = "Motivo" if estado == "rejeitado" else None
    session.commit()
    headers = caso.a.cabecalho_de("administracao")
    assert client.get(BASE, headers=headers).status_code == 403
    assert client.get(rota(caso), headers=headers).status_code == 403
    assert client.get(rota(caso, "/chave"), headers=headers).status_code == 403
    assert (
        client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso)).status_code
        == 403
    )
    assert (
        client.put(
            rota(caso, "/proprietario"), headers=headers, json=proprietario(caso)
        ).status_code
        == 403
    )


@pytest.mark.parametrize("acao", ["/chave", "/chave/regeneracao", "/chave/revogacao"])
def test_unidade_inativa_nao_tem_chave(client, session, caso, acao):
    caso.a.unidade_101.ativo = False
    session.commit()
    headers = caso.a.cabecalho_de("administracao")
    assert client.post(rota(caso, acao), headers=headers, json=responsavel(caso)).status_code == 409
    assert client.get(rota(caso, "/chave"), headers=headers).status_code == 404
    assert client.get(rota(caso), headers=headers).json()["chave"] is None


def test_isolamento_unidade_chave_e_proprietario(client, caso):
    headers = caso.b.cabecalho_de("administracao")
    dados = {"responsavel_id": str(caso.outro.id)}
    for sufixo in ("", "/chave"):
        assert client.get(rota(caso, sufixo), headers=headers).status_code == 404
    for sufixo in ("/chave", "/chave/regeneracao", "/chave/revogacao"):
        assert client.post(rota(caso, sufixo), headers=headers, json=dados).status_code == 404
    assert (
        client.put(
            rota(caso, "/proprietario"), headers=headers, json=proprietario(caso, **dados)
        ).status_code
        == 404
    )
    lista = client.get(BASE, headers=headers).json()
    assert lista["total"] == 2
    assert str(caso.a.unidade_101.id) not in json.dumps(lista)


@pytest.mark.parametrize("tipo", ["ausente", "outro", "inativo"])
def test_responsavel_obrigatorio_e_validado(client, session, caso, tipo):
    dados = (
        {}
        if tipo == "ausente"
        else {"responsavel_id": str(caso.outro.id if tipo == "outro" else caso.responsavel.id)}
    )
    if tipo == "inativo":
        caso.responsavel.ativo = False
        session.commit()
    headers = caso.a.cabecalho_de("administracao")
    assert client.post(rota(caso, "/chave"), headers=headers, json=dados).status_code == (
        422 if tipo == "ausente" else 404
    )
    corpo = proprietario(caso)
    corpo.pop("responsavel_id")
    assert client.put(
        rota(caso, "/proprietario"), headers=headers, json={**corpo, **dados}
    ).status_code == (422 if tipo == "ausente" else 404)


def test_colisoes_globais_inclusive_revogadas_e_limite_de_cinco(
    client, session, caso, monkeypatch, caplog
):
    headers = caso.a.cabecalho_de("administracao")
    codigo = "ABCDEFGHJK"
    session.add(
        ChaveAcesso(
            condominio_id=caso.b.condominio.id,
            unidade_id=caso.b.unidade_101.id,
            codigo=codigo,
            criada_em=datetime(2026, 11, 1, tzinfo=UTC),
            revogada_em=datetime(2026, 11, 2, tzinfo=UTC),
        )
    )
    session.commit()
    codigos = iter([codigo, "MNPQRSTUVW"])
    monkeypatch.setattr(service, "gerar_codigo", lambda: next(codigos))
    resposta = client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso))
    assert resposta.status_code == 201 and resposta.json()["codigo"] == "MNPQR-STUVW"
    chamadas = []

    def colidir():
        chamadas.append(1)
        return codigo

    monkeypatch.setattr(service, "gerar_codigo", colidir)
    falha = client.post(rota(caso, "/chave/regeneracao"), headers=headers, json=responsavel(caso))
    assert falha.status_code == 503 and len(chamadas) == 5
    assert client.get(rota(caso, "/chave"), headers=headers).json() == resposta.json()
    assert codigo not in caplog.text and codigo not in falha.text


@pytest.mark.parametrize("documento", ["52998224725", "11222333000181"])
def test_cadastrar_editar_proprietario_e_auditar_sem_dados_sensiveis(
    client, session, caso, documento
):
    headers = caso.a.cabecalho_de("administracao")
    foto = arquivo(session, caso.a)
    dados = proprietario(caso, documento=documento, foto_arquivo_id=str(foto.id))
    resposta = client.put(rota(caso, "/proprietario"), headers=headers, json=dados)
    assert resposta.status_code == 200, resposta.text
    saida = resposta.json()
    assert saida["nome"] == "Maria Souza" and saida["documento"] == documento
    assert saida["emails"][0] == "maria@exemplo.test" and saida["foto_arquivo_id"] == str(foto.id)
    assert client.get(rota(caso), headers=headers).json()["proprietario"] == saida
    editada = client.put(
        rota(caso, "/proprietario"),
        headers=headers,
        json=proprietario(caso, nome="Maria Silva", emails=[], whatsapps=[], telefone=None),
    )
    assert editada.status_code == 200 and editada.json()["nome"] == "Maria Silva"
    assert editada.json()["foto_arquivo_id"] is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(ProprietarioUnidade)
            .where(ProprietarioUnidade.unidade_id == caso.a.unidade_101.id)
        )
        == 1
    )
    eventos = list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
                RegistroAuditoria.acao == "proprietario.editar",
            )
        )
    )
    assert len(eventos) == 2
    for evento in eventos:
        assert evento.responsavel_nome == caso.responsavel.nome
        texto = json.dumps([evento.antes, evento.depois])
        assert documento not in texto and "52998224725" not in texto and "***" in texto
        assert "@" not in texto and "81988887777" not in texto


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("documento", "52998224726"),
        ("documento", "11222333000182"),
        ("documento", "11111111111"),
        ("documento", "123"),
        ("nome", " "),
        ("emails", ["invalido"]),
        ("emails", ["a@b.test"] * 3),
        ("whatsapps", ["81 98888-7777"]),
        ("whatsapps", ["81988887777"] * 3),
        ("telefone", "123"),
        ("condominio_id", str(uuid.uuid4())),
        ("unidade_id", str(uuid.uuid4())),
        ("id", str(uuid.uuid4())),
        ("perfil", "plataforma"),
        ("codigo", "ABCDEFGHJK"),
    ],
)
def test_proprietario_rejeita_entrada_invalida_e_campos_protegidos(client, caso, campo, valor):
    resposta = client.put(
        rota(caso, "/proprietario"),
        headers=caso.a.cabecalho_de("administracao"),
        json=proprietario(caso, **{campo: valor}),
    )
    assert resposta.status_code == 422


@pytest.mark.parametrize(
    "tipo", ["outro_condominio", "outro_autor", "nao_imagem", "outro_modulo", "inexistente"]
)
def test_foto_validada_por_escopo_e_storage(client, session, caso, tipo):
    if tipo == "inexistente":
        id_ = uuid.uuid4()
    else:
        foto = arquivo(
            session,
            caso.b if tipo == "outro_condominio" else caso.a,
            autor=caso.a.funcionario.id if tipo == "outro_autor" else None,
            mime="application/pdf" if tipo == "nao_imagem" else "image/png",
            modulo="ocorrencias" if tipo == "outro_modulo" else "fotos",
        )
        id_ = foto.id
    resposta = client.put(
        rota(caso, "/proprietario"),
        headers=caso.a.cabecalho_de("administracao"),
        json=proprietario(caso, foto_arquivo_id=str(id_)),
    )
    assert resposta.status_code == 404


def test_lista_filtros_e_paginacao(client, session, caso):
    headers = caso.a.cabecalho_de("administracao")
    assert (
        client.put(
            rota(caso, "/proprietario"), headers=headers, json=proprietario(caso)
        ).status_code
        == 200
    )
    pagina = client.get(BASE, headers=headers, params={"page_size": 1}).json()
    assert pagina["total"] == 2 and len(pagina["items"]) == 1
    for filtros, total in [
        ({"sem_proprietario": True}, 1),
        ({"sem_proprietario": False}, 1),
        ({"bloco_id": str(caso.bloco.id)}, 2),
        ({"andar_id": str(caso.andar.id)}, 2),
        ({"andar_id": str(uuid.uuid4())}, 0),
        ({"busca": "101"}, 1),
        ({"busca": "%"}, 0),
        ({"ativo": False}, 0),
        ({"page": 2, "page_size": 1}, 2),
    ]:
        resposta = client.get(BASE, headers=headers, params=filtros)
        assert resposta.status_code == 200 and resposta.json()["total"] == total
    caso.a.unidade_102.ativo = False
    session.commit()
    assert client.get(BASE, headers=headers).json()["total"] == 1
    assert client.get(BASE, headers=headers, params={"ativo": False}).json()["total"] == 1


@pytest.mark.parametrize("operacao", ["gerar", "regenerar", "revogar", "proprietario"])
def test_falha_auditoria_reverte_escritas(client, session, caso, monkeypatch, operacao):
    headers = caso.a.cabecalho_de("administracao")
    if operacao in {"regenerar", "revogar"}:
        assert (
            client.post(rota(caso, "/chave"), headers=headers, json=responsavel(caso)).status_code
            == 201
        )
    original = auditoria.registrar_acao

    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Falha simulada na auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    if operacao == "proprietario":
        resposta = client.put(rota(caso, "/proprietario"), headers=headers, json=proprietario(caso))
    else:
        sufixo = {
            "gerar": "/chave",
            "regenerar": "/chave/regeneracao",
            "revogar": "/chave/revogacao",
        }[operacao]
        resposta = client.post(rota(caso, sufixo), headers=headers, json=responsavel(caso))
    assert resposta.status_code == 500
    assert (
        session.scalar(
            select(func.count())
            .select_from(ProprietarioUnidade)
            .where(ProprietarioUnidade.unidade_id == caso.a.unidade_101.id)
        )
        == 0
    )
    chaves = list(
        session.scalars(select(ChaveAcesso).where(ChaveAcesso.unidade_id == caso.a.unidade_101.id))
    )
    assert len(chaves) == (1 if operacao in {"regenerar", "revogar"} else 0)
    assert all(c.revogada_em is None for c in chaves)


def test_vinculo_e_perfil_lidos_do_banco(client, session, caso):
    headers = cabecalho(token_de(caso.a.morador, caso.a.condominio.id, perfil="administracao"))
    assert client.get(BASE, headers=headers).status_code == 403
    caso.a.vinculo_morador.perfil = "administracao"
    session.commit()
    assert client.get(BASE, headers=headers).status_code == 200
    caso.a.vinculo_morador.ativo = False
    session.commit()
    assert client.get(BASE, headers=headers).status_code == 403


def test_foto_do_proprietario_respeita_politica_de_download(client, session, caso):
    from app.modules.storage.router import get_storage_adapter
    from tests.isolamento.cenario import criar_usuario, vincular

    client.app.dependency_overrides[get_storage_adapter] = lambda: SimpleNamespace(
        sign=lambda key, seconds: f"https://storage.exemplo.test/{key}?expires={seconds}"
    )
    foto = arquivo(session, caso.a)
    headers = caso.a.cabecalho_de("administracao")
    assert (
        client.put(
            rota(caso, "/proprietario"),
            headers=headers,
            json=proprietario(caso, foto_arquivo_id=str(foto.id)),
        ).status_code
        == 200
    )
    download = f"/api/v1/arquivos/{foto.id}/download"
    assert client.get(download, headers=headers).status_code == 200
    for perfil in ("morador", "funcionario", "plataforma"):
        assert client.get(download, headers=caso.a.cabecalho_de(perfil)).status_code == 404
    assert client.get(download, headers=caso.b.cabecalho_de("administracao")).status_code == 404
    outra_conta = criar_usuario(session)
    vincular(session, outra_conta, caso.a.condominio, perfil="administracao")
    session.commit()
    assert (
        client.get(
            download, headers=cabecalho(token_de(outra_conta, caso.a.condominio.id))
        ).status_code
        == 200
    )


def test_lista_de_unidades_ordena_por_bloco_andar_e_identificacao(client, session, caso):
    """O "101" do bloco A vem antes do do bloco B, mesmo criado depois; legadas ficam por último."""
    from app.modules.unidades.models import Andar, Bloco, Unidade

    condominio_id = caso.a.condominio.id
    bloco_b = Bloco(condominio_id=condominio_id, nome="Bloco B")
    session.add(bloco_b)
    session.flush()
    terreo_b = Andar(condominio_id=condominio_id, bloco_id=bloco_b.id, nome="Térreo", ordem=0)
    alto_b = Andar(condominio_id=condominio_id, bloco_id=bloco_b.id, nome="1º", ordem=1)
    alto_a = Andar(condominio_id=condominio_id, bloco_id=caso.bloco.id, nome="1º", ordem=1)
    session.add_all([terreo_b, alto_b, alto_a])
    session.flush()
    # Inseridas de propósito fora de ordem: antes da correção o desempate era o UUID.
    novas = [
        Unidade(condominio_id=condominio_id, andar_id=alto_b.id, identificacao="201"),
        Unidade(condominio_id=condominio_id, andar_id=terreo_b.id, identificacao="101"),
        Unidade(condominio_id=condominio_id, andar_id=alto_a.id, identificacao="201"),
    ]
    session.add_all(novas)
    session.commit()
    resposta = client.get(BASE, headers=caso.a.cabecalho_de("administracao"))
    assert resposta.status_code == 200, resposta.text
    por_id = {str(u.id): u for u in [caso.a.unidade_101, caso.a.unidade_102, *novas]}
    nomes = [
        (
            por_id[item["id"]].andar_id,
            por_id[item["id"]].identificacao,
        )
        for item in resposta.json()["items"]
    ]
    assert nomes == [
        (caso.andar.id, "Bloco A / 101"),
        (caso.andar.id, "Bloco A / 102"),
        (alto_a.id, "201"),
        (terreo_b.id, "101"),
        (alto_b.id, "201"),
    ]
