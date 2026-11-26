"""Bloqueio de datas (US-602) e e-mail `reserva_cancelada` (US-803)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.permissoes import Perfil
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.avisos.models import Aviso
from app.modules.notificacoes.models import EnvioEmail
from app.modules.reservas.models import BloqueioArea, Reserva
from app.modules.reservas.repository import RepositorioReservas
from tests.reservas.cenario import (
    AGORA,
    DIA,
    HOJE_CONGELADO,
    ONTEM,
    criar_area,
    criar_bloqueio,
    criar_reserva,
    criar_responsavel,
    novo_morador,
    pedido,
)

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]


@pytest.fixture(autouse=True)
def congelar(relogio):
    relogio.momento = AGORA  # 10/06/2030, 14:30 em São Paulo


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


@pytest.fixture
def area(session, predio):
    return criar_area(session, predio)


@pytest.fixture
def responsavel(session, predio):
    return criar_responsavel(session, predio)


def url(area, sufixo="bloqueios"):
    return f"/api/v1/areas-comuns/{area.id}/{sufixo}"


def corpo(responsavel, de=None, ate=None, **campos):
    base = {
        "data_inicio": (de or DIA).isoformat(),
        "data_fim": (ate or de or DIA).isoformat(),
        "motivo": "Manutenção do piso",
        "responsavel_id": str(responsavel.id),
        "confirmar_cancelamentos": False,
    }
    base.update(campos)
    return base


def erro(resposta):
    return resposta.json()["error"]


def contar(session, modelo, *condicoes):
    return session.scalar(select(func.count()).select_from(modelo).where(*condicoes))


def eventos(session, predio, acao):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == predio.condominio.id,
                RegistroAuditoria.acao == acao,
            )
        )
    )


# --- perfis, 401 e isolamento -----------------------------------------------------------------


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
@pytest.mark.parametrize("rota", ["listar", "previa", "criar"])
def test_matriz_por_perfil(client, predio, area, responsavel, rota, indice):
    headers = predio.cabecalho_de(PERFIS[indice])
    resposta = {
        "listar": lambda: client.get(url(area), headers=headers),
        "previa": lambda: client.get(
            url(area, "bloqueios/previa"),
            headers=headers,
            params={"data_inicio": DIA.isoformat(), "data_fim": DIA.isoformat()},
        ),
        "criar": lambda: client.post(url(area), headers=headers, json=corpo(responsavel)),
    }[rota]()
    esperado = (201 if rota == "criar" else 200) if PERFIS[indice] == Perfil.ADMINISTRACAO else 403
    assert resposta.status_code == esperado, resposta.text
    if esperado == 403:
        assert erro(resposta)["code"] == "forbidden"


@pytest.mark.parametrize("rota", ["bloqueios", "bloqueios/previa"])
def test_sem_token_e_401(client, area, rota):
    assert client.get(url(area, rota)).status_code == 401
    assert client.post(url(area), json={}).status_code == 401


def test_403_de_perfil_vem_antes_de_422(client, predio, area):
    resposta = client.post(
        url(area), headers=predio.cabecalho_de(Perfil.MORADOR), json={"lixo": True}
    )
    assert resposta.status_code == 403


def test_area_de_outro_condominio_e_404(client, session, predio, outro_predio, adm, responsavel):
    alheia = criar_area(session, outro_predio)
    assert client.get(url(alheia), headers=adm).status_code == 404
    assert (
        client.get(
            url(alheia, "bloqueios/previa"),
            headers=adm,
            params={"data_inicio": DIA.isoformat(), "data_fim": DIA.isoformat()},
        ).status_code
        == 404
    )
    assert client.post(url(alheia), headers=adm, json=corpo(responsavel)).status_code == 404
    assert contar(session, BloqueioArea, BloqueioArea.area_id == alheia.id) == 0


def test_responsavel_de_outro_condominio_ou_inativo_e_404(
    client, session, predio, outro_predio, area, adm
):
    de_outro = criar_responsavel(session, outro_predio)
    inativo = criar_responsavel(session, predio, "Antigo", ativo=False)
    for responsavel in (de_outro, inativo):
        resposta = client.post(url(area), headers=adm, json=corpo(responsavel))
        assert resposta.status_code == 404
    assert contar(session, BloqueioArea, BloqueioArea.area_id == area.id) == 0


# --- validação --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campos",
    [
        {"data_fim": (DIA - timedelta(days=1)).isoformat()},  # fim antes do início
        {"motivo": ""},
        {"motivo": "   "},
        {"motivo": "m" * 201},
        {"data_inicio": "amanhã"},
        {"confirmar_cancelamentos": "talvez"},
        {"condominio_id": str(uuid.uuid4())},
        {"area_id": str(uuid.uuid4())},
    ],
)
def test_entrada_invalida_e_422(client, session, area, adm, responsavel, campos):
    resposta = client.post(url(area), headers=adm, json=corpo(responsavel, **campos))
    assert resposta.status_code == 422, resposta.text
    assert contar(session, BloqueioArea) == 0


@pytest.mark.parametrize("campo", ["data_inicio", "data_fim", "motivo", "responsavel_id"])
def test_campos_obrigatorios(client, area, adm, responsavel, campo):
    dados = corpo(responsavel)
    del dados[campo]
    assert client.post(url(area), headers=adm, json=dados).status_code == 422


def test_periodo_que_ja_terminou_e_422(client, session, area, adm, responsavel):
    resposta = client.post(url(area), headers=adm, json=corpo(responsavel, ONTEM, ONTEM))
    assert resposta.status_code == 422
    assert erro(resposta)["reason"] == "periodo_passado"
    assert contar(session, BloqueioArea) == 0


def test_periodo_que_termina_hoje_vale(client, area, adm, responsavel):
    hoje = HOJE_CONGELADO
    assert (
        client.post(url(area), headers=adm, json=corpo(responsavel, ONTEM, hoje)).status_code == 201
    )


# --- criar sem reservas -----------------------------------------------------------------------


def test_bloqueio_sem_reservas_e_criado_direto(client, session, predio, area, adm, responsavel):
    resposta = client.post(
        url(area), headers=adm, json=corpo(responsavel, DIA, DIA + timedelta(days=2))
    )
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados["area_id"] == str(area.id)
    assert dados["data_inicio"] == DIA.isoformat()
    assert dados["data_fim"] == (DIA + timedelta(days=2)).isoformat()
    assert dados["motivo"] == "Manutenção do piso"
    assert dados["responsavel"] == {"id": str(responsavel.id), "nome": responsavel.nome}
    assert dados["reservas_canceladas"] == 0

    gravado = session.get(BloqueioArea, uuid.UUID(dados["id"]))
    assert gravado.condominio_id == predio.condominio.id and gravado.removido_em is None
    [evento] = eventos(session, predio, "area.bloquear")
    assert evento.recurso_id == area.id
    assert evento.depois["bloqueio_id"] == dados["id"]
    assert eventos(session, predio, "reserva.cancelar") == []
    assert contar(session, Aviso, Aviso.condominio_id == predio.condominio.id) == 0


def test_dia_unico_repete_a_mesma_data(client, area, adm, responsavel):
    assert client.post(url(area), headers=adm, json=corpo(responsavel, DIA, DIA)).status_code == 201


def test_bloqueios_sobrepostos_sao_aceitos(client, session, area, adm, responsavel):
    for _ in range(2):
        assert client.post(url(area), headers=adm, json=corpo(responsavel)).status_code == 201
    assert contar(session, BloqueioArea, BloqueioArea.area_id == area.id) == 2


def test_area_desativada_aceita_bloqueio(client, session, predio, adm, responsavel):
    desativada = criar_area(session, predio, "Quadra", ativa=False)
    assert client.post(url(desativada), headers=adm, json=corpo(responsavel)).status_code == 201


def test_reserva_nova_na_data_bloqueada_e_409(client, session, predio, area, adm, responsavel):
    client.post(url(area), headers=adm, json=corpo(responsavel))
    morador = predio.cabecalho_de(Perfil.MORADOR)
    resposta = client.post(
        "/api/v1/reservas", headers=morador, json=pedido(area, predio.unidade_101)
    )
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "area_bloqueada"


def test_agenda_do_morador_mostra_o_dia_bloqueado(client, predio, area, adm, responsavel):
    client.post(url(area), headers=adm, json=corpo(responsavel))
    resposta = client.get(
        f"/api/v1/areas-comuns/{area.id}/agenda",
        headers=predio.cabecalho_de(Perfil.MORADOR),
        params={"unidade_id": str(predio.unidade_101.id), "data": DIA.isoformat()},
    )
    assert {slot["estado"] for slot in resposta.json()["slots"]} == {"bloqueado"}


# --- prévia e fluxo com reservas --------------------------------------------------------------


@pytest.fixture
def com_reservas(session, predio, area):
    """Duas reservas ativas dentro do período (101 e 102) e outras que o bloqueio não toca."""
    dentro_101 = criar_reserva(session, predio, area, data=DIA, hora=18)
    dentro_102 = criar_reserva(
        session, predio, area, data=DIA + timedelta(days=1), hora=9, unidade=predio.unidade_102
    )
    fora_do_periodo = criar_reserva(session, predio, area, data=DIA + timedelta(days=5), hora=10)
    cancelada = criar_reserva(session, predio, area, data=DIA, hora=11, status="cancelada")
    outra_area = criar_reserva(
        session, predio, criar_area(session, predio, "Quadra"), data=DIA, hora=8
    )
    return {
        "afetadas": [dentro_101, dentro_102],
        "intocadas": [fora_do_periodo, cancelada, outra_area],
    }


def test_previa_lista_so_as_reservas_que_seriam_canceladas(client, predio, area, adm, com_reservas):
    resposta = client.get(
        url(area, "bloqueios/previa"),
        headers=adm,
        params={
            "data_inicio": DIA.isoformat(),
            "data_fim": (DIA + timedelta(days=2)).isoformat(),
        },
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["total"] == 2
    assert dados["reservas_afetadas"] == [
        {
            "id": str(com_reservas["afetadas"][0].id),
            "unidade": {
                "id": str(predio.unidade_101.id),
                "identificacao": predio.unidade_101.identificacao,
            },
            "data": DIA.isoformat(),
            "hora_inicio": "18:00",
        },
        {
            "id": str(com_reservas["afetadas"][1].id),
            "unidade": {
                "id": str(predio.unidade_102.id),
                "identificacao": predio.unidade_102.identificacao,
            },
            "data": (DIA + timedelta(days=1)).isoformat(),
            "hora_inicio": "09:00",
        },
    ]


def test_previa_nao_grava_nada(client, session, predio, area, adm, com_reservas):
    client.get(
        url(area, "bloqueios/previa"),
        headers=adm,
        params={"data_inicio": DIA.isoformat(), "data_fim": DIA.isoformat()},
    )
    assert contar(session, BloqueioArea) == 0
    assert contar(session, Reserva, Reserva.status == "cancelada") == 1  # só a que já existia


def test_previa_ignora_reserva_que_ja_comecou(client, session, predio, area, adm):
    # Hoje, 14:30: o slot das 14:00 já começou (não se cancela); o das 15:00 ainda não.
    criar_reserva(session, predio, area, data=HOJE_CONGELADO, hora=14)
    futura = criar_reserva(
        session, predio, area, data=HOJE_CONGELADO, hora=15, unidade=predio.unidade_102
    )
    resposta = client.get(
        url(area, "bloqueios/previa"),
        headers=adm,
        params={"data_inicio": HOJE_CONGELADO.isoformat(), "data_fim": HOJE_CONGELADO.isoformat()},
    )
    assert [r["id"] for r in resposta.json()["reservas_afetadas"]] == [str(futura.id)]


def test_previa_com_intervalo_invertido_e_422(client, area, adm):
    resposta = client.get(
        url(area, "bloqueios/previa"),
        headers=adm,
        params={"data_inicio": DIA.isoformat(), "data_fim": (DIA - timedelta(days=1)).isoformat()},
    )
    assert resposta.status_code == 422


def test_sem_confirmacao_com_reservas_afetadas_e_409_e_nao_grava_nada(
    client, session, predio, area, adm, responsavel, com_reservas
):
    resposta = client.post(
        url(area), headers=adm, json=corpo(responsavel, DIA, DIA + timedelta(days=2))
    )
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "reservas_afetadas"
    assert contar(session, BloqueioArea) == 0
    assert contar(session, Reserva, Reserva.status == "cancelada") == 1
    assert contar(session, Aviso, Aviso.condominio_id == predio.condominio.id) == 0
    assert contar(session, EnvioEmail, EnvioEmail.condominio_id == predio.condominio.id) == 0
    assert eventos(session, predio, "area.bloquear") == []


def test_com_confirmacao_cancela_avisa_enfileira_e_audita(
    client, session, predio, area, adm, responsavel, com_reservas
):
    resposta = client.post(
        url(area),
        headers=adm,
        json=corpo(responsavel, DIA, DIA + timedelta(days=2), confirmar_cancelamentos=True),
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["reservas_canceladas"] == 2

    # Reservas afetadas: canceladas pela Administração, com o motivo do bloqueio.
    for reserva in com_reservas["afetadas"]:
        session.refresh(reserva)
        assert reserva.status == "cancelada"
        assert reserva.cancelada_responsavel_id == responsavel.id
        assert reserva.cancelada_por_usuario_id == predio.administracao.id
        assert reserva.motivo_cancelamento == "Bloqueio da área: Manutenção do piso"
    # As outras ficam como estavam.
    for reserva in com_reservas["intocadas"]:
        before = reserva.status
        session.refresh(reserva)
        assert reserva.status == before
    assert com_reservas["intocadas"][0].status == "ativa"

    # Um aviso por unidade afetada (101 e 102), cada um com as reservas dela.
    avisos = list(session.scalars(select(Aviso).where(Aviso.condominio_id == predio.condominio.id)))
    assert {a.unidade_id for a in avisos} == {predio.unidade_101.id, predio.unidade_102.id}
    assert len(avisos) == 2
    da_101 = next(a for a in avisos if a.unidade_id == predio.unidade_101.id)
    assert "Manutenção do piso" in da_101.texto and "18:00" in da_101.texto
    assert area.nome in da_101.texto

    # E-mail `reserva_cancelada` por reserva cancelada, para quem reservou.
    envios = list(
        session.scalars(select(EnvioEmail).where(EnvioEmail.condominio_id == predio.condominio.id))
    )
    assert {e.recurso_id for e in envios} == {r.id for r in com_reservas["afetadas"]}
    assert all(
        e.evento == "reserva_cancelada"
        and e.recurso_tipo == "reserva"
        and e.status == "pendente"
        and e.destinatario == predio.morador.email
        for e in envios
    )

    # Auditoria: um `area.bloquear` e um `reserva.cancelar` por reserva.
    [bloqueio] = eventos(session, predio, "area.bloquear")
    assert bloqueio.depois["reservas_canceladas"] == 2
    cancelados = {e.recurso_id for e in eventos(session, predio, "reserva.cancelar")}
    assert cancelados == {r.id for r in com_reservas["afetadas"]}

    # O horário fica livre: a unidade reserva de novo noutra data, e a agenda mostra o bloqueio.
    assert contar(session, BloqueioArea, BloqueioArea.area_id == area.id) == 1


def test_bloqueio_preserva_cancelamento_ocorrido_apos_a_consulta(
    client, session, predio, area, adm, responsavel, monkeypatch
):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=18)
    consulta = RepositorioReservas.afetadas_por_bloqueio

    def consultar_e_simular_cancelamento(repo, *args, **kwargs):
        afetadas = consulta(repo, *args, **kwargs)
        # Reproduz a linha já carregada na sessão e a atualização posterior no banco.
        repo.session.execute(
            text(
                "UPDATE reservas SET status = 'cancelada', cancelada_em = now(), "
                "cancelada_por_usuario_id = :morador WHERE id = :reserva"
            ),
            {"morador": predio.morador.id, "reserva": reserva.id},
        )
        return afetadas

    monkeypatch.setattr(
        RepositorioReservas, "afetadas_por_bloqueio", consultar_e_simular_cancelamento
    )
    resposta = client.post(
        url(area),
        headers=adm,
        json=corpo(responsavel, DIA, DIA, confirmar_cancelamentos=True),
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["reservas_canceladas"] == 0
    session.refresh(reserva)
    assert reserva.cancelada_por_usuario_id == predio.morador.id
    assert reserva.cancelada_responsavel_id is None
    assert contar(session, Aviso, Aviso.condominio_id == predio.condominio.id) == 0
    assert contar(session, EnvioEmail, EnvioEmail.recurso_id == reserva.id) == 0
    [bloqueio] = eventos(session, predio, "area.bloquear")
    assert bloqueio.depois["reservas_canceladas"] == 0
    assert eventos(session, predio, "reserva.cancelar") == []


def test_confirmar_sem_reservas_afetadas_nao_cria_aviso_nem_email(
    client, session, predio, area, adm, responsavel
):
    resposta = client.post(
        url(area), headers=adm, json=corpo(responsavel, confirmar_cancelamentos=True)
    )
    assert resposta.status_code == 201 and resposta.json()["reservas_canceladas"] == 0
    assert contar(session, Aviso, Aviso.condominio_id == predio.condominio.id) == 0
    assert contar(session, EnvioEmail, EnvioEmail.condominio_id == predio.condominio.id) == 0


def test_um_aviso_por_unidade_mesmo_com_varias_reservas(
    client, session, predio, area, adm, responsavel
):
    for hora in (9, 10, 11):
        criar_reserva(
            session, predio, criar_area(session, predio, f"Área {hora}"), data=DIA, hora=hora
        )
    primeira = criar_reserva(session, predio, area, data=DIA, hora=12)
    segunda = criar_reserva(session, predio, area, data=DIA + timedelta(days=1), hora=12)
    resposta = client.post(
        url(area),
        headers=adm,
        json=corpo(responsavel, DIA, DIA + timedelta(days=1), confirmar_cancelamentos=True),
    )
    assert resposta.status_code == 201
    assert resposta.json()["reservas_canceladas"] == 2  # só as da área bloqueada
    avisos = list(session.scalars(select(Aviso).where(Aviso.condominio_id == predio.condominio.id)))
    assert len(avisos) == 1
    assert "12:00" in avisos[0].texto
    for reserva in (primeira, segunda):
        session.refresh(reserva)
        assert reserva.status == "cancelada"


def test_aviso_com_muitas_reservas_da_mesma_unidade_cabe_no_limite(
    client, session, predio, area, adm, responsavel
):
    for dia in range(40):
        criar_reserva(session, predio, area, data=DIA + timedelta(days=dia), hora=10)
    resposta = client.post(
        url(area),
        headers=adm,
        json=corpo(responsavel, DIA, DIA + timedelta(days=40), confirmar_cancelamentos=True),
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["reservas_canceladas"] == 40
    [aviso] = session.scalars(select(Aviso).where(Aviso.condominio_id == predio.condominio.id))
    assert "e mais 20" in aviso.texto and len(aviso.texto) <= 2000


def test_email_vai_para_quem_reservou_e_nao_para_o_outro_morador_da_unidade(
    client, session, predio, area, adm, responsavel
):
    usuario, _, _ = novo_morador(session, predio, predio.unidade_101, nome="Outra Pessoa")
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10, usuario=usuario)
    client.post(url(area), headers=adm, json=corpo(responsavel, confirmar_cancelamentos=True))
    [envio] = session.scalars(select(EnvioEmail).where(EnvioEmail.recurso_id == reserva.id))
    assert envio.destinatario == usuario.email


def test_falha_no_meio_nao_deixa_nada_gravado(
    client, session, predio, area, adm, responsavel, com_reservas, monkeypatch
):
    from app.modules.avisos import service as avisos

    def falha(*args, **kwargs):
        raise RuntimeError("falha no aviso")

    monkeypatch.setattr(avisos, "publicar_para_unidade", falha)
    session.commit()  # os dados do teste ficam; o rollback abaixo só desfaz o que a requisição fez
    cliente_sem_raise = type(client)(client.app, raise_server_exceptions=False)
    resposta = cliente_sem_raise.post(
        url(area),
        headers=adm,
        json=corpo(responsavel, DIA, DIA + timedelta(days=2), confirmar_cancelamentos=True),
    )
    assert resposta.status_code == 500
    session.rollback()  # o app de produção devolve a sessão ao pool sem commit
    assert contar(session, BloqueioArea) == 0
    for reserva in com_reservas["afetadas"]:
        session.refresh(reserva)
        assert reserva.status == "ativa"


# --- listagem ---------------------------------------------------------------------------------


def test_listar_traz_so_bloqueios_ativos_da_area_do_mais_recente_ao_mais_antigo(
    client, session, predio, area, adm
):
    antigo = criar_bloqueio(session, predio, area, DIA, DIA)
    novo = criar_bloqueio(session, predio, area, DIA + timedelta(days=10), DIA + timedelta(days=12))
    criar_bloqueio(session, predio, area, DIA, DIA, removido=True)
    criar_bloqueio(session, predio, criar_area(session, predio, "Quadra"), DIA, DIA)

    resposta = client.get(url(area), headers=adm)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert [i["id"] for i in dados["items"]] == [str(novo.id), str(antigo.id)]
    assert dados["total"] == 2 and dados["page"] == 1 and dados["page_size"] == 20
    assert set(dados["items"][0]) == {
        "id",
        "area_id",
        "data_inicio",
        "data_fim",
        "motivo",
        "responsavel",
        "criado_em",
    }


def test_listar_filtra_por_periodo_e_pagina(client, session, predio, area, adm):
    for deslocamento in (0, 10, 20):
        criar_bloqueio(
            session,
            predio,
            area,
            DIA + timedelta(days=deslocamento),
            DIA + timedelta(days=deslocamento + 1),
        )
    filtrada = client.get(
        url(area),
        headers=adm,
        params={
            "data_de": (DIA + timedelta(days=9)).isoformat(),
            "data_ate": (DIA + timedelta(days=11)).isoformat(),
        },
    )
    assert filtrada.json()["total"] == 1
    pagina = client.get(url(area), headers=adm, params={"page": 2, "page_size": 2}).json()
    assert pagina["total"] == 3 and len(pagina["items"]) == 1
    for ruim in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        assert client.get(url(area), headers=adm, params=ruim).status_code == 422


def test_bloqueio_removido_nao_vale_mais(client, session, predio, area, adm, responsavel):
    criar_bloqueio(session, predio, area, DIA, DIA, removido=True)
    morador = predio.cabecalho_de(Perfil.MORADOR)
    resposta = client.post(
        "/api/v1/reservas", headers=morador, json=pedido(area, predio.unidade_101)
    )
    assert resposta.status_code == 201


# --- e-mail no cancelamento pela Administração (US-605) ---------------------------------------


def test_cancelamento_pela_administracao_enfileira_o_email(
    client, session, predio, area, adm, responsavel
):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    resposta = client.post(
        f"/api/v1/reservas/{reserva.id}/cancelamento",
        headers=adm,
        json={"motivo": "Evento do condomínio", "responsavel_id": str(responsavel.id)},
    )
    assert resposta.status_code == 200, resposta.text
    [envio] = session.scalars(
        select(EnvioEmail).where(EnvioEmail.condominio_id == predio.condominio.id)
    )
    assert envio.evento == "reserva_cancelada"
    assert envio.recurso_tipo == "reserva" and envio.recurso_id == reserva.id
    assert envio.destinatario == predio.morador.email
    assert envio.status == "pendente" and envio.tentativas == 0


def test_cancelamento_pelo_morador_nao_enfileira_email(client, session, predio, area):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=10)
    resposta = client.post(
        f"/api/v1/reservas/{reserva.id}/cancelamento",
        headers=predio.cabecalho_de(Perfil.MORADOR),
        json={},
    )
    assert resposta.status_code == 200
    assert contar(session, EnvioEmail, EnvioEmail.condominio_id == predio.condominio.id) == 0


def test_cancelamento_recusado_nao_enfileira_email(client, session, predio, area, adm, responsavel):
    ja_cancelada = criar_reserva(session, predio, area, data=DIA, hora=10, status="cancelada")
    resposta = client.post(
        f"/api/v1/reservas/{ja_cancelada.id}/cancelamento",
        headers=adm,
        json={"motivo": "Evento", "responsavel_id": str(responsavel.id)},
    )
    assert resposta.status_code == 409
    assert contar(session, EnvioEmail, EnvioEmail.condominio_id == predio.condominio.id) == 0


# --- remoção de bloqueio ----------------------------------------------------------------------


def remocao(area, bloqueio):
    return url(area, f"bloqueios/{bloqueio.id}/remocao")


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_remocao_matriz_por_perfil(client, session, predio, area, responsavel, indice):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    headers = predio.cabecalho_de(PERFIS[indice])
    resposta = client.post(
        remocao(area, bloqueio), headers=headers, json={"responsavel_id": str(responsavel.id)}
    )
    esperado = 200 if PERFIS[indice] == Perfil.ADMINISTRACAO else 403
    assert resposta.status_code == esperado, resposta.text
    session.refresh(bloqueio)
    assert (bloqueio.removido_em is not None) == (esperado == 200)


def test_remocao_sem_token_e_401(client, session, predio, area):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    assert client.post(remocao(area, bloqueio), json={}).status_code == 401


def test_remover_grava_remocao_audita_e_responde(client, session, predio, area, adm, responsavel):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA + timedelta(days=2))
    resposta = client.post(
        remocao(area, bloqueio), headers=adm, json={"responsavel_id": str(responsavel.id)}
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["id"] == str(bloqueio.id)
    assert dados["removido_em"]
    assert dados["data_inicio"] == DIA.isoformat()
    session.refresh(bloqueio)
    assert bloqueio.removido_em is not None
    assert bloqueio.removido_por_usuario_id == predio.administracao.id
    [evento] = eventos(session, predio, "area.desbloquear")
    assert evento.recurso_id == area.id
    assert evento.antes["bloqueio_id"] == str(bloqueio.id)
    assert evento.depois == {"bloqueio_id": str(bloqueio.id), "removido": True}


def test_bloqueio_removido_some_da_lista_e_libera_a_data(
    client, session, predio, area, adm, responsavel
):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    corpo_reserva = pedido(area, predio.unidade_101, DIA, "10:00")
    morador = predio.cabecalho_de(Perfil.MORADOR)
    assert client.post("/api/v1/reservas", headers=morador, json=corpo_reserva).status_code == 409

    client.post(remocao(area, bloqueio), headers=adm, json={"responsavel_id": str(responsavel.id)})

    assert client.get(url(area), headers=adm).json()["total"] == 0
    assert client.post("/api/v1/reservas", headers=morador, json=corpo_reserva).status_code == 201


def test_remover_duas_vezes_e_409(client, session, predio, area, adm, responsavel):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    corpo_remocao = {"responsavel_id": str(responsavel.id)}
    assert client.post(remocao(area, bloqueio), headers=adm, json=corpo_remocao).status_code == 200
    segunda = client.post(remocao(area, bloqueio), headers=adm, json=corpo_remocao)
    assert segunda.status_code == 409
    assert erro(segunda)["reason"] == "bloqueio_ja_removido"
    assert len(eventos(session, predio, "area.desbloquear")) == 1


def test_remover_bloqueio_que_ja_estava_removido_e_409(
    client, session, predio, area, adm, responsavel
):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA, removido=True)
    resposta = client.post(
        remocao(area, bloqueio), headers=adm, json={"responsavel_id": str(responsavel.id)}
    )
    assert resposta.status_code == 409
    assert eventos(session, predio, "area.desbloquear") == []


def test_remover_nao_desfaz_reservas_canceladas(client, session, predio, area, adm, responsavel):
    reserva = criar_reserva(session, predio, area, data=DIA, hora=18)
    resposta = client.post(
        url(area), headers=adm, json=corpo(responsavel, confirmar_cancelamentos=True)
    )
    assert resposta.status_code == 201, resposta.text
    bloqueio_id = resposta.json()["id"]

    remover = client.post(
        url(area, f"bloqueios/{bloqueio_id}/remocao"),
        headers=adm,
        json={"responsavel_id": str(responsavel.id)},
    )
    assert remover.status_code == 200
    session.refresh(reserva)
    assert reserva.status == "cancelada"


def test_remocao_de_bloqueio_inexistente_ou_de_outra_area_e_404(
    client, session, predio, area, adm, responsavel
):
    corpo_remocao = {"responsavel_id": str(responsavel.id)}
    desconhecido = url(area, f"bloqueios/{uuid.uuid4()}/remocao")
    assert client.post(desconhecido, headers=adm, json=corpo_remocao).status_code == 404

    outra_area = criar_area(session, predio, nome="Quadra")
    bloqueio = criar_bloqueio(session, predio, outra_area, DIA, DIA)
    assert client.post(remocao(area, bloqueio), headers=adm, json=corpo_remocao).status_code == 404
    session.refresh(bloqueio)
    assert bloqueio.removido_em is None


def test_remocao_isolada_por_condominio(
    client, session, predio, outro_predio, area, adm, responsavel
):
    alheia = criar_area(session, outro_predio)
    alheio = criar_bloqueio(session, outro_predio, alheia, DIA, DIA)
    corpo_remocao = {"responsavel_id": str(responsavel.id)}
    assert client.post(remocao(alheia, alheio), headers=adm, json=corpo_remocao).status_code == 404
    assert client.post(remocao(area, alheio), headers=adm, json=corpo_remocao).status_code == 404
    session.refresh(alheio)
    assert alheio.removido_em is None


def test_remocao_com_responsavel_de_outro_condominio_ou_inativo_e_404(
    client, session, predio, outro_predio, area, adm
):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    alheio = criar_responsavel(session, outro_predio)
    inativo = criar_responsavel(session, predio, "Inativo", ativo=False)
    for responsavel_id in (alheio.id, inativo.id, uuid.uuid4()):
        resposta = client.post(
            remocao(area, bloqueio), headers=adm, json={"responsavel_id": str(responsavel_id)}
        )
        assert resposta.status_code == 404
    session.refresh(bloqueio)
    assert bloqueio.removido_em is None


@pytest.mark.parametrize("json", [{}, {"responsavel_id": "nao-e-uuid"}, {"responsavel_id": None}])
def test_remocao_com_corpo_invalido_e_422(client, session, predio, area, adm, json):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    assert client.post(remocao(area, bloqueio), headers=adm, json=json).status_code == 422


def test_remocao_recusa_campo_desconhecido(client, session, predio, area, adm, responsavel):
    bloqueio = criar_bloqueio(session, predio, area, DIA, DIA)
    resposta = client.post(
        remocao(area, bloqueio),
        headers=adm,
        json={"responsavel_id": str(responsavel.id), "removido_em": "2020-01-01T00:00:00Z"},
    )
    assert resposta.status_code == 422
