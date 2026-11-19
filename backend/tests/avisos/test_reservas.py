import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.avisos import service as avisos
from app.modules.avisos.models import Aviso
from app.modules.reservas.models import Reserva
from tests.reservas.cenario import AGORA, DIA, criar_area, criar_reserva, criar_responsavel

pytestmark = pytest.mark.postgres


def preparar(session, predio):
    reserva = criar_reserva(session, predio, criar_area(session, predio), data=DIA, hora=10)
    responsavel = criar_responsavel(session, predio)
    session.commit()
    return reserva, {"responsavel_id": str(responsavel.id), "motivo": "Manutenção emergencial"}


def test_cancelamento_administrativo_publica_para_unidade(client, session, predio):
    reserva, dados = preparar(session, predio)
    resposta = client.post(
        f"/api/v1/reservas/{reserva.id}/cancelamento",
        headers=predio.cabecalho_de("administracao"),
        json=dados,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["status"] == "cancelada"
    aviso = session.scalars(select(Aviso).where(Aviso.condominio_id == predio.condominio.id)).one()
    assert aviso.unidade_id == reserva.unidade_id
    assert aviso.responsavel_id == uuid.UUID(dados["responsavel_id"])
    assert dados["motivo"] in aviso.texto
    assert f"{DIA:%d/%m/%Y}" in aviso.texto and "10:00" in aviso.texto
    assert aviso.importante is True
    assert aviso.inicio_em == AGORA and aviso.fim_em == AGORA + timedelta(days=7)
    registros = list(
        session.scalars(
            select(RegistroAuditoria)
            .where(RegistroAuditoria.condominio_id == predio.condominio.id)
            .order_by(RegistroAuditoria.id)
        )
    )
    assert [r.acao for r in registros] == ["aviso.publicar", "reserva.cancelar"]
    assert registros[0].recurso_id == aviso.id
    assert registros[1].recurso_id == reserva.id
    assert all(
        r.responsavel_nome == resposta.json()["cancelamento"]["responsavel"]["nome"]
        for r in registros
    )
    for perfil, quantidade in [("morador", 1), ("funcionario", 0), ("administracao", 1)]:
        consulta = client.get("/api/v1/avisos", headers=predio.cabecalho_de(perfil))
        assert consulta.status_code == 200
        assert consulta.json()["total"] == quantidade
    # A reserva e o aviso sobrevivem a uma nova transação.
    aviso_id, reserva_id = aviso.id, reserva.id
    session.rollback()
    assert session.get(Aviso, aviso_id) is not None
    assert session.get(Reserva, reserva_id).status == "cancelada"
    assert (
        client.post(
            f"/api/v1/reservas/{reserva.id}/cancelamento",
            headers=predio.cabecalho_de("administracao"),
            json=dados,
        ).status_code
        == 409
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(Aviso)
            .where(Aviso.condominio_id == predio.condominio.id)
        )
        == 1
    )


def test_cancelamento_morador_nao_publica_aviso(client, session, predio):
    reserva, _ = preparar(session, predio)
    resposta = client.post(
        f"/api/v1/reservas/{reserva.id}/cancelamento",
        headers=predio.cabecalho_de("morador"),
        json={},
    )
    assert resposta.status_code == 200
    assert (
        session.scalar(
            select(func.count())
            .select_from(Aviso)
            .where(Aviso.condominio_id == predio.condominio.id)
        )
        == 0
    )


@pytest.mark.parametrize("etapa", ["aviso", "aviso.publicar", "reserva.cancelar"])
def test_falha_reverte_reserva_aviso_e_eventos(client, session, predio, monkeypatch, etapa):
    reserva, dados = preparar(session, predio)
    reserva_id = reserva.id
    if etapa == "aviso":
        publicar = avisos.publicar_para_unidade

        def falhar(*args, **kwargs):
            publicar(*args, **kwargs)
            raise RuntimeError("Falha simulada após persistir o aviso")

        monkeypatch.setattr(avisos, "publicar_para_unidade", falhar)
    else:
        registrar = auditoria.registrar_acao

        def falhar_evento(*args, **kwargs):
            registrar(*args, **kwargs)
            if kwargs["acao"] == etapa:
                raise RuntimeError("Falha simulada após persistir o evento")

        monkeypatch.setattr(auditoria, "registrar_acao", falhar_evento)
    resposta = client.post(
        f"/api/v1/reservas/{reserva_id}/cancelamento",
        headers=predio.cabecalho_de("administracao"),
        json=dados,
    )
    assert resposta.status_code == 500
    session.expire_all()
    persistida = session.get(Reserva, reserva_id)
    assert persistida.status == "ativa"
    assert persistida.cancelada_em is None and persistida.motivo_cancelamento is None
    assert (
        session.scalar(
            select(func.count())
            .select_from(Aviso)
            .where(Aviso.condominio_id == predio.condominio.id)
        )
        == 0
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.condominio_id == predio.condominio.id)
        )
        == 0
    )
