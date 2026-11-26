"""O laço do worker e a exclusão entre dois workers (SKIP LOCKED), sem fixture de rollback."""

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.notificacoes import repository, worker
from app.modules.notificacoes.models import EnvioEmail

pytestmark = pytest.mark.postgres


def test_laco_roda_a_cada_intervalo_e_sobrevive_a_erro(monkeypatch):
    chamadas: list[int] = []

    def rodada(settings, backend=None):
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("falha inesperada")

    monkeypatch.setattr(worker, "rodar_uma_vez", rodada)
    settings = Settings(email_worker_intervalo_seconds=1)

    async def executar():
        tarefa = asyncio.create_task(worker.laco(settings))
        await asyncio.sleep(1.5)
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    asyncio.run(executar())
    assert len(chamadas) >= 2  # o erro da primeira não parou o laço


def test_a_api_so_liga_o_worker_quando_configurada(monkeypatch):
    iniciado: list[bool] = []

    async def laco_falso(settings):
        iniciado.append(True)
        await asyncio.sleep(3600)

    import app.main as principal

    monkeypatch.setattr(principal, "laco", laco_falso)
    for ativo in (False, True):
        iniciado.clear()
        monkeypatch.setattr(
            principal, "get_settings", lambda a=ativo: Settings(email_worker_ativo=a)
        )
        with TestClient(principal.create_app()):
            pass
        assert iniciado == ([True] if ativo else [])


def test_dois_workers_nao_pegam_o_mesmo_envio():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    # Sem condomínio: a fila é do sistema e o envio não depende de nenhuma outra linha.
    destino = f"{uuid.uuid4().hex[:8]}@exemplo.test"
    with Session(engine) as semeadura:
        envio = EnvioEmail(destinatario=destino, evento="condominio_aprovado")
        semeadura.add(envio)
        semeadura.commit()
        envio_id = envio.id
    try:
        with Session(engine) as primeiro, Session(engine) as segundo:
            # Os envios de outros testes, se houver, também aparecem: marcamos os que já vimos.
            vistos: set[uuid.UUID] = set()
            while True:
                pego = repository.proximo_pendente(primeiro, max_tentativas=3, ignorar=vistos)
                assert pego is not None
                if pego.id == envio_id:
                    break
                vistos.add(pego.id)
            outro = repository.proximo_pendente(segundo, max_tentativas=3, ignorar=vistos)
            assert outro is None or outro.id != envio_id  # o travado é pulado, não esperado
            segundo.rollback()
            primeiro.rollback()
    finally:
        with engine.begin() as conexao:
            conexao.execute(text("DELETE FROM envios_email WHERE id = :i"), {"i": envio_id})
        engine.dispose()
