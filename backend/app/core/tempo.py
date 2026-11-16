"""Relógio da aplicação no fuso do condomínio (convencoes.md, seção 1).

MVP: um fuso fixo para todos os condomínios. Quem precisa de "agora" recebe um `Relogio` por
parâmetro ou pela dependência `get_relogio`, para os testes poderem congelar o tempo.
"""

from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

FUSO_CONDOMINIO = ZoneInfo("America/Sao_Paulo")

Relogio = Callable[[], datetime]


def agora() -> datetime:
    """Agora, com fuso, em America/Sao_Paulo."""
    return datetime.now(FUSO_CONDOMINIO)


def get_relogio() -> Relogio:
    """Dependência FastAPI. Os testes trocam com `app.dependency_overrides[get_relogio]`."""
    return agora


def no_fuso(momento: datetime) -> datetime:
    """Converte para o fuso do condomínio (um relógio de teste pode devolver UTC)."""
    return momento.astimezone(FUSO_CONDOMINIO)


def inicio_do_slot(data: date, hora: time) -> datetime:
    """Data + hora de negócio (sem fuso) viram um instante no fuso do condomínio."""
    return datetime.combine(data, hora, tzinfo=FUSO_CONDOMINIO)
