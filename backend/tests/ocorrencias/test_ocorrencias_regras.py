"""Ocorrências: abertura, anexos, listas, respostas, resolução, auditoria e concorrência."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo, OcorrenciaInteracao
from tests.ocorrencias.cenario import (
    corpo,
    criar_arquivo,
    criar_interacao,
    criar_ocorrencia,
    resolucao,
    resposta,
)
from tests.reservas.cenario import criar_responsavel

URL = "/api/v1/ocorrencias"
T1 = datetime(2030, 6, 10, 12, tzinfo=UTC)
T2 = datetime(2030, 6, 11, 12, tzinfo=UTC)
T3 = datetime(2030, 6, 12, 12, tzinfo=UTC)


@pytest.fixture
def morador(predio):
    return predio.cabecalho_de(Perfil.MORADOR)


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


@pytest.fixture
def responsavel(session, predio):
    return criar_responsavel(session, predio)


def erro(resposta_http):
    return resposta_http.json()["error"]


def eventos(session, predio, acao):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == predio.condominio.id,
                RegistroAuditoria.acao == acao,
            )
        )
    )


# --- abertura ---------------------------------------------------------------------------------


def test_criar_devolve_201_location_e_objeto(client, predio, morador):
    resposta_http = client.post(URL, headers=morador, json=corpo(predio))
    assert resposta_http.status_code == 201, resposta_http.text
    dados = resposta_http.json()
    assert dados["unidade"] == {
        "id": str(predio.unidade_101.id),
        "identificacao": "Bloco A / 101",
    }
    assert dados["titulo"] == "Vazamento na garagem"
    assert dados["status"] == "em_aberto"
    assert dados["aberta_por"] == {"id": str(predio.morador.id), "nome": predio.morador.nome}
    assert dados["resolvida_em"] is None
    assert dados["anexos"] == []
    assert dados["interacoes"] == []
    assert "criada_em" in dados
    assert resposta_http.headers["Location"] == f"{URL}/{dados['id']}"


def test_criar_com_anexo_de_imagem(client, session, predio, morador):
    arquivo = criar_arquivo(session, predio)
    resposta_http = client.post(URL, headers=morador, json=corpo(predio, anexos=[str(arquivo.id)]))
    assert resposta_http.status_code == 201, resposta_http.text
    assert resposta_http.json()["anexos"] == [{"arquivo_id": str(arquivo.id), "interacao_id": None}]
    assert (
        session.scalar(select(OcorrenciaAnexo).where(OcorrenciaAnexo.arquivo_id == arquivo.id))
        is not None
    )


def test_criar_com_video_mp4_aceito(client, session, predio, morador):
    arquivo = criar_arquivo(session, predio, usuario=predio.morador, tipo_mime="video/mp4")
    resposta_http = client.post(URL, headers=morador, json=corpo(predio, anexos=[str(arquivo.id)]))
    assert resposta_http.status_code == 201, resposta_http.text


@pytest.mark.parametrize(
    "campo",
    ["unidade_id", "titulo", "detalhe"],
)
def test_obrigatorios_sao_422(client, predio, morador, campo):
    dados = corpo(predio)
    dados.pop(campo)
    assert client.post(URL, headers=morador, json=dados).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [
        {"titulo": "   "},
        {"detalhe": "x" * 4001},
        {"titulo": "x" * 121},
        {"condominio_id": str(uuid.uuid4())},
        {"usuario_id": str(uuid.uuid4())},
        {"anexos": [str(uuid.uuid4()) for _ in range(6)]},
    ],
)
def test_formato_invalido_e_422(client, predio, morador, extra):
    resposta_http = client.post(URL, headers=morador, json=corpo(predio, **extra))
    assert resposta_http.status_code == 422, resposta_http.text
    assert erro(resposta_http)["code"] == "validation_error"
    assert "reason" not in erro(resposta_http)


def test_anexo_repetido_e_422(client, session, predio, morador):
    arquivo = criar_arquivo(session, predio)
    ids = [str(arquivo.id), str(arquivo.id)]
    resposta_http = client.post(URL, headers=morador, json=corpo(predio, anexos=ids))
    assert resposta_http.status_code == 422


@pytest.mark.parametrize(
    "montar",
    [
        "de_outro_usuario",
        "de_outro_modulo",
        "inexistente",
        "de_outro_condominio",
        "tipo_invalido",
    ],
)
def test_anexo_invalido_e_422(client, session, predio, morador, montar):
    if montar == "de_outro_usuario":
        arquivo = criar_arquivo(session, predio, usuario=predio.administracao)
    elif montar == "de_outro_modulo":
        arquivo = criar_arquivo(session, predio, modulo="fotos")
    elif montar == "de_outro_condominio":
        arquivo = criar_arquivo(session, predio, de_condominio=False)
    elif montar == "tipo_invalido":
        arquivo = criar_arquivo(session, predio, tipo_mime="application/pdf")
    else:
        arquivo = None
    anexos = [str(uuid.uuid4())] if arquivo is None else [str(arquivo.id)]
    resposta_http = client.post(URL, headers=morador, json=corpo(predio, anexos=anexos))
    assert resposta_http.status_code == 422, resposta_http.text


# --- listas -----------------------------------------------------------------------------------


def test_morador_ve_apenas_a_unidade_informada_e_filtra_status(client, session, predio, morador):
    aberta = criar_ocorrencia(session, predio, criado_em=T1)
    resolvida = criar_ocorrencia(session, predio, status="resolvida", criado_em=T2, resolvida_em=T2)
    criar_ocorrencia(session, predio, unidade=predio.unidade_102, criado_em=T3)

    resposta_http = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador)
    assert resposta_http.status_code == 200, resposta_http.text
    dados = resposta_http.json()
    assert dados["total"] == 2
    assert [item["id"] for item in dados["items"]] == [str(resolvida.id), str(aberta.id)]

    so_resolvidas = client.get(
        f"{URL}?unidade_id={predio.unidade_101.id}&status=resolvida", headers=morador
    ).json()
    assert [item["id"] for item in so_resolvidas["items"]] == [str(resolvida.id)]

    sem_unidade = client.get(URL, headers=morador)
    assert sem_unidade.status_code == 422
    assert erro(sem_unidade)["code"] == "validation_error"


def test_administracao_ve_o_condominio_e_filtra(client, session, predio, adm):
    da_101 = criar_ocorrencia(session, predio, criado_em=T1)
    da_102 = criar_ocorrencia(
        session, predio, unidade=predio.unidade_102, status="resolvida", criado_em=T2
    )
    da_101_resolvida = criar_ocorrencia(
        session,
        predio,
        status="resolvida",
        criado_em=T3,
        resolvida_em=T3,
    )

    todas = client.get(URL, headers=adm).json()
    assert todas["total"] == 3
    assert [item["id"] for item in todas["items"]] == [
        str(da_101_resolvida.id),
        str(da_102.id),
        str(da_101.id),
    ]

    por_unidade = client.get(f"{URL}?unidade_id={predio.unidade_102.id}", headers=adm).json()
    assert [item["id"] for item in por_unidade["items"]] == [str(da_102.id)]

    por_periodo = client.get(f"{URL}?de=2030-06-11&ate=2030-06-11", headers=adm).json()
    assert [item["id"] for item in por_periodo["items"]] == [str(da_102.id)]

    por_status = client.get(f"{URL}?status=resolvida", headers=adm).json()
    assert {item["id"] for item in por_status["items"]} == {
        str(da_102.id),
        str(da_101_resolvida.id),
    }


def test_lista_traz_ultima_interacao_e_aguardando(client, session, predio, morador, responsavel):
    sem_resposta = criar_ocorrencia(session, predio, titulo="Sem resposta", criado_em=T1)
    respondida = criar_ocorrencia(session, predio, titulo="Respondida", criado_em=T1)
    criar_interacao(
        session,
        predio,
        respondida,
        responsavel=responsavel,
        criado_em=T2,
    )
    com_comentario = criar_ocorrencia(session, predio, titulo="Com comentário", criado_em=T1)
    criar_interacao(session, predio, com_comentario, responsavel=responsavel, criado_em=T2)
    criar_interacao(
        session,
        predio,
        com_comentario,
        tipo="comentario",
        texto="O vazamento continua.",
        usuario=predio.morador,
        criado_em=T3,
    )

    dados = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador).json()
    por_id = {item["id"]: item for item in dados["items"]}

    assert por_id[str(sem_resposta.id)]["ultima_interacao_em"] is None
    assert por_id[str(sem_resposta.id)]["aguardando_administracao"] is True
    assert datetime.fromisoformat(por_id[str(respondida.id)]["ultima_interacao_em"]) == T2
    assert por_id[str(respondida.id)]["aguardando_administracao"] is False
    assert datetime.fromisoformat(por_id[str(com_comentario.id)]["ultima_interacao_em"]) == T3
    assert por_id[str(com_comentario.id)]["aguardando_administracao"] is True


# --- respostas --------------------------------------------------------------------------------


def test_responder_devolve_201_e_aparece_no_detalhe(
    client, session, predio, morador, adm, responsavel
):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta_http = client.post(
        f"{URL}/{ocorrencia.id}/respostas",
        headers=adm,
        json=resposta(responsavel.id),
    )
    assert resposta_http.status_code == 201, resposta_http.text
    dados = resposta_http.json()
    assert dados["tipo"] == "resposta"
    assert dados["texto"] == "Equipe de manutenção acionada."
    assert dados["autor"] == {"tipo": "administracao", "nome": responsavel.nome}
    assert dados["anexos"] == []
    assert "em" in dados

    detalhe = client.get(f"{URL}/{ocorrencia.id}", headers=morador).json()
    assert detalhe["status"] == "em_aberto"
    assert detalhe["interacoes"] == [
        {
            "id": dados["id"],
            "tipo": "resposta",
            "texto": dados["texto"],
            "autor": dados["autor"],
            "em": dados["em"],
            "anexos": [],
        }
    ]

    [linha] = session.scalars(
        select(OcorrenciaInteracao).where(OcorrenciaInteracao.ocorrencia_id == ocorrencia.id)
    ).all()
    assert linha.usuario_id == predio.administracao.id
    assert linha.responsavel_id == responsavel.id


def test_responder_sem_responsavel_ou_com_responsavel_invalido(
    client, session, predio, adm, outro_predio
):
    ocorrencia = criar_ocorrencia(session, predio)
    url = f"{URL}/{ocorrencia.id}/respostas"

    sem_responsavel = client.post(url, headers=adm, json={"texto": "Oi"})
    assert sem_responsavel.status_code == 422

    inativo = criar_responsavel(session, predio, ativo=False)
    assert client.post(url, headers=adm, json=resposta(inativo.id)).status_code == 404

    de_outro = criar_responsavel(session, outro_predio)
    assert client.post(url, headers=adm, json=resposta(de_outro.id)).status_code == 404

    texto_vazio = client.post(
        url, headers=adm, json={"texto": "   ", "responsavel_id": str(inativo.id)}
    )
    assert texto_vazio.status_code == 422


# --- resolução --------------------------------------------------------------------------------


def test_resolver_devolve_200_interacao_e_auditoria(
    client, session, predio, morador, adm, responsavel
):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta_http = client.post(
        f"{URL}/{ocorrencia.id}/resolucao",
        headers=adm,
        json=resolucao(responsavel.id),
    )
    assert resposta_http.status_code == 200, resposta_http.text
    dados = resposta_http.json()
    assert dados["status"] == "resolvida"
    assert dados["resolvida_em"] is not None
    assert dados["interacoes"][-1]["tipo"] == "resolucao"
    assert dados["interacoes"][-1]["texto"] == "Vazamento corrigido."
    assert dados["interacoes"][-1]["autor"] == {
        "tipo": "administracao",
        "nome": responsavel.nome,
    }

    como_morador = client.get(f"{URL}/{ocorrencia.id}", headers=morador).json()
    assert como_morador["status"] == "resolvida"
    assert como_morador["resolvida_em"] == dados["resolvida_em"]

    [evento] = eventos(session, predio, "ocorrencia.resolver")
    assert evento.recurso_id == ocorrencia.id
    assert evento.usuario_id == predio.administracao.id
    assert evento.responsavel_nome == responsavel.nome
    assert evento.antes == {"status": "em_aberto"}
    assert evento.depois == {"status": "resolvida"}


def test_resolver_sem_texto(client, session, predio, adm, responsavel):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta_http = client.post(
        f"{URL}/{ocorrencia.id}/resolucao",
        headers=adm,
        json=resolucao(responsavel.id, texto=None),
    )
    assert resposta_http.status_code == 200, resposta_http.text
    assert resposta_http.json()["interacoes"][-1]["texto"] is None


def test_resolver_duas_vezes_e_409(client, session, predio, adm, responsavel):
    ocorrencia = criar_ocorrencia(session, predio)
    url = f"{URL}/{ocorrencia.id}/resolucao"
    assert client.post(url, headers=adm, json=resolucao(responsavel.id)).status_code == 200
    resolvida_em = client.get(f"{URL}/{ocorrencia.id}", headers=adm).json()["resolvida_em"]

    segunda = client.post(url, headers=adm, json=resolucao(responsavel.id))
    assert segunda.status_code == 409
    assert erro(segunda)["reason"] == "ocorrencia_ja_resolvida"
    assert client.get(f"{URL}/{ocorrencia.id}", headers=adm).json()["resolvida_em"] == resolvida_em

    resolucoes = session.scalars(
        select(OcorrenciaInteracao).where(
            OcorrenciaInteracao.ocorrencia_id == ocorrencia.id,
            OcorrenciaInteracao.tipo == "resolucao",
        )
    ).all()
    assert len(resolucoes) == 1


def test_resolver_responsavel_invalido_nao_altera(client, session, predio, adm, outro_predio):
    ocorrencia = criar_ocorrencia(session, predio)
    de_outro = criar_responsavel(session, outro_predio)
    resposta_http = client.post(
        f"{URL}/{ocorrencia.id}/resolucao", headers=adm, json=resolucao(de_outro.id)
    )
    assert resposta_http.status_code == 404
    session.refresh(ocorrencia)
    assert ocorrencia.status == "em_aberto"
    assert ocorrencia.resolvida_em is None


def test_resolver_ocorrencia_ja_resolvida_e_409(client, session, predio, adm, responsavel):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    resposta_http = client.post(
        f"{URL}/{ocorrencia.id}/resolucao", headers=adm, json=resolucao(responsavel.id)
    )
    assert resposta_http.status_code == 409
    assert erro(resposta_http)["reason"] == "ocorrencia_ja_resolvida"


def test_ocorrencia_nao_e_apagada(client, session, predio, morador, adm, responsavel):
    ocorrencia = criar_ocorrencia(session, predio)
    client.post(f"{URL}/{ocorrencia.id}/resolucao", headers=adm, json=resolucao(responsavel.id))
    assert client.get(f"{URL}/{ocorrencia.id}", headers=morador).status_code == 200
    assert client.delete(f"{URL}/{ocorrencia.id}", headers=morador).status_code == 405
    assert session.get(Ocorrencia, ocorrencia.id) is not None
