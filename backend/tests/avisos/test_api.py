import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.avisos.models import Aviso
from app.modules.avisos.service import publicar_para_unidade
from app.modules.unidades.models import MoradorUnidade
from tests.autorizacao.cenario import Predio
from tests.reservas.cenario import AGORA, criar_responsavel

pytestmark = pytest.mark.postgres
BASE = "/api/v1/avisos"


def corpo(responsavel_id: uuid.UUID, /, **campos: Any) -> dict[str, Any]:
    return {
        "titulo": "Abastecimento de água",
        "texto": "O abastecimento será interrompido para manutenção.",
        "inicio_em": (AGORA - timedelta(hours=1)).isoformat(),
        "fim_em": (AGORA + timedelta(days=2)).isoformat(),
        "importante": False,
        "responsavel_id": str(responsavel_id),
        **campos,
    }


def contexto(predio: Predio, perfil: str = "administracao") -> ContextoCondominio:
    usuario = predio.administracao if perfil == "administracao" else predio.morador
    return ContextoCondominio(usuario.id, predio.condominio.id, perfil, uuid.uuid4())


def criar(session: Session, predio: Predio, **campos: Any) -> Aviso:
    valores = corpo(criar_responsavel(session, predio).id)
    valores["inicio_em"] = AGORA - timedelta(hours=1)
    valores["fim_em"] = AGORA + timedelta(days=2)
    valores["responsavel_id"] = uuid.UUID(valores["responsavel_id"])
    valores.update(campos)
    aviso = Aviso(condominio_id=predio.condominio.id, **valores)
    session.add(aviso)
    # Preserva o cenário quando a dependência real reverte uma requisição negada.
    session.commit()
    return aviso


def test_publicar_contrato_e_auditoria(client: TestClient, session: Session, predio: Predio):
    responsavel = criar_responsavel(session, predio)
    resposta = client.post(
        BASE,
        headers=predio.cabecalho_de("administracao"),
        json=corpo(responsavel.id, titulo="  Manutenção  ", importante=True),
    )
    assert resposta.status_code == 201, resposta.text
    aviso = resposta.json()
    assert resposta.headers["Location"] == f"{BASE}/{aviso['id']}"
    assert aviso == {
        "id": aviso["id"],
        "titulo": "Manutenção",
        "texto": corpo(responsavel.id)["texto"],
        "importante": True,
        "inicio_em": aviso["inicio_em"],
        "fim_em": aviso["fim_em"],
        "encerrado_em": None,
        "situacao": "vigente",
        "unidade": None,
        "publicado_por": {"id": str(responsavel.id), "nome": responsavel.nome},
    }
    registro = session.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.recurso_id == uuid.UUID(aviso["id"]))
    ).one()
    assert registro.acao == "aviso.publicar"
    assert registro.usuario_id == predio.administracao.id
    assert registro.condominio_id == predio.condominio.id
    assert registro.responsavel_nome == responsavel.nome
    assert registro.perfil == "administracao"
    assert registro.recurso_tipo == "aviso"
    assert registro.antes == {}
    assert registro.depois is not None
    assert registro.depois["titulo"] == "Manutenção"
    assert registro.depois["responsavel_id"] == str(responsavel.id)


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "plataforma"])
@pytest.mark.parametrize("operacao", ["publicar", "editar", "encerrar"])
def test_escrita_exige_administracao(client, session, predio, perfil, operacao):
    aviso = criar(session, predio)
    headers = predio.cabecalho_de(perfil)
    dados = corpo(aviso.responsavel_id)
    if operacao == "publicar":
        resposta = client.post(BASE, headers=headers, json=dados)
    elif operacao == "editar":
        resposta = client.put(f"{BASE}/{aviso.id}", headers=headers, json=dados)
    else:
        resposta = client.post(
            f"{BASE}/{aviso.id}/encerramento",
            headers=headers,
            json={"responsavel_id": str(aviso.responsavel_id)},
        )
    assert resposta.status_code == 403


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("titulo", ""),
        ("titulo", "   "),
        ("titulo", "x" * 121),
        ("texto", ""),
        ("texto", " \n "),
        ("texto", "x" * 2001),
        ("inicio_em", "sem-data"),
        ("inicio_em", "2030-06-10T12:00:00"),
        ("fim_em", "2030-06-12T12:00:00"),
        ("fim_em", (AGORA - timedelta(hours=1)).isoformat()),
        ("fim_em", (AGORA - timedelta(days=2)).isoformat()),
        ("unidade_id", str(uuid.uuid4())),
        ("condominio_id", str(uuid.uuid4())),
        ("usuario_id", str(uuid.uuid4())),
        ("perfil", "administracao"),
        ("encerrado_em", AGORA.isoformat()),
        ("responsavel_id", None),
    ],
)
@pytest.mark.parametrize("metodo", ["post", "put"])
def test_validacao_da_entrada(client, session, predio, campo, valor, metodo):
    aviso = criar(session, predio)
    dados = corpo(aviso.responsavel_id, **{campo: valor})
    url = BASE if metodo == "post" else f"{BASE}/{aviso.id}"
    resposta = getattr(client, metodo)(
        url, headers=predio.cabecalho_de("administracao"), json=dados
    )
    assert resposta.status_code == 422


@pytest.mark.parametrize("operacao", ["publicar", "editar", "encerrar"])
@pytest.mark.parametrize("tipo", ["ausente", "inexistente", "inativo", "outro_condominio"])
def test_responsavel_obrigatorio_ativo_e_do_condominio(
    client, session, predio, outro_predio, operacao, tipo
):
    aviso = criar(session, predio)
    if tipo == "inativo":
        rid = criar_responsavel(session, predio, ativo=False).id
    elif tipo == "outro_condominio":
        rid = criar_responsavel(session, outro_predio).id
    else:
        rid = uuid.uuid4()
    dados = corpo(rid) if operacao != "encerrar" else {"responsavel_id": str(rid)}
    if tipo == "ausente":
        dados.pop("responsavel_id")
    session.commit()
    headers = predio.cabecalho_de("administracao")
    if operacao == "publicar":
        resposta = client.post(BASE, headers=headers, json=dados)
    elif operacao == "editar":
        resposta = client.put(f"{BASE}/{aviso.id}", headers=headers, json=dados)
    else:
        resposta = client.post(f"{BASE}/{aviso.id}/encerramento", headers=headers, json=dados)
    assert resposta.status_code == (422 if tipo == "ausente" else 404)
    assert session.get(Aviso, aviso.id).encerrado_em is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(Aviso)
            .where(Aviso.condominio_id == predio.condominio.id)
        )
        == 1
    )


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "administracao"])
def test_vigencia_limites_ordenacao_e_alias(client, session, predio, relogio, perfil):
    comum = criar(session, predio, inicio_em=AGORA)
    importante = criar(session, predio, importante=True, inicio_em=AGORA - timedelta(days=1))
    recente = criar(session, predio, importante=True, inicio_em=AGORA)
    agendado = criar(session, predio, inicio_em=AGORA + timedelta(microseconds=1))
    expirado = criar(session, predio, inicio_em=AGORA - timedelta(days=1), fim_em=AGORA)
    encerrado = criar(session, predio, encerrado_em=AGORA)
    headers = predio.cabecalho_de(perfil)
    resposta = client.get(BASE, headers=headers)
    assert resposta.status_code == 200, resposta.text
    assert [item["id"] for item in resposta.json()["items"]] == [
        str(recente.id),
        str(importante.id),
        str(comum.id),
    ]
    assert resposta.json()["total"] == 3
    assert client.get(f"{BASE}/vigentes", headers=headers).json() == resposta.json()
    for aviso in (agendado, expirado, encerrado):
        detalhe = client.get(f"{BASE}/{aviso.id}", headers=headers)
        assert detalhe.status_code == (200 if perfil == "administracao" else 404)
    for item in resposta.json()["items"]:
        assert ("publicado_por" in item) == (perfil == "administracao")
    if perfil != "administracao":
        assert (
            client.get(BASE, headers=headers, params={"situacao": "todos"}).json()
            == resposta.json()
        )
    relogio.momento = AGORA + timedelta(days=3)
    assert client.get(BASE, headers=headers).json()["items"] == []


def test_filtros_administrativos_e_paginacao(client, session, predio):
    vigente = criar(session, predio)
    agendado = criar(session, predio, inicio_em=AGORA + timedelta(days=1))
    expirado = criar(session, predio, inicio_em=AGORA - timedelta(days=1), fim_em=AGORA)
    encerrado = criar(session, predio, encerrado_em=AGORA)
    headers = predio.cabecalho_de("administracao")
    for filtro, esperados in [
        ("vigentes", [vigente]),
        ("agendados", [agendado]),
        ("encerrados", [expirado, encerrado]),
    ]:
        resultado = client.get(BASE, headers=headers, params={"situacao": filtro}).json()
        assert {item["id"] for item in resultado["items"]} == {str(a.id) for a in esperados}
    ids = []
    for pagina in range(1, 6):
        resposta = client.get(
            BASE, headers=headers, params={"situacao": "todos", "page": pagina, "page_size": 1}
        )
        assert resposta.status_code == 200
        dados = resposta.json()
        assert dados["total"] == 4
        assert dados["page"] == pagina and dados["page_size"] == 1
        ids.extend(item["id"] for item in dados["items"])
    assert len(ids) == len(set(ids)) == 4
    for params in [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"situacao": "expirados"}]:
        assert client.get(BASE, headers=headers, params=params).status_code == 422


@pytest.mark.parametrize("perfil", ["morador", "funcionario", "administracao"])
def test_isolamento_de_condominio(client, session, predio, outro_predio, perfil):
    meu = criar(session, predio)
    alheio = criar(session, outro_predio)
    headers = predio.cabecalho_de(perfil)
    resposta = client.get(
        BASE,
        headers={**headers, "X-Condominio-Id": str(outro_predio.condominio.id)},
        params={"condominio_id": str(outro_predio.condominio.id)},
    )
    assert [item["id"] for item in resposta.json()["items"]] == [str(meu.id)]
    assert client.get(f"{BASE}/{alheio.id}", headers=headers).status_code == 404
    if perfil == "administracao":
        assert (
            client.put(
                f"{BASE}/{alheio.id}", headers=headers, json=corpo(meu.responsavel_id)
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"{BASE}/{alheio.id}/encerramento",
                headers=headers,
                json={"responsavel_id": str(meu.responsavel_id)},
            ).status_code
            == 404
        )


def test_publico_unidades_e_revogacao_imediata(client, session, predio):
    geral = criar(session, predio)
    minha = criar(session, predio, unidade_id=predio.unidade_101.id)
    outra = criar(session, predio, unidade_id=predio.unidade_102.id)
    for perfil, ids in [
        ("morador", [geral.id, minha.id]),
        ("funcionario", [geral.id]),
        ("administracao", [geral.id, minha.id, outra.id]),
    ]:
        headers = predio.cabecalho_de(perfil)
        dados = client.get(BASE, headers=headers).json()
        assert {item["id"] for item in dados["items"]} == {str(id_) for id_ in ids}
        assert dados["total"] == len(ids)
        for aviso in [geral, minha, outra]:
            assert client.get(f"{BASE}/{aviso.id}", headers=headers).status_code == (
                200 if aviso.id in ids else 404
            )
    # Várias unidades usam os vínculos atuais; não o campo legado do vínculo de condomínio.
    vinculo = MoradorUnidade(
        condominio_id=predio.condominio.id,
        usuario_id=predio.morador.id,
        unidade_id=predio.unidade_102.id,
        origem="cadastro",
    )
    session.add(vinculo)
    session.commit()
    headers = predio.cabecalho_de("morador")
    assert client.get(f"{BASE}/{outra.id}", headers=headers).status_code == 200
    predio.morador_unidade.status = "desvinculado"
    predio.morador_unidade.desvinculado_em = AGORA
    session.commit()
    assert client.get(f"{BASE}/{minha.id}", headers=headers).status_code == 404
    assert client.get(f"{BASE}/{outra.id}", headers=headers).status_code == 200


def test_edicao_encerramento_preservam_autor_e_historico(client, session, predio):
    aviso = criar(session, predio)
    autor = aviso.responsavel_id
    editor = criar_responsavel(session, predio, "Outra responsável")
    headers = predio.cabecalho_de("administracao")
    resposta = client.put(
        f"{BASE}/{aviso.id}",
        headers=headers,
        json=corpo(editor.id, titulo="Novo título", importante=True),
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["publicado_por"]["id"] == str(autor)
    resposta = client.post(
        f"{BASE}/{aviso.id}/encerramento", headers=headers, json={"responsavel_id": str(editor.id)}
    )
    assert resposta.status_code == 200
    assert resposta.json()["situacao"] == "encerrado"
    session.expire_all()
    persistido = session.get(Aviso, aviso.id)
    assert persistido.titulo == "Novo título"
    assert persistido.responsavel_id == autor
    assert persistido.encerrado_em == AGORA
    assert client.get(BASE, headers=headers).json()["items"] == []
    assert client.get(f"{BASE}/{aviso.id}", headers=headers).status_code == 200
    registros = list(
        session.scalars(
            select(RegistroAuditoria)
            .where(RegistroAuditoria.recurso_id == aviso.id)
            .order_by(RegistroAuditoria.id)
        )
    )
    assert [r.acao for r in registros] == ["aviso.editar", "aviso.encerrar"]
    assert all(r.responsavel_nome == editor.nome for r in registros)
    assert registros[0].antes == {"titulo": "Abastecimento de água", "importante": False}
    assert registros[0].depois == {"titulo": "Novo título", "importante": True}
    assert registros[1].antes == {"encerrado_em": None}
    assert datetime.fromisoformat(registros[1].depois["encerrado_em"]) == AGORA


@pytest.mark.parametrize("estado", ["expirado", "encerrado"])
def test_nao_altera_aviso_finalizado(client, session, predio, estado):
    campos = {"encerrado_em": AGORA} if estado == "encerrado" else {"fim_em": AGORA}
    aviso = criar(session, predio, **campos)
    headers = predio.cabecalho_de("administracao")
    respostas = [
        client.put(f"{BASE}/{aviso.id}", headers=headers, json=corpo(aviso.responsavel_id)),
        client.post(
            f"{BASE}/{aviso.id}/encerramento",
            headers=headers,
            json={"responsavel_id": str(aviso.responsavel_id)},
        ),
    ]
    for resposta in respostas:
        assert resposta.status_code == 409
        assert resposta.json()["error"]["reason"] == "aviso_encerrado"
    assert session.get(Aviso, aviso.id) is not None


def test_automatico_nao_editavel_mas_pode_encerrar(client, session, predio):
    aviso = criar(session, predio, unidade_id=predio.unidade_101.id)
    headers = predio.cabecalho_de("administracao")
    resposta = client.put(f"{BASE}/{aviso.id}", headers=headers, json=corpo(aviso.responsavel_id))
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "aviso_automatico"
    assert (
        client.post(
            f"{BASE}/{aviso.id}/encerramento",
            headers=headers,
            json={"responsavel_id": str(aviso.responsavel_id)},
        ).status_code
        == 200
    )


def test_funcao_interna_valida_unidade_e_nao_commita(session, predio, outro_predio):
    responsavel = criar_responsavel(session, predio)
    session.commit()
    id_ = publicar_para_unidade(
        session,
        ctx=contexto(predio),
        unidade_id=predio.unidade_101.id,
        titulo="Automático",
        texto="Cancelamento",
        responsavel_id=responsavel.id,
        relogio=lambda: AGORA,
    )
    aviso = session.get(Aviso, id_)
    assert aviso.importante is True
    assert aviso.inicio_em == AGORA
    assert aviso.fim_em == AGORA + timedelta(days=7)
    session.rollback()
    assert session.get(Aviso, id_) is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.recurso_id == id_)
        )
        == 0
    )
    with pytest.raises(RecursoNaoEncontrado):
        publicar_para_unidade(
            session,
            ctx=contexto(predio),
            unidade_id=outro_predio.unidade_101.id,
            titulo="Outro prédio",
            texto="Texto",
            responsavel_id=responsavel.id,
        )
    with pytest.raises(ApiError) as erro:
        publicar_para_unidade(
            session,
            ctx=contexto(predio, "morador"),
            unidade_id=predio.unidade_101.id,
            titulo="Inválido",
            texto="Texto",
            responsavel_id=responsavel.id,
        )
    assert erro.value.status_code == 403


@pytest.mark.parametrize("operacao", ["publicar", "editar", "encerrar"])
def test_falha_de_auditoria_reverte_acao(client, session, predio, monkeypatch, operacao):
    aviso = criar(session, predio)
    id_ = aviso.id
    rid = aviso.responsavel_id
    headers = predio.cabecalho_de("administracao")
    session.commit()
    registrar = auditoria.registrar_acao

    def falhar(*args, **kwargs):
        registrar(*args, **kwargs)
        raise RuntimeError("Falha simulada após a auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    if operacao == "publicar":
        resposta = client.post(BASE, headers=headers, json=corpo(rid))
    elif operacao == "editar":
        resposta = client.put(f"{BASE}/{id_}", headers=headers, json=corpo(rid, titulo="Alterado"))
    else:
        resposta = client.post(
            f"{BASE}/{id_}/encerramento", headers=headers, json={"responsavel_id": str(rid)}
        )
    assert resposta.status_code == 500
    session.expire_all()
    assert session.get(Aviso, id_).titulo == "Abastecimento de água"
    assert session.get(Aviso, id_).encerrado_em is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(Aviso)
            .where(Aviso.condominio_id == predio.condominio.id)
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.condominio_id == predio.condominio.id)
        )
        == 0
    )


def test_autenticacao_e_adm_na_leitura(client, session, predio):
    aviso = criar(session, predio)
    for url in [BASE, f"{BASE}/vigentes", f"{BASE}/{aviso.id}"]:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=predio.cabecalho_de("plataforma")).status_code == 403
    assert client.post(BASE, json={}).status_code == 401
