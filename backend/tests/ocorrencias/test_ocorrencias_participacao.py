"""Ocorrências: comentário e reabertura pelo Morador (US-704)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo, OcorrenciaInteracao
from tests.ocorrencias.cenario import criar_arquivo, criar_interacao, criar_ocorrencia
from tests.reservas.cenario import criar_responsavel, definir_aba

URL = "/api/v1/ocorrencias"
# Interação já existente antes do pedido: anterior ao now() das requisições do teste.
ANTES = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.fixture
def morador(predio):
    return predio.cabecalho_de(Perfil.MORADOR)


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


def erro(resposta):
    return resposta.json()["error"]


def eventos(session, predio, acao):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == predio.condominio.id,
                RegistroAuditoria.acao == acao,
            )
        )
    )


# --- matriz de perfis -------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
@pytest.mark.parametrize(
    ("perfil", "esperado"),
    [
        (Perfil.MORADOR, 200),
        (Perfil.FUNCIONARIO, 403),
        (Perfil.ADMINISTRACAO, 403),
        (Perfil.PLATAFORMA, 403),
    ],
)
def test_matriz_por_perfil(client, session, predio, rota, perfil, esperado):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/{rota}",
        headers=predio.cabecalho_de(perfil),
        json={"texto": "Voltou a vazar."},
    )
    # O comentário devolve 201; a reabertura, 200.
    esperado_da_rota = 201 if (rota == "comentarios" and esperado == 200) else esperado
    assert resposta.status_code == esperado_da_rota, resposta.text
    if resposta.status_code == 403:
        assert erro(resposta)["code"] == "forbidden"


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
def test_403_de_perfil_vem_antes_de_422_e_404(client, predio, rota):
    resposta = client.post(
        f"{URL}/{uuid.uuid4()}/{rota}",
        headers=predio.cabecalho_de(Perfil.ADMINISTRACAO),
        json={"x": 1},
    )
    assert resposta.status_code == 403


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
def test_sem_token_e_401(client, session, predio, rota):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    assert client.post(f"{URL}/{ocorrencia.id}/{rota}", json={"texto": "x"}).status_code == 401


# --- unidade, aba e isolamento ----------------------------------------------------------------


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
def test_ocorrencia_de_outra_unidade_e_404(client, session, predio, morador, rota):
    alheia = criar_ocorrencia(session, predio, unidade=predio.unidade_102, status="resolvida")
    resposta = client.post(f"{URL}/{alheia.id}/{rota}", headers=morador, json={"texto": "Oi"})
    assert resposta.status_code == 404


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
def test_ocorrencia_de_outro_condominio_e_404(client, session, predio, outro_predio, morador, rota):
    alheia = criar_ocorrencia(session, outro_predio, status="resolvida")
    resposta = client.post(f"{URL}/{alheia.id}/{rota}", headers=morador, json={"texto": "Oi"})
    assert resposta.status_code == 404


@pytest.mark.parametrize("rota", ["comentarios", "reabertura"])
def test_aba_sem_acesso_e_403(client, session, predio, morador, rota):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    definir_aba(session, predio.morador_unidade, aba="ocorrencias", com_acesso=False)
    resposta = client.post(f"{URL}/{ocorrencia.id}/{rota}", headers=morador, json={"texto": "Oi"})
    assert resposta.status_code == 403
    assert session.get(Ocorrencia, ocorrencia.id).status == "resolvida"


# --- comentário -------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["em_aberto", "resolvida"])
def test_comentar_vale_em_qualquer_estado_e_nao_muda_o_status(
    client, session, predio, morador, status
):
    ocorrencia = criar_ocorrencia(session, predio, status=status)
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/comentarios", headers=morador, json={"texto": "  Ainda vaza.  "}
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["tipo"] == "comentario"
    assert dados["texto"] == "Ainda vaza."
    assert dados["autor"] == {"tipo": "morador", "nome": predio.morador.nome}
    assert dados["anexos"] == []
    session.refresh(ocorrencia)
    assert ocorrencia.status == status


def test_comentar_aparece_no_historico_e_aguarda_a_administracao(
    client, session, predio, morador, adm
):
    ocorrencia = criar_ocorrencia(session, predio)
    responsavel = criar_responsavel(session, predio)
    criar_interacao(session, predio, ocorrencia, responsavel=responsavel, criado_em=ANTES)
    antes = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador).json()
    assert antes["items"][0]["aguardando_administracao"] is False

    client.post(f"{URL}/{ocorrencia.id}/comentarios", headers=morador, json={"texto": "E agora?"})

    detalhe = client.get(f"{URL}/{ocorrencia.id}", headers=adm).json()
    assert [i["tipo"] for i in detalhe["interacoes"]] == ["resposta", "comentario"]
    depois = client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador).json()
    assert depois["items"][0]["aguardando_administracao"] is True


def test_comentar_com_anexos(client, session, predio, morador):
    ocorrencia = criar_ocorrencia(session, predio)
    foto = criar_arquivo(session, predio)
    video = criar_arquivo(session, predio, tipo_mime="video/mp4")
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/comentarios",
        headers=morador,
        json={"texto": "Fotos novas.", "anexos": [str(foto.id), str(video.id)]},
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert {a["arquivo_id"] for a in dados["anexos"]} == {str(foto.id), str(video.id)}
    assert all(a["interacao_id"] == dados["id"] for a in dados["anexos"])

    detalhe = client.get(f"{URL}/{ocorrencia.id}", headers=morador).json()
    assert len(detalhe["anexos"]) == 2
    assert {a["arquivo_id"] for a in detalhe["interacoes"][0]["anexos"]} == {
        str(foto.id),
        str(video.id),
    }


@pytest.mark.parametrize(
    "campos",
    [
        {"texto": ""},
        {"texto": "   "},
        {"texto": "x" * 2001},
        {"texto": "Oi", "anexos": [str(uuid.uuid4())] * 2},
        {"texto": "Oi", "anexos": [str(uuid.uuid4()) for _ in range(6)]},
        {"texto": "Oi", "status": "resolvida"},
        {"texto": "Oi", "responsavel_id": str(uuid.uuid4())},
    ],
)
def test_comentario_invalido_e_422(client, session, predio, morador, campos):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta = client.post(f"{URL}/{ocorrencia.id}/comentarios", headers=morador, json=campos)
    assert resposta.status_code == 422, resposta.text


@pytest.mark.parametrize(
    "preparar",
    [
        pytest.param(lambda s, p: uuid.uuid4(), id="inexistente"),
        pytest.param(lambda s, p: criar_arquivo(s, p, de_condominio=False).id, id="sem_condominio"),
        pytest.param(lambda s, p: criar_arquivo(s, p, usuario=p.administracao).id, id="de_outro"),
        pytest.param(lambda s, p: criar_arquivo(s, p, modulo="encomendas").id, id="outro_modulo"),
        pytest.param(lambda s, p: criar_arquivo(s, p, tipo_mime="application/pdf").id, id="pdf"),
    ],
)
def test_comentario_com_anexo_invalido_e_422(client, session, predio, morador, preparar):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/comentarios",
        headers=morador,
        json={"texto": "Oi", "anexos": [str(preparar(session, predio))]},
    )
    assert resposta.status_code == 422, resposta.text
    assert session.scalars(select(OcorrenciaInteracao)).first() is None


def test_comentario_nao_reaproveita_anexo_ja_na_ocorrencia(client, session, predio, morador):
    foto = criar_arquivo(session, predio)
    ocorrencia = criar_ocorrencia(session, predio, anexos=(foto,))
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/comentarios",
        headers=morador,
        json={"texto": "De novo.", "anexos": [str(foto.id)]},
    )
    assert resposta.status_code == 422
    total = session.scalars(
        select(OcorrenciaAnexo).where(OcorrenciaAnexo.ocorrencia_id == ocorrencia.id)
    ).all()
    assert len(total) == 1


# --- reabertura -------------------------------------------------------------------------------


def test_reabrir_volta_a_em_aberto_e_guarda_o_historico(client, session, predio, morador, adm):
    ocorrencia = criar_ocorrencia(session, predio)
    responsavel = criar_responsavel(session, predio)
    resolvida = client.post(
        f"{URL}/{ocorrencia.id}/resolucao",
        headers=adm,
        json={"texto": "Corrigido.", "responsavel_id": str(responsavel.id)},
    )
    assert resolvida.json()["resolvida_em"] is not None

    resposta = client.post(
        f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": "  Voltou a vazar. "}
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["status"] == "em_aberto"
    assert dados["resolvida_em"] is None
    # Os testes rodam numa transação só (now() fixo), então comparamos sem depender da ordem.
    assert sorted(i["tipo"] for i in dados["interacoes"]) == ["reabertura", "resolucao"]
    [reabertura] = [i for i in dados["interacoes"] if i["tipo"] == "reabertura"]
    assert reabertura["texto"] == "Voltou a vazar."
    assert reabertura["autor"] == {"tipo": "morador", "nome": predio.morador.nome}
    session.refresh(ocorrencia)
    assert ocorrencia.status == "em_aberto" and ocorrencia.resolvida_em is None


def test_reabrir_devolve_a_ocorrencia_para_a_fila_da_administracao(
    client, session, predio, morador, adm
):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    responsavel = criar_responsavel(session, predio)
    criar_interacao(
        session, predio, ocorrencia, tipo="resolucao", responsavel=responsavel, criado_em=ANTES
    )
    client.post(f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": "Voltou."})

    fila = client.get(f"{URL}?status=em_aberto", headers=adm).json()
    [item] = fila["items"]
    assert item["id"] == str(ocorrencia.id)
    assert item["aguardando_administracao"] is True


def test_reabrir_gera_auditoria(client, session, predio, morador):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    client.post(f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": "Voltou."})
    [evento] = eventos(session, predio, "ocorrencia.reabrir")
    assert evento.recurso_id == ocorrencia.id
    assert evento.usuario_id == predio.morador.id
    assert evento.antes == {"status": "resolvida"}
    assert evento.depois == {"status": "em_aberto"}


@pytest.mark.parametrize("texto", ["", "   ", "x" * 2001])
def test_reabrir_com_texto_invalido_e_422(client, session, predio, morador, texto):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": texto}
    )
    assert resposta.status_code == 422
    assert session.get(Ocorrencia, ocorrencia.id).status == "resolvida"


def test_reabrir_exige_texto_e_recusa_campos_extras(client, session, predio, morador):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    url = f"{URL}/{ocorrencia.id}/reabertura"
    assert client.post(url, headers=morador, json={}).status_code == 422
    assert client.post(url, headers=morador, json={"texto": "Oi", "status": "x"}).status_code == 422


def test_reabrir_em_aberto_e_409(client, session, predio, morador):
    ocorrencia = criar_ocorrencia(session, predio)
    resposta = client.post(
        f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": "Oi"}
    )
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "ocorrencia_nao_resolvida"
    assert eventos(session, predio, "ocorrencia.reabrir") == []


def test_reabrir_duas_vezes_e_409_e_guarda_so_uma_reabertura(client, session, predio, morador):
    ocorrencia = criar_ocorrencia(session, predio, status="resolvida")
    url = f"{URL}/{ocorrencia.id}/reabertura"
    assert client.post(url, headers=morador, json={"texto": "Voltou."}).status_code == 200
    segunda = client.post(url, headers=morador, json={"texto": "Voltou de novo."})
    assert segunda.status_code == 409
    reaberturas = session.scalars(
        select(OcorrenciaInteracao).where(
            OcorrenciaInteracao.ocorrencia_id == ocorrencia.id,
            OcorrenciaInteracao.tipo == "reabertura",
        )
    ).all()
    assert len(reaberturas) == 1


def test_ciclo_resolver_reabrir_resolver(client, session, predio, morador, adm):
    ocorrencia = criar_ocorrencia(session, predio)
    responsavel = criar_responsavel(session, predio)
    resolver = {"texto": None, "responsavel_id": str(responsavel.id)}
    assert (
        client.post(f"{URL}/{ocorrencia.id}/resolucao", headers=adm, json=resolver).status_code
        == 200
    )
    assert (
        client.post(
            f"{URL}/{ocorrencia.id}/reabertura", headers=morador, json={"texto": "Voltou"}
        ).status_code
        == 200
    )
    final = client.post(f"{URL}/{ocorrencia.id}/resolucao", headers=adm, json=resolver)
    assert final.status_code == 200
    assert sorted(i["tipo"] for i in final.json()["interacoes"]) == [
        "reabertura",
        "resolucao",
        "resolucao",
    ]
    assert final.json()["status"] == "resolvida"
