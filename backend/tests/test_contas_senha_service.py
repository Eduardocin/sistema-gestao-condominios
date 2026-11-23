"""Testes sem banco externo para sessão, rate limit e revogação na troca/redefinição."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_session
from app.main import create_app
from app.modules.auth import repository as auth_repository
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.auth.rate_limit import LoginRateLimiter, get_login_rate_limiter
from app.modules.auth.security import TipoToken, decodificar_token, hash_do_token, hash_senha
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.contas import repository as contas_repository
from app.modules.contas import service as contas_service
from app.modules.usuarios.models import Usuario

SENHA = "SenhaFicticia123"
NOVA = "OutraSenha456"
HASH_ATUAL = hash_senha(SENHA)


def _usuario(*, sessao_versao: int = 1) -> Usuario:
    return Usuario(
        id=uuid.uuid4(),
        nome="Ana Martins",
        email="ana.martins@exemplo.test",
        telefone="11987654321",
        tipo_cadastro="morador",
        senha_hash=HASH_ATUAL,
        ativo=True,
        administrador_plataforma=False,
        sessao_versao=sessao_versao,
    )


def _condominio(nome: str, *, status: str = "ativo") -> Condominio:
    return Condominio(id=uuid.uuid4(), nome=nome, status=status)


def _vinculo(
    usuario_id: uuid.UUID, condominio_id: uuid.UUID, perfil: str = "morador"
) -> VinculoCondominio:
    return VinculoCondominio(
        id=uuid.uuid4(),
        usuario_id=usuario_id,
        condominio_id=condominio_id,
        perfil=perfil,
        ativo=True,
    )


def test_redefinicao_limpa_bloqueios_do_rate_limiter_somente_apos_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usuario = _usuario()
    token = "token-recuperacao-valido"
    token_hash = hash_do_token(token)
    limiter = LoginRateLimiter(max_falhas=2, bloqueio_segundos=900)
    for _ in range(2):
        limiter.registrar_falha(usuario.email)
        limiter.registrar_falha(f"senha:{usuario.id}")
    assert limiter.bloqueio_restante(usuario.email) > 0
    assert limiter.bloqueio_restante(f"senha:{usuario.id}") > 0

    session = MagicMock()
    monkeypatch.setattr(
        contas_repository,
        "obter_usuario_id_token_recuperacao",
        lambda _s, h: usuario.id if h == token_hash else None,
    )
    monkeypatch.setattr(contas_repository, "obter_conta_travada", lambda _s, _uid: usuario)
    monkeypatch.setattr(contas_repository, "consumir_token_recuperacao", lambda _s, _h: usuario.id)
    monkeypatch.setattr(
        contas_repository, "gravar_senha", lambda _s, u, novo: setattr(u, "senha_hash", novo)
    )
    monkeypatch.setattr(contas_repository, "inutilizar_tokens_pendentes", lambda _s, _uid: None)
    monkeypatch.setattr(contas_service.auditoria, "registrar_acao", lambda *_a, **_kw: None)

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter

    with TestClient(app, raise_server_exceptions=False) as client:
        # Senha fraca faz rollback e NÃO limpa o bloqueio
        fraca = client.post(
            "/api/v1/contas/redefinicao-senha",
            json={"token": token, "senha_nova": usuario.email},
        )
        assert fraca.status_code == 422
        assert limiter.bloqueio_restante(usuario.email) > 0
        assert limiter.bloqueio_restante(f"senha:{usuario.id}") > 0

        # Redefinição confirmada limpa ambos os bloqueios
        ok = client.post(
            "/api/v1/contas/redefinicao-senha",
            json={"token": token, "senha_nova": NOVA},
        )
        assert ok.status_code == 204
        assert limiter.bloqueio_restante(usuario.email) == 0
        assert limiter.bloqueio_restante(f"senha:{usuario.id}") == 0


def test_troca_senha_preserva_condominio_selecionado_e_inutiliza_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usuario = _usuario()
    aurora = _condominio("Aurora")
    boa_vista = _condominio("Boa Vista")
    vinculos = [
        (_vinculo(usuario.id, aurora.id), aurora),
        (_vinculo(usuario.id, boa_vista.id), boa_vista),
    ]
    inutilizados: list[uuid.UUID] = []
    session = MagicMock()

    def _gravar(_s: object, u: Usuario, novo: str) -> None:
        u.senha_hash = novo
        u.sessao_versao += 1

    monkeypatch.setattr(contas_repository, "bloquear_conta", lambda _s, _uid: usuario)
    monkeypatch.setattr(contas_repository, "gravar_senha", _gravar)
    monkeypatch.setattr(
        contas_repository,
        "inutilizar_tokens_pendentes",
        lambda _s, uid: inutilizados.append(uid),
    )
    monkeypatch.setattr(auth_repository, "listar_vinculos_ativos", lambda _s, _uid: vinculos)
    monkeypatch.setattr(contas_service.auditoria, "registrar_acao", lambda *_a, **_kw: None)

    app = create_app()
    limiter = LoginRateLimiter(max_falhas=5, bloqueio_segundos=900)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_usuario_autenticado] = lambda: UsuarioAutenticado(
        usuario=usuario,
        condominio_id=boa_vista.id,
    )

    with TestClient(app) as client:
        resposta = client.put(
            "/api/v1/contas/me/senha",
            json={"senha_atual": SENHA, "senha_nova": NOVA},
        )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["condominio"]["id"] == str(boa_vista.id)
    assert corpo["requer_selecao"] is False
    claims = decodificar_token(
        corpo["access_token"], tipo_esperado=TipoToken.ACCESS, settings=get_settings()
    )
    assert claims.condominio_id == boa_vista.id
    assert inutilizados == [usuario.id]


def test_troca_senha_rejeita_sessao_revogada_em_corrida(monkeypatch: pytest.MonkeyPatch) -> None:
    usuario_jwt = _usuario(sessao_versao=1)
    usuario_banco = _usuario(sessao_versao=2)
    usuario_banco.id = usuario_jwt.id
    session = MagicMock()
    limiter = LoginRateLimiter(max_falhas=5, bloqueio_segundos=900)

    monkeypatch.setattr(contas_repository, "bloquear_conta", lambda _s, _uid: usuario_banco)

    with pytest.raises(ApiError) as exc_info:
        contas_service.trocar_propria_senha(
            session,
            usuario_jwt,
            contas_service.TrocaSenha(senha_atual=SENHA, senha_nova=NOVA),
            limiter=limiter,
            settings=get_settings(),
            ip="203.0.113.53",
        )
    assert exc_info.value.status_code == 401
