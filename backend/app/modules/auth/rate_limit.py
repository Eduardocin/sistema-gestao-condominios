"""Limite de tentativas de login (proteção contra força bruta).

A regra é a mesma sugerida para a chave de acesso: depois de N erros seguidos, a conta fica
bloqueada por alguns minutos e a API responde 429.

Atenção: o controle fica na memória do processo. Com um único servidor (nosso caso hoje) isso
funciona bem; se um dia rodarmos várias réplicas, cada uma terá o próprio contador e o certo
é mover isto para o Redis ou para uma tabela. A interface (`bloqueio_restante`,
`registrar_falha`, `limpar`) já foi pensada para essa troca ser fácil.
"""

import threading
import time
from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_falhas: int,
        bloqueio_segundos: int,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_falhas = max_falhas
        self._bloqueio_segundos = bloqueio_segundos
        # `relogio` é injetável para os testes avançarem o tempo sem dormir de verdade.
        self._relogio = relogio
        self._lock = threading.Lock()
        # chave -> instantes (no relógio acima) das falhas ainda dentro da janela
        self._falhas: dict[str, list[float]] = {}
        # chave -> instante em que o bloqueio termina
        self._bloqueado_ate: dict[str, float] = {}

    def bloqueio_restante(self, chave: str) -> int:
        """Segundos até poder tentar de novo (0 se a chave não está bloqueada)."""
        with self._lock:
            agora = self._relogio()
            ate = self._bloqueado_ate.get(chave)
            if ate is None:
                return 0
            if ate <= agora:
                # O bloqueio acabou: esquecemos a chave para a memória não crescer à toa.
                del self._bloqueado_ate[chave]
                return 0
            return int(ate - agora) + 1

    def registrar_falha(self, chave: str) -> None:
        with self._lock:
            agora = self._relogio()
            janela_inicio = agora - self._bloqueio_segundos
            # Só contam as falhas recentes; erros antigos "expiram" sozinhos.
            recentes = [t for t in self._falhas.get(chave, []) if t > janela_inicio]
            recentes.append(agora)
            if len(recentes) >= self._max_falhas:
                self._bloqueado_ate[chave] = agora + self._bloqueio_segundos
                self._falhas.pop(chave, None)
            else:
                self._falhas[chave] = recentes

    def limpar(self, chave: str) -> None:
        """Login bem-sucedido zera o histórico de erros da chave."""
        with self._lock:
            self._falhas.pop(chave, None)
            self._bloqueado_ate.pop(chave, None)

    def resetar(self) -> None:
        """Esquece tudo. Existe para os testes não se contaminarem entre si."""
        with self._lock:
            self._falhas.clear()
            self._bloqueado_ate.clear()


@lru_cache
def get_login_rate_limiter() -> LoginRateLimiter:
    """Uma instância única por processo, criada com os limites das configurações."""
    settings = get_settings()
    return LoginRateLimiter(
        max_falhas=settings.login_max_failures,
        bloqueio_segundos=settings.login_lockout_minutes * 60,
    )
