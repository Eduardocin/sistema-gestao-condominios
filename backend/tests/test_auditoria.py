import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import EventoAuditoria
from app.modules.auditoria import repository, service
from app.modules.auditoria.models import TipoEventoAuditoria


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'auditoria.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize("tipo_evento", list(TipoEventoAuditoria))
def test_log_insere_exatamente_um_evento_por_acao_critica(session, tipo_evento):
    evento = service.log(
        session,
        tipo_evento=tipo_evento,
        recurso="teste",
        usuario_id=None,
        ator="usuario@exemplo.test" if tipo_evento == TipoEventoAuditoria.FALHA_LOGIN else None,
    )

    assert (
        session.scalar(
            select(func.count()).select_from(EventoAuditoria).where(EventoAuditoria.id == evento.id)
        )
        == 1
    )
    assert repository.obter_por_id(session, evento.id) is evento


def test_log_exige_nome_da_pessoa_em_conta_compartilhada(session):
    with pytest.raises(ValueError, match="nome_responsavel é obrigatório"):
        service.log(
            session,
            tipo_evento=TipoEventoAuditoria.RESERVA,
            recurso="reserva",
            conta_compartilhada=True,
        )

    assert session.scalar(select(func.count()).select_from(EventoAuditoria)) == 0


@pytest.mark.parametrize("perfil", ["administracao", "funcionario"])
def test_log_deriva_conta_compartilhada_do_perfil_e_exige_responsavel(session, perfil):
    with pytest.raises(ValueError, match="nome_responsavel é obrigatório"):
        service.log(
            session,
            tipo_evento=TipoEventoAuditoria.RESERVA,
            recurso="reserva",
            perfil=perfil,
        )

    evento = service.log(
        session,
        tipo_evento=TipoEventoAuditoria.RESERVA,
        recurso="reserva",
        perfil=perfil,
        nome_responsavel="Responsável de teste",
    )
    assert evento.conta_compartilhada is True
    assert evento.nome_responsavel == "Responsável de teste"


def test_log_grava_responsavel_e_dados_antes_depois(session):
    condominio_id = uuid.uuid4()

    evento = service.log(
        session,
        tipo_evento=TipoEventoAuditoria.OCORRENCIA,
        recurso="ocorrencia",
        condominio_id=condominio_id,
        conta_compartilhada=True,
        nome_responsavel="  Ana Martins  ",
        dados_antes={"status": "aberta"},
        dados_depois={"status": "resolvida"},
        ip="2001:db8::1",
    )

    assert evento.nome_responsavel == "Ana Martins"
    assert evento.dados_antes == {"status": "aberta"}
    assert evento.dados_depois == {"status": "resolvida"}
    assert evento.ip == "2001:db8::1"
