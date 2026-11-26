"""O laço que esvazia a fila `envios_email` (US-803).

Roda no processo da API quando `EMAIL_WORKER_ATIVO=true` (lifespan), ou sozinho com
`python -m app.modules.notificacoes.worker`. Sem Redis nem Celery (ADR 0001): a própria fila no
PostgreSQL basta, e `SKIP LOCKED` deixa mais de um worker rodar sem enviar em dobro.
"""

import asyncio
import logging

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.modules.notificacoes import service
from app.modules.notificacoes.smtp import EmailBackend, obter_backend

logger = logging.getLogger(__name__)


def rodar_uma_vez(settings: Settings, backend: EmailBackend | None = None) -> None:
    resultado = service.processar_pendentes(
        get_session_factory(),
        backend or obter_backend(settings),
        max_tentativas=settings.email_max_tentativas,
    )
    if resultado.enviados or resultado.falhas:
        logger.info("Fila de e-mail: %s", resultado.model_dump())


async def laco(settings: Settings) -> None:
    """Uma rodada a cada intervalo. Erro inesperado vai para o log e o laço continua."""
    backend = obter_backend(settings)
    while True:
        try:
            await asyncio.to_thread(rodar_uma_vez, settings, backend)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha inesperada no worker de e-mail")
        await asyncio.sleep(settings.email_worker_intervalo_seconds)


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(laco(get_settings()))
