"""Reservas: criação e ordem de validação, cancelamento, agenda, calendário, listas e vazamento."""

import json
import uuid
from datetime import date, time, timedelta

import pytest
from sqlalchemy import select

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.reservas.models import Reserva
from tests.autorizacao.cenario import criar_unidade
from tests.reservas.cenario import (
    AGORA,
    DIA,
    HOJE_CONGELADO,
    ONTEM,
    criar_area,
    criar_bloqueio,
    criar_reserva,
    criar_responsavel,
    definir_aba,
    novo_morador,
    pedido,
)

URL = "/api/v1/reservas"


@pytest.fixture(autouse=True)
def congelar(relogio):
    relogio.momento = AGORA  # 10/06/2030, 14:30 em São Paulo


@pytest.fixture
def morador(session, predio):
    definir_aba(session, predio.morador_unidade)
    return predio.cabecalho_de(Perfil.MORADOR)


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


@pytest.fixture
def area(session, predio):
    return criar_area(session, predio)  # 08:00 a 22:00


@pytest.fixture
def vizinho(session, predio):
    """Morador da 102, com nome fácil de procurar no JSON das respostas ao morador da 101."""
    usuario, _, cabecalho = novo_morador(
        session, predio, predio.unidade_102, nome="Vizinho Secreto"
    )
    return usuario, cabecalho


def eventos(session, predio, acao):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == predio.condominio.id,
                RegistroAuditoria.acao == acao,
            )
        )
    )


def erro(resposta):
    return resposta.json()["error"]


# --- criar ------------------------------------------------------------------------------------


def test_criar_devolve_201_location_objeto_e_auditoria(client, session, predio, morador, area):
    resposta = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "18:00")
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["area"] == {"id": str(area.id), "nome": area.nome}
    assert dados["unidade"] == {"id": str(predio.unidade_101.id), "identificacao": "Bloco A / 101"}
    assert (dados["data"], dados["hora_inicio"], dados["hora_fim"]) == (
        DIA.isoformat(),
        "18:00",
        "19:00",
    )
    assert dados["status"] == "ativa"
    assert dados["reservada_por"] == {"id": str(predio.morador.id), "nome": predio.morador.nome}
    assert dados["cancelamento"] is None
    assert "criada_em" in dados
    assert resposta.headers["Location"] == f"{URL}/{dados['id']}"

    [evento] = eventos(session, predio, "reserva.criar")
    assert evento.recurso_id == uuid.UUID(dados["id"])
    assert evento.usuario_id == predio.morador.id
    assert evento.depois == {
        "area_id": str(area.id),
        "unidade_id": str(predio.unidade_101.id),
        "data": DIA.isoformat(),
        "hora_inicio": "18:00",
    }


@pytest.mark.parametrize(
    ("hora", "dia", "status", "reason"),
    [
        ("10:30", DIA, 422, "hora_invalida"),
        ("07:00", DIA, 422, "fora_do_funcionamento"),  # antes de abrir
        ("22:00", DIA, 422, "fora_do_funcionamento"),  # 22h + 1h passa do fechamento
        ("14:00", HOJE_CONGELADO, 422, "horario_passado"),  # já começou (14:00 <= 14:30)
        ("13:00", HOJE_CONGELADO, 422, "horario_passado"),
        ("20:00", ONTEM, 422, "horario_passado"),
    ],
)
def test_regras_de_horario(client, predio, morador, area, hora, dia, status, reason):
    resposta = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101, dia, hora))
    assert resposta.status_code == status
    assert erro(resposta)["reason"] == reason


def test_limites_do_funcionamento_sao_aceitos(client, session, predio, morador, area):
    primeiro = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "08:00")
    )
    outro_dia = DIA + timedelta(days=1)
    ultimo = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, outro_dia, "21:00")
    )
    hoje_ainda = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, HOJE_CONGELADO, "15:00")
    )
    assert (primeiro.status_code, ultimo.status_code, hoje_ainda.status_code) == (201, 201, 201)


@pytest.mark.parametrize(
    ("corpo_extra", "descricao"),
    [
        ({"hora_inicio": "18:00:00"}, "segundos"),
        ({"hora_inicio": "18h"}, "texto"),
        ({"hora_inicio": 18}, "número"),
        ({"data": "2030-13-01"}, "mês inválido"),
        ({"data": "amanhã"}, "data em texto"),
        ({"area_id": "nao-uuid"}, "área sem uuid"),
        ({"hora_fim": "19:00"}, "campo extra"),
        ({"usuario_id": str(uuid.uuid4())}, "usuario_id no corpo"),
    ],
)
def test_formato_invalido_e_422_sem_reason(client, predio, morador, area, corpo_extra, descricao):
    corpo = pedido(area, predio.unidade_101) | corpo_extra
    resposta = client.post(URL, headers=morador, json=corpo)
    assert resposta.status_code == 422, descricao
    assert erro(resposta)["code"] == "validation_error"
    assert "reason" not in erro(resposta)


def test_area_desativada_ou_inexistente_e_404(client, session, predio, morador):
    desativada = criar_area(session, predio, "Quadra", ativa=False)
    assert (
        client.post(URL, headers=morador, json=pedido(desativada, predio.unidade_101)).status_code
        == 404
    )
    corpo = pedido(desativada, predio.unidade_101) | {"area_id": str(uuid.uuid4())}
    assert client.post(URL, headers=morador, json=corpo).status_code == 404


def test_dentro_de_bloqueio_e_409(client, session, predio, morador, area):
    criar_bloqueio(session, predio, area, DIA - timedelta(days=1), DIA + timedelta(days=1))
    resposta = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101))
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "area_bloqueada"


def test_bloqueio_removido_ou_de_outra_area_nao_bloqueia(client, session, predio, morador, area):
    criar_bloqueio(session, predio, area, DIA, DIA, removido=True)
    criar_bloqueio(session, predio, criar_area(session, predio, "Quadra"), DIA, DIA)
    assert (
        client.post(URL, headers=morador, json=pedido(area, predio.unidade_101)).status_code == 201
    )


@pytest.mark.parametrize(
    ("montar", "esperado"),
    [
        # Área desativada (5) vence hora quebrada (6).
        ("desativada+quebrada", (404, None)),
        # Hora quebrada (6) vence fora do funcionamento (7).
        ("quebrada+fora", (422, "hora_invalida")),
        # Fora do funcionamento (7) vence passado (8).
        ("fora+passado", (422, "fora_do_funcionamento")),
        # Passado (8) vence bloqueio (9).
        ("passado+bloqueio", (422, "horario_passado")),
        # Bloqueio (9) vence a duplicidade da unidade (10).
        ("bloqueio+duplicada", (409, "area_bloqueada")),
    ],
)
def test_ordem_de_validacao(client, session, predio, morador, area, montar, esperado):
    dia, hora = DIA, "10:00"
    if montar == "desativada+quebrada":
        area.ativa = False
        hora = "10:30"
    elif montar == "quebrada+fora":
        hora = "07:30"
    elif montar == "fora+passado":
        dia, hora = ONTEM, "07:00"
    elif montar == "passado+bloqueio":
        dia = ONTEM
        criar_bloqueio(session, predio, area, ONTEM, ONTEM)
    else:
        criar_reserva(session, predio, area, data=DIA, hora=12)
        criar_bloqueio(session, predio, area, DIA, DIA)
    session.flush()
    resposta = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101, dia, hora))
    assert resposta.status_code == esperado[0], resposta.text
    if esperado[1]:
        assert erro(resposta)["reason"] == esperado[1]


def test_segunda_reserva_da_unidade_no_mesmo_dia_e_409(client, predio, morador, area):
    assert (
        client.post(
            URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "10:00")
        ).status_code
        == 201
    )
    resposta = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "15:00")
    )
    assert resposta.status_code == 409
    assert erro(resposta) == {
        "code": "conflict",
        "message": "Cada unidade pode reservar no máximo um horário por área por dia.",
        "reason": "reserva_duplicada_unidade",
    }


def test_horario_ocupado_nao_cita_a_outra_unidade(client, session, predio, morador, area, vizinho):
    _, cab_vizinho = vizinho
    assert (
        client.post(URL, headers=cab_vizinho, json=pedido(area, predio.unidade_102)).status_code
        == 201
    )
    resposta = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101))
    assert resposta.status_code == 409
    assert erro(resposta) == {
        "code": "conflict",
        "message": "Este horário acabou de ser reservado por outra unidade. Escolha outro.",
        "reason": "horario_ocupado",
    }
    texto = resposta.text
    assert "102" not in texto and str(predio.unidade_102.id) not in texto


def test_reservar_cancelar_e_reservar_de_novo(client, session, predio, morador, area):
    primeira = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101)).json()
    assert (
        client.post(f"{URL}/{primeira['id']}/cancelamento", headers=morador, json={}).status_code
        == 200
    )
    de_novo = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101))
    assert de_novo.status_code == 201
    assert de_novo.json()["id"] != primeira["id"]


def test_falha_na_auditoria_desfaz_a_reserva(client, session, predio, morador, area, monkeypatch):
    from app.modules.auditoria import service as auditoria

    def quebrar(*args, **kwargs):
        raise RuntimeError("auditoria fora do ar")

    session.commit()  # fixa o cenário: o rollback abaixo só desfaz o que a requisição gravou
    monkeypatch.setattr(auditoria, "registrar_acao", quebrar)
    resposta = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101))
    assert resposta.status_code == 500
    session.rollback()  # o que o get_session real faz quando a requisição estoura
    assert session.scalars(select(Reserva).where(Reserva.area_id == area.id)).all() == []


# --- cancelar ---------------------------------------------------------------------------------


def test_morador_cancela_e_repetir_e_409(client, session, predio, morador, area):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    url = f"{URL}/{reserva.id}/cancelamento"

    resposta = client.post(url, headers=morador, json={})
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["status"] == "cancelada"
    assert dados["cancelamento"]["por"] == "morador"
    assert dados["cancelamento"]["motivo"] is None
    assert "responsavel" not in dados["cancelamento"]  # só a Administração vê
    session.refresh(reserva)
    assert reserva.cancelada_por_usuario_id == predio.morador.id
    assert reserva.cancelada_responsavel_id is None

    repetir = client.post(url, headers=morador)  # sem corpo também vale
    assert repetir.status_code == 409
    assert erro(repetir)["reason"] == "reserva_ja_cancelada"

    [evento] = eventos(session, predio, "reserva.cancelar")
    assert evento.depois == {"status": "cancelada", "por": "morador"}
    assert evento.responsavel_nome is None


def test_outro_morador_da_mesma_unidade_cancela(client, session, predio, morador, area):
    _, _, colega = novo_morador(session, predio, predio.unidade_101, nome="Colega da 101")
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)  # feita pelo morador
    assert (
        client.post(f"{URL}/{reserva.id}/cancelamento", headers=colega, json={}).status_code == 200
    )


def test_morador_nao_manda_motivo_nem_responsavel(client, session, predio, morador, area):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    resposta = client.post(
        f"{URL}/{reserva.id}/cancelamento", headers=morador, json={"motivo": "x"}
    )
    assert resposta.status_code == 422


def test_cancelar_reserva_passada_e_409(client, session, predio, morador, area):
    ja_comecou = criar_reserva(session, predio, area, data=HOJE_CONGELADO, hora=14)
    ontem = criar_reserva(
        session, predio, criar_area(session, predio, "Quadra"), data=ONTEM, hora=20
    )
    for reserva in (ja_comecou, ontem):
        resposta = client.post(f"{URL}/{reserva.id}/cancelamento", headers=morador, json={})
        assert resposta.status_code == 409
        assert erro(resposta)["reason"] == "reserva_encerrada"


def test_status_e_conferido_antes_do_horario(client, session, predio, morador, area):
    cancelada_e_passada = criar_reserva(
        session, predio, area, data=ONTEM, hora=10, status="cancelada"
    )
    resposta = client.post(f"{URL}/{cancelada_e_passada.id}/cancelamento", headers=morador, json={})
    assert erro(resposta)["reason"] == "reserva_ja_cancelada"


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"motivo": "Manutenção"},
        {"responsavel_id": "RESP"},
        {"motivo": "", "responsavel_id": "RESP"},
        {"motivo": "   ", "responsavel_id": "RESP"},
        {"motivo": "m" * 301, "responsavel_id": "RESP"},
        {"motivo": "Manutenção", "responsavel_id": "nao-uuid"},
        {"motivo": "Manutenção", "responsavel_id": "RESP", "extra": 1},
    ],
)
def test_administracao_sem_motivo_ou_responsavel_e_422(client, session, predio, adm, area, corpo):
    responsavel = criar_responsavel(session, predio)
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    corpo = {k: (str(responsavel.id) if v == "RESP" else v) for k, v in corpo.items()}
    resposta = client.post(f"{URL}/{reserva.id}/cancelamento", headers=adm, json=corpo)
    assert resposta.status_code == 422, corpo
    session.refresh(reserva)
    assert reserva.status == "ativa"


def test_responsavel_inativo_ou_inexistente_e_404(client, session, predio, adm, area):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    inativo = criar_responsavel(session, predio, "Ex-síndico", ativo=False)
    for responsavel_id in (inativo.id, uuid.uuid4()):
        resposta = client.post(
            f"{URL}/{reserva.id}/cancelamento",
            headers=adm,
            json={"motivo": "Manutenção", "responsavel_id": str(responsavel_id)},
        )
        assert resposta.status_code == 404


def test_administracao_cancela_com_motivo_e_auditoria(client, session, predio, adm, morador, area):
    responsavel = criar_responsavel(session, predio, "Carlos (síndico)")
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    resposta = client.post(
        f"{URL}/{reserva.id}/cancelamento",
        headers=adm,
        json={"motivo": "  Vazamento no salão ", "responsavel_id": str(responsavel.id)},
    )
    assert resposta.status_code == 200, resposta.text
    cancelamento = resposta.json()["cancelamento"]
    assert cancelamento["por"] == "administracao"
    assert cancelamento["motivo"] == "Vazamento no salão"
    assert cancelamento["responsavel"] == {"id": str(responsavel.id), "nome": "Carlos (síndico)"}

    session.refresh(reserva)
    assert reserva.cancelada_responsavel_id == responsavel.id
    assert reserva.motivo_cancelamento == "Vazamento no salão"

    [evento] = eventos(session, predio, "reserva.cancelar")
    assert evento.perfil == "administracao"
    assert evento.responsavel_nome == "Carlos (síndico)"
    assert evento.depois == {
        "status": "cancelada",
        "por": "administracao",
        "responsavel_id": str(responsavel.id),
        "motivo": "Vazamento no salão",
    }

    # O Morador vê o motivo, mas não o responsável.
    visto_pelo_morador = client.get(f"{URL}/{reserva.id}", headers=morador).json()
    assert visto_pelo_morador["cancelamento"]["motivo"] == "Vazamento no salão"
    assert "responsavel" not in visto_pelo_morador["cancelamento"]


def test_administracao_ve_responsavel_nulo_quando_o_morador_cancelou(
    client, session, predio, adm, morador, area
):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    client.post(f"{URL}/{reserva.id}/cancelamento", headers=morador, json={})
    assert (
        client.get(f"{URL}/{reserva.id}", headers=adm).json()["cancelamento"]["responsavel"] is None
    )


# --- agenda -----------------------------------------------------------------------------------


def agenda(client, cab, area, unidade, dia):
    return client.get(
        f"/api/v1/areas-comuns/{area.id}/agenda?unidade_id={unidade.id}&data={dia}", headers=cab
    )


def test_agenda_estados_e_precedencia(client, session, predio, morador, vizinho):
    usuario_vizinho, _ = vizinho
    u103 = criar_unidade(session, predio.condominio, "Bloco A / 103")
    area = criar_area(session, predio, abre_as=time(8), fecha_as=time(18))
    minha_passada = criar_reserva(session, predio, area, data=HOJE_CONGELADO, hora=9)
    criar_reserva(
        session,
        predio,
        area,
        data=HOJE_CONGELADO,
        hora=11,
        unidade=predio.unidade_102,
        usuario=usuario_vizinho,
    )  # passada, de outra unidade
    criar_reserva(
        session, predio, area, data=HOJE_CONGELADO, hora=16, unidade=u103, usuario=usuario_vizinho
    )  # futura, de outra unidade (uma por unidade e dia)
    criar_reserva(session, predio, area, data=HOJE_CONGELADO, hora=17, status="cancelada")

    resposta = agenda(client, morador, area, predio.unidade_101, HOJE_CONGELADO)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["unidade_ja_reservou"] is True
    estados = {s["hora_inicio"]: s["estado"] for s in dados["slots"]}
    assert list(estados) == [f"{h:02d}:00" for h in range(8, 18)]  # nada fora do funcionamento
    assert estados["09:00"] == "da_minha_unidade"  # vence "passado"
    assert estados["11:00"] == "ocupado"  # vence "passado"
    assert estados["16:00"] == "ocupado"
    assert estados["14:00"] == "passado"  # 14:00 <= 14:30
    assert estados["15:00"] == "livre"
    assert estados["17:00"] == "livre"  # cancelada libera o horário

    slot_meu = next(s for s in dados["slots"] if s["hora_inicio"] == "09:00")
    assert slot_meu == {
        "hora_inicio": "09:00",
        "hora_fim": "10:00",
        "estado": "da_minha_unidade",
        "reserva_id": str(minha_passada.id),
    }
    assert all("reserva_id" not in s for s in dados["slots"] if s["estado"] != "da_minha_unidade")


def test_agenda_bloqueado_vence_passado_e_perde_para_reservas(
    client, session, predio, morador, vizinho, area
):
    usuario_vizinho, _ = vizinho
    criar_bloqueio(session, predio, area, HOJE_CONGELADO, HOJE_CONGELADO)
    criar_reserva(
        session,
        predio,
        area,
        data=HOJE_CONGELADO,
        hora=20,
        unidade=predio.unidade_102,
        usuario=usuario_vizinho,
    )
    dados = agenda(client, morador, area, predio.unidade_101, HOJE_CONGELADO).json()
    estados = {s["hora_inicio"]: s["estado"] for s in dados["slots"]}
    assert estados["08:00"] == "bloqueado"  # passado, mas bloqueado vem antes
    assert estados["15:00"] == "bloqueado"
    assert estados["20:00"] == "ocupado"
    assert dados["unidade_ja_reservou"] is False


def test_agenda_de_area_desativada_e_404(client, session, predio, morador):
    desativada = criar_area(session, predio, ativa=False)
    assert agenda(client, morador, desativada, predio.unidade_101, DIA).status_code == 404
    url = (
        f"/api/v1/areas-comuns/{uuid.uuid4()}/agenda?unidade_id={predio.unidade_101.id}&data={DIA}"
    )
    assert client.get(url, headers=morador).status_code == 404


@pytest.mark.parametrize(
    "query", ["data=2030-02-30", "data=amanha", "", "unidade_id=x&data=2030-06-11"]
)
def test_agenda_com_query_invalida_e_422(client, predio, morador, area, query):
    if "unidade_id" not in query:
        query = f"unidade_id={predio.unidade_101.id}&{query}"
    resposta = client.get(f"/api/v1/areas-comuns/{area.id}/agenda?{query}", headers=morador)
    assert resposta.status_code == 422


# --- calendário -------------------------------------------------------------------------------


def test_calendario_so_dias_com_bloqueio_ou_reserva_da_unidade(
    client, session, predio, morador, vizinho, area
):
    usuario_vizinho, _ = vizinho
    criar_bloqueio(session, predio, area, date(2030, 5, 30), date(2030, 6, 2))  # cruza o mês
    criar_bloqueio(session, predio, area, date(2030, 6, 20), date(2030, 6, 20), removido=True)
    criar_reserva(session, predio, area, data=date(2030, 6, 2), hora=10)  # bloqueado e minha
    criar_reserva(session, predio, area, data=date(2030, 6, 15), hora=10)
    criar_reserva(session, predio, area, data=date(2030, 6, 16), hora=10, status="cancelada")
    criar_reserva(
        session,
        predio,
        area,
        data=date(2030, 6, 17),
        hora=10,
        unidade=predio.unidade_102,
        usuario=usuario_vizinho,
    )
    criar_reserva(session, predio, area, data=date(2030, 7, 1), hora=10)  # outro mês

    resposta = client.get(
        f"/api/v1/areas-comuns/{area.id}/calendario?unidade_id={predio.unidade_101.id}&mes=2030-06",
        headers=morador,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "mes": "2030-06",
        "dias": [
            {"data": "2030-06-01", "bloqueado": True, "tem_reserva_da_minha_unidade": False},
            {"data": "2030-06-02", "bloqueado": True, "tem_reserva_da_minha_unidade": True},
            {"data": "2030-06-15", "bloqueado": False, "tem_reserva_da_minha_unidade": True},
        ],
    }


@pytest.mark.parametrize("mes", ["2030-13", "2030-6", "junho", ""])
def test_calendario_com_mes_invalido_e_422(client, predio, morador, area, mes):
    url = f"/api/v1/areas-comuns/{area.id}/calendario?unidade_id={predio.unidade_101.id}&mes={mes}"
    assert client.get(url, headers=morador).status_code == 422


def test_calendario_com_disponibilidade_respeita_horas_e_cancelamentos(
    client, session, predio, morador, vizinho
):
    area = criar_area(session, predio, abre_as=time(9), fecha_as=time(10))
    usuario_vizinho, _ = vizinho

    def junho(dia: int) -> date:
        return date(2030, 6, dia)

    criar_reserva(
        session,
        predio,
        area,
        data=junho(12),
        hora=9,
        unidade=predio.unidade_102,
        usuario=usuario_vizinho,
    )
    criar_reserva(session, predio, area, data=junho(13), hora=9, status="cancelada")
    criar_reserva(session, predio, area, data=junho(14), hora=9)
    criar_bloqueio(session, predio, area, junho(15), junho(15))
    resposta = client.get(
        f"/api/v1/areas-comuns/{area.id}/calendario",
        params={
            "unidade_id": str(predio.unidade_101.id),
            "mes": "2030-06",
            "incluir_disponibilidade": True,
        },
        headers=morador,
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["dias_disponiveis"][:3] == ["2030-06-11", "2030-06-13", "2030-06-16"]
    assert "Vizinho Secreto" not in resposta.text


# --- listas -----------------------------------------------------------------------------------


def test_lista_do_morador_futuras_primeiro_depois_passadas(
    client, session, predio, morador, vizinho
):
    usuario_vizinho, _ = vizinho
    a1 = criar_area(session, predio, "A1")
    a2 = criar_area(session, predio, "A2")
    esperado = [
        criar_reserva(session, predio, a1, data=HOJE_CONGELADO, hora=15),  # futura mais próxima
        criar_reserva(session, predio, a1, data=DIA, hora=9),
        criar_reserva(
            session, predio, a1, data=DIA + timedelta(days=5), hora=8, status="cancelada"
        ),
        criar_reserva(session, predio, a2, data=HOJE_CONGELADO, hora=14),  # passada mais recente
        criar_reserva(session, predio, a1, data=ONTEM, hora=21),
        criar_reserva(session, predio, a1, data=ONTEM - timedelta(days=3), hora=10),
    ]
    criar_reserva(
        session, predio, a1, data=DIA, hora=12, unidade=predio.unidade_102, usuario=usuario_vizinho
    )  # de outra unidade: nunca aparece

    url = f"{URL}?unidade_id={predio.unidade_101.id}"
    dados = client.get(url, headers=morador).json()
    assert [r["id"] for r in dados["items"]] == [str(r.id) for r in esperado]
    assert dados["total"] == 6

    pagina_2 = client.get(f"{url}&page=2&page_size=4", headers=morador).json()
    assert [r["id"] for r in pagina_2["items"]] == [str(r.id) for r in esperado[4:]]

    # Filtros da Administração são ignorados para o Morador.
    filtrada = client.get(f"{url}&status=cancelada&area_id={a2.id}", headers=morador).json()
    assert filtrada["total"] == 6


def test_morador_sem_unidade_id_e_422(client, morador):
    assert client.get(URL, headers=morador).status_code == 422


def test_filtros_e_ordem_da_administracao(client, session, predio, adm, vizinho):
    usuario_vizinho, _ = vizinho
    a1 = criar_area(session, predio, "A1")
    a2 = criar_area(session, predio, "A2")
    r1 = criar_reserva(session, predio, a1, data=DIA, hora=9)
    r2 = criar_reserva(session, predio, a2, data=DIA, hora=20, status="cancelada")
    r3 = criar_reserva(session, predio, a1, data=ONTEM, hora=10)
    r4 = criar_reserva(
        session,
        predio,
        a1,
        data=DIA + timedelta(days=2),
        hora=11,
        unidade=predio.unidade_102,
        usuario=usuario_vizinho,
    )

    def ids(query=""):
        dados = client.get(f"{URL}?{query}", headers=adm).json()
        return [r["id"] for r in dados["items"]]

    assert ids() == [str(r.id) for r in (r4, r2, r1, r3)]  # data desc, depois hora desc
    assert ids(f"area_id={a2.id}") == [str(r2.id)]
    assert ids(f"unidade_id={predio.unidade_102.id}") == [str(r4.id)]
    assert ids(f"data_de={DIA}&data_ate={DIA}") == [str(r2.id), str(r1.id)]
    assert ids("status=ativa") == [str(r.id) for r in (r4, r1, r3)]
    assert ids("status=cancelada") == [str(r2.id)]
    assert ids(f"data_ate={ONTEM}") == [str(r3.id)]


@pytest.mark.parametrize("query", ["page=0", "page_size=101", "status=expirada", "data_de=ontem"])
def test_query_invalida_na_lista_e_422(client, adm, query):
    assert client.get(f"{URL}?{query}", headers=adm).status_code == 422


def test_reserva_inexistente_e_404(client, adm, morador):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=adm).status_code == 404
    assert (
        client.post(f"{URL}/{uuid.uuid4()}/cancelamento", headers=morador, json={}).status_code
        == 404
    )


# --- nada de outra unidade nas respostas ao Morador ---------------------------------------------


def test_respostas_ao_morador_nunca_trazem_outra_unidade(
    client, session, predio, morador, vizinho, area
):
    usuario_vizinho, cab_vizinho = vizinho
    da_vizinha = client.post(
        URL, headers=cab_vizinho, json=pedido(area, predio.unidade_102, DIA, "19:00")
    )
    assert da_vizinha.status_code == 201
    minha = client.post(
        URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "18:00")
    ).json()
    ocupado = client.post(URL, headers=morador, json=pedido(area, predio.unidade_101, DIA, "19:00"))

    respostas = [
        agenda(client, morador, area, predio.unidade_101, DIA),
        client.get(
            f"/api/v1/areas-comuns/{area.id}/calendario?unidade_id={predio.unidade_101.id}&mes=2030-06",
            headers=morador,
        ),
        client.get(f"{URL}?unidade_id={predio.unidade_101.id}", headers=morador),
        client.get(f"{URL}/{minha['id']}", headers=morador),
        ocupado,
        client.get(f"{URL}/{da_vizinha.json()['id']}", headers=morador),  # 404
    ]
    proibidos = [
        str(predio.unidade_102.id),
        "Bloco A / 102",
        str(usuario_vizinho.id),
        "Vizinho Secreto",
        usuario_vizinho.email,
        da_vizinha.json()["id"],  # nem o id da reserva alheia
    ]
    for resposta in respostas:
        texto = json.dumps(resposta.json(), ensure_ascii=False)
        for valor in proibidos:
            assert valor not in texto, (resposta.request.url, valor)

    # Na grade, o horário do vizinho aparece só como "ocupado".
    slot = next(s for s in respostas[0].json()["slots"] if s["hora_inicio"] == "19:00")
    assert slot == {"hora_inicio": "19:00", "hora_fim": "20:00", "estado": "ocupado"}
