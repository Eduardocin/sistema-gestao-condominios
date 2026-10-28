import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.modules.auth.security import (
    TipoToken,
    TokenInvalido,
    decodificar_token,
    emitir_token,
    hash_senha,
    precisa_rehash,
    segundos_de_validade,
    verificar_senha,
)

SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres-ok"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, jwt_secret_key=SEGREDO)


def emitir(
    settings: Settings,
    tipo: TipoToken = TipoToken.ACCESS,
    *,
    usuario_id: uuid.UUID | None = None,
    condominio_id: uuid.UUID | None = ...,  # type: ignore[assignment]
    sessao_versao: int = 1,
    perfil: str | None = "morador",
    agora: datetime | None = None,
) -> str:
    """Atalho para emitir tokens de teste. `condominio_id=None` significa "sem cid"."""
    return emitir_token(
        tipo=tipo,
        usuario_id=usuario_id or uuid.uuid4(),
        condominio_id=uuid.uuid4() if condominio_id is ... else condominio_id,
        sessao_versao=sessao_versao,
        perfil=perfil,
        settings=settings,
        agora=agora,
    )


def test_hash_nao_guarda_a_senha_pura_e_verifica():
    senha_hash = hash_senha("Senha#Forte123")
    assert senha_hash.startswith("$argon2id$")
    assert "Senha#Forte123" not in senha_hash
    assert verificar_senha("Senha#Forte123", senha_hash)
    assert not verificar_senha("outra-senha", senha_hash)


def test_mesma_senha_gera_hashes_diferentes():
    assert hash_senha("abc12345") != hash_senha("abc12345")


def test_hash_invalido_vira_false_em_vez_de_excecao():
    assert verificar_senha("qualquer", "isto-nao-e-um-hash") is False


def test_hash_recente_nao_precisa_de_rehash():
    assert precisa_rehash(hash_senha("abc12345")) is False


def test_token_de_acesso_ida_e_volta(settings):
    usuario_id, condominio_id = uuid.uuid4(), uuid.uuid4()
    token = emitir(settings, usuario_id=usuario_id, condominio_id=condominio_id, sessao_versao=3)
    claims = decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)
    assert claims.usuario_id == usuario_id
    assert claims.condominio_id == condominio_id
    assert claims.sessao_versao == 3
    assert claims.perfil == "morador"


def test_token_sem_condominio_nao_tem_cid(settings):
    token = emitir(settings, condominio_id=None, perfil=None)
    payload = jwt.decode(token, SEGREDO, algorithms=["HS256"])
    assert "cid" not in payload
    assert "perfil" not in payload
    claims = decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)
    assert claims.condominio_id is None


def test_validade_do_access_e_do_refresh(settings):
    assert segundos_de_validade(TipoToken.ACCESS, settings) == 15 * 60
    assert segundos_de_validade(TipoToken.REFRESH, settings) == 7 * 24 * 60 * 60
    payload = jwt.decode(emitir(settings), SEGREDO, algorithms=["HS256"])
    assert payload["exp"] - payload["iat"] == 15 * 60


def test_token_expirado_e_recusado(settings):
    passado = datetime.now(UTC) - timedelta(hours=1)
    token = emitir(settings, agora=passado)
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)


def test_refresh_nao_vale_como_access_e_vice_versa(settings):
    refresh = emitir(settings, TipoToken.REFRESH)
    access = emitir(settings, TipoToken.ACCESS)
    with pytest.raises(TokenInvalido):
        decodificar_token(refresh, tipo_esperado=TipoToken.ACCESS, settings=settings)
    with pytest.raises(TokenInvalido):
        decodificar_token(access, tipo_esperado=TipoToken.REFRESH, settings=settings)


def test_assinatura_adulterada_e_recusada(settings):
    token = emitir(settings)
    outro = Settings(_env_file=None, jwt_secret_key="outro-segredo-tambem-com-mais-de-32-chars")
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=outro)


def test_algoritmo_none_e_recusado(settings):
    agora = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "sv": 1,
        "typ": "access",
        "iat": agora,
        "exp": agora + 600,
    }
    token = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)


@pytest.mark.parametrize("faltando", ["sub", "sv", "typ", "exp", "iat"])
def test_token_sem_claim_obrigatoria_e_recusado(settings, faltando):
    agora = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "sv": 1,
        "typ": "access",
        "iat": agora,
        "exp": agora + 600,
    }
    del payload[faltando]
    token = jwt.encode(payload, SEGREDO, algorithm="HS256")
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)


@pytest.mark.parametrize("sv", [True, "1", 1.5])
def test_sv_com_tipo_errado_e_recusado(settings, sv):
    agora = int(datetime.now(UTC).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "sv": sv,
        "typ": "access",
        "iat": agora,
        "exp": agora + 600,
    }
    token = jwt.encode(payload, SEGREDO, algorithm="HS256")
    with pytest.raises(TokenInvalido):
        decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)


def test_lixo_no_lugar_do_token_e_recusado(settings):
    with pytest.raises(TokenInvalido):
        decodificar_token("nao.e.um.jwt", tipo_esperado=TipoToken.ACCESS, settings=settings)
