"""Peças de segurança do login: hash de senha (argon2id) e tokens JWT.

Este arquivo não conhece banco nem HTTP, só recebe valores e devolve valores. Isso deixa tudo
fácil de testar e reaproveitar (por exemplo, na autorização central da TASK-19).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Senhas
# ---------------------------------------------------------------------------

# argon2id com os parâmetros padrão da biblioteca (recomendados pela OWASP). Se algum dia
# endurecermos os parâmetros, `precisa_rehash` avisa e o login regrava o hash sozinho.
_hasher = PasswordHasher()

# Hash descartável, usado só para "gastar o mesmo tempo" quando o e-mail não existe.
_HASH_FICTICIO = _hasher.hash("senha-ficticia-so-para-igualar-o-tempo-de-resposta")


def hash_senha(senha: str) -> str:
    """Gera o hash argon2id da senha (com salt aleatório embutido no resultado)."""
    return _hasher.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    """Confere a senha contra o hash. Qualquer problema vira `False`, nunca uma exceção."""
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerificationError, InvalidHashError):
        # VerificationError cobre senha errada; InvalidHashError cobre hash corrompido ou
        # em formato desconhecido. Para quem chama, os dois significam "não entra".
        return False


def precisa_rehash(senha_hash: str) -> bool:
    """Diz se o hash foi gerado com parâmetros mais fracos que os atuais."""
    return _hasher.check_needs_rehash(senha_hash)


def gastar_tempo_de_verificacao(senha: str) -> None:
    """Faz uma verificação inútil para o tempo de resposta ser igual ao de um usuário real.

    Sem isso, "e-mail não existe" responderia em milissegundos e "senha errada" em dezenas deles,
    e dava para descobrir quais e-mails têm conta só medindo o tempo.
    """
    verificar_senha(senha, _HASH_FICTICIO)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


class TipoToken(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenInvalido(Exception):
    """Token malformado, adulterado, expirado ou do tipo errado."""


@dataclass(frozen=True)
class ClaimsToken:
    """O que o token diz sobre quem o usa. Só identidade: permissões vêm sempre do banco."""

    usuario_id: uuid.UUID
    condominio_id: uuid.UUID | None
    sessao_versao: int
    # Só para a interface esconder menus. Nunca use isto para decidir acesso.
    perfil: str | None
    tipo: TipoToken


# Claims que todo token nosso precisa ter; se faltar qualquer um, o token é recusado.
_CLAIMS_OBRIGATORIAS = ["exp", "iat", "sub", "sv", "typ"]


def segundos_de_validade(tipo: TipoToken, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    if tipo is TipoToken.ACCESS:
        return settings.access_token_expire_minutes * 60
    return settings.refresh_token_expire_days * 24 * 60 * 60


def emitir_token(
    *,
    tipo: TipoToken,
    usuario_id: uuid.UUID,
    condominio_id: uuid.UUID | None,
    sessao_versao: int,
    perfil: str | None,
    settings: Settings | None = None,
    agora: datetime | None = None,
) -> str:
    """Assina um JWT. `agora` existe para os testes poderem simular a passagem do tempo."""
    settings = settings or get_settings()
    agora = agora or datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(usuario_id),
        "sv": sessao_versao,
        # `typ` impede usar um refresh token como access token (e vice-versa).
        "typ": tipo.value,
        "iat": int(agora.timestamp()),
        "exp": int((agora + timedelta(seconds=segundos_de_validade(tipo, settings))).timestamp()),
    }
    if condominio_id is not None:
        payload["cid"] = str(condominio_id)
    if perfil is not None:
        payload["perfil"] = perfil
    return jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decodificar_token(
    token: str, *, tipo_esperado: TipoToken, settings: Settings | None = None
) -> ClaimsToken:
    """Valida assinatura, validade e tipo, e devolve os claims já tipados.

    Qualquer defeito levanta `TokenInvalido`, sem dizer qual: para quem chama, o resultado é o
    mesmo (pedir login de novo) e não há motivo para dar pistas a quem está testando tokens.
    """
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Lista fixa de algoritmos: nunca aceitar o que o próprio token pede (ex.: "none").
            algorithms=[settings.jwt_algorithm],
            options={"require": _CLAIMS_OBRIGATORIAS},
        )
        if payload["typ"] != tipo_esperado.value:
            raise TokenInvalido("tipo de token inesperado")
        sessao_versao = payload["sv"]
        # `bool` é subclasse de `int` em Python; um `true` no lugar do número não pode passar.
        if not isinstance(sessao_versao, int) or isinstance(sessao_versao, bool):
            raise TokenInvalido("sv inválido")
        condominio = payload.get("cid")
        return ClaimsToken(
            usuario_id=uuid.UUID(payload["sub"]),
            condominio_id=uuid.UUID(condominio) if condominio is not None else None,
            sessao_versao=sessao_versao,
            perfil=payload.get("perfil"),
            tipo=tipo_esperado,
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as erro:
        raise TokenInvalido("token inválido") from erro
