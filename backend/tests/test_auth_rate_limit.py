from app.modules.auth.rate_limit import LoginRateLimiter


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def criar(max_falhas: int = 3, bloqueio: int = 60):
    relogio = RelogioFalso()
    return LoginRateLimiter(max_falhas=max_falhas, bloqueio_segundos=bloqueio, relogio=relogio), (
        relogio
    )


def test_bloqueia_apos_o_limite_de_falhas():
    limiter, _ = criar()
    for _ in range(2):
        limiter.registrar_falha("ana@exemplo.com")
        assert limiter.bloqueio_restante("ana@exemplo.com") == 0
    limiter.registrar_falha("ana@exemplo.com")
    assert limiter.bloqueio_restante("ana@exemplo.com") > 0


def test_bloqueio_expira_com_o_tempo():
    limiter, relogio = criar()
    for _ in range(3):
        limiter.registrar_falha("ana@exemplo.com")
    relogio.agora += 61
    assert limiter.bloqueio_restante("ana@exemplo.com") == 0


def test_falhas_antigas_nao_somam():
    limiter, relogio = criar()
    limiter.registrar_falha("ana@exemplo.com")
    limiter.registrar_falha("ana@exemplo.com")
    relogio.agora += 120  # as duas falhas já saíram da janela
    limiter.registrar_falha("ana@exemplo.com")
    assert limiter.bloqueio_restante("ana@exemplo.com") == 0


def test_limpar_zera_o_historico():
    limiter, _ = criar()
    limiter.registrar_falha("ana@exemplo.com")
    limiter.registrar_falha("ana@exemplo.com")
    limiter.limpar("ana@exemplo.com")
    limiter.registrar_falha("ana@exemplo.com")
    assert limiter.bloqueio_restante("ana@exemplo.com") == 0


def test_chaves_sao_independentes():
    limiter, _ = criar()
    for _ in range(3):
        limiter.registrar_falha("ana@exemplo.com")
    assert limiter.bloqueio_restante("bia@exemplo.com") == 0
