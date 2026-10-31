"""Regras do login: quem entra, em qual condomínio e com qual token.

Ordem de verificação (a mesma da matriz de permissões, seção 5):
identidade (401) → condomínio (403/404) → perfil. Aqui cuidamos das duas primeiras.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.auth import repository
from app.modules.auth.rate_limit import LoginRateLimiter
from app.modules.auth.security import (
    TipoToken,
    TokenInvalido,
    decodificar_token,
    emitir_token,
    gastar_tempo_de_verificacao,
    hash_senha,
    precisa_rehash,
    segundos_de_validade,
    verificar_senha,
)
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

# Mensagem única para qualquer falha de credencial: não revelamos se o e-mail existe,
# se a senha está errada ou se a conta está inativa.
MENSAGEM_CREDENCIAL_INVALIDA = "E-mail ou senha incorretos."

# Perfil que aparece no token do ADM da plataforma (não é um perfil de condomínio).
PERFIL_PLATAFORMA = "plataforma"


@dataclass(frozen=True)
class Acesso:
    """Vínculo do usuário com um condomínio, já cruzado com os dados do condomínio."""

    condominio_id: uuid.UUID
    nome: str
    perfil: str
    status: str

    @property
    def liberado(self) -> bool:
        """R7: condomínio fora do ar só aceita a Administração (para corrigir o cadastro)."""
        return self.status == "ativo" or self.perfil == "administracao"


@dataclass(frozen=True)
class SessaoEmitida:
    """Tudo o que o login devolve: quem entrou, onde pode entrar e os tokens."""

    usuario: Usuario
    acessos: list[Acesso]
    selecionado: Acesso | None
    requer_selecao: bool
    access_token: str
    refresh_token: str
    expires_in: int


def _status_do_condominio(condominio: Condominio) -> str:
    # Provisório: hoje o banco só guarda `ativo` (sim/não). Quando o DER trouxer os quatro
    # status (pendente, ativo, rejeitado, desativado), é só trocar este mapeamento.
    return "ativo" if condominio.ativo else "desativado"


def _montar_acesso(vinculo: VinculoCondominio, condominio: Condominio) -> Acesso:
    return Acesso(
        condominio_id=condominio.id,
        nome=condominio.nome,
        perfil=vinculo.perfil,
        status=_status_do_condominio(condominio),
    )


def _acessos_do_usuario(session: Session, usuario: Usuario) -> list[Acesso]:
    # O ADM da plataforma não pertence a condomínio nenhum (matriz, R8/R9).
    if usuario.administrador_plataforma:
        return []
    return [
        _montar_acesso(vinculo, condominio)
        for vinculo, condominio in repository.listar_vinculos_ativos(session, usuario.id)
    ]


def _emitir_sessao(
    usuario: Usuario,
    acessos: list[Acesso],
    selecionado: Acesso | None,
    settings: Settings,
) -> SessaoEmitida:
    if usuario.administrador_plataforma:
        perfil: str | None = PERFIL_PLATAFORMA
    else:
        perfil = selecionado.perfil if selecionado else None
    condominio_id = selecionado.condominio_id if selecionado else None

    def emitir(tipo: TipoToken) -> str:
        return emitir_token(
            tipo=tipo,
            usuario_id=usuario.id,
            condominio_id=condominio_id,
            sessao_versao=usuario.sessao_versao,
            perfil=perfil,
            settings=settings,
        )

    return SessaoEmitida(
        usuario=usuario,
        acessos=acessos,
        selecionado=selecionado,
        # Com mais de um condomínio, quem decide é o usuário (o token sai sem `cid`).
        requer_selecao=len(acessos) > 1,
        access_token=emitir(TipoToken.ACCESS),
        refresh_token=emitir(TipoToken.REFRESH),
        expires_in=segundos_de_validade(TipoToken.ACCESS, settings),
    )


def _credencial_invalida() -> ApiError:
    return ApiError(401, "not_authenticated", MENSAGEM_CREDENCIAL_INVALIDA)


def _nao_autenticado() -> ApiError:
    return ApiError(
        401,
        "not_authenticated",
        "Sessão inválida ou expirada. Entre novamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def login(
    session: Session,
    *,
    email: str,
    senha: str,
    limiter: LoginRateLimiter,
    settings: Settings,
) -> SessaoEmitida:
    """Valida e-mail e senha e devolve a sessão (tokens + condomínios disponíveis)."""
    # 1) Já está bloqueado? Respondemos antes de gastar CPU com argon2.
    segundos = limiter.bloqueio_restante(email)
    if segundos > 0:
        logger.warning("seguranca.login_bloqueado")
        raise ApiError(
            429,
            "too_many_attempts",
            "Muitas tentativas de login. Tente novamente mais tarde.",
            headers={"Retry-After": str(segundos)},
        )

    # 2) Confere as credenciais. Qualquer motivo de falha termina no mesmo erro genérico.
    usuario = repository.obter_usuario_por_email(session, email)
    if usuario is None or usuario.senha_hash is None:
        # Mesmo sem usuário, gastamos o tempo de uma verificação para não vazar a diferença.
        gastar_tempo_de_verificacao(senha)
        senha_ok = False
    else:
        senha_ok = verificar_senha(senha, usuario.senha_hash)

    if usuario is None or not senha_ok or not usuario.ativo:
        # A falha é contada por e-mail digitado, exista a conta ou não (senão o 429
        # denunciaria quais e-mails têm conta).
        limiter.registrar_falha(email)
        # Quando a auditoria (US-1004) existir, este log vira o evento `seguranca.login_falho`.
        logger.warning("seguranca.login_falho")
        raise _credencial_invalida()

    limiter.limpar(email)

    # 3) Se o hash foi feito com parâmetros antigos, aproveitamos o login para atualizá-lo.
    assert usuario.senha_hash is not None  # garantido acima; ajuda o mypy
    if precisa_rehash(usuario.senha_hash):
        usuario.senha_hash = hash_senha(senha)
        session.commit()

    # 4) Descobre em qual condomínio o token já nasce.
    acessos = _acessos_do_usuario(session, usuario)
    selecionado = acessos[0] if len(acessos) == 1 and acessos[0].liberado else None
    return _emitir_sessao(usuario, acessos, selecionado, settings)


def selecionar_condominio(
    session: Session,
    *,
    usuario: Usuario,
    condominio_id: uuid.UUID,
    settings: Settings,
) -> SessaoEmitida:
    """Emite um novo token já com o condomínio escolhido (`cid`)."""
    # Sem vínculo ativo é 404: não confirmamos nem que o condomínio existe (R4).
    # O ADM da plataforma também cai aqui, porque não tem vínculos.
    linha = None
    if not usuario.administrador_plataforma:
        linha = repository.obter_vinculo_ativo(session, usuario.id, condominio_id)
    if linha is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")

    escolhido = _montar_acesso(*linha)
    if not escolhido.liberado:
        raise ApiError(403, "forbidden", "Este condomínio não está disponível no momento.")

    acessos = _acessos_do_usuario(session, usuario)
    return _emitir_sessao(usuario, acessos, escolhido, settings)


def renovar_access_token(
    session: Session, *, refresh_token: str, settings: Settings
) -> tuple[str, int]:
    """Troca um refresh token válido por um access token novo.

    Tudo é conferido de novo no banco (usuário ativo, `sv`, vínculo e perfil), então quem
    perdeu acesso desde o login não consegue renovar.
    """
    try:
        claims = decodificar_token(
            refresh_token, tipo_esperado=TipoToken.REFRESH, settings=settings
        )
    except TokenInvalido as erro:
        raise _nao_autenticado() from erro

    usuario = repository.obter_usuario_por_id(session, claims.usuario_id)
    if usuario is None or not usuario.ativo or usuario.sessao_versao != claims.sessao_versao:
        raise _nao_autenticado()

    if usuario.administrador_plataforma:
        perfil: str | None = PERFIL_PLATAFORMA
    elif claims.condominio_id is None:
        perfil = None
    else:
        linha = repository.obter_vinculo_ativo(session, usuario.id, claims.condominio_id)
        acesso = _montar_acesso(*linha) if linha else None
        if acesso is None or not acesso.liberado:
            raise _nao_autenticado()
        # O perfil sai do banco, não do token antigo: se mudou, o novo token já reflete.
        perfil = acesso.perfil

    access_token = emitir_token(
        tipo=TipoToken.ACCESS,
        usuario_id=usuario.id,
        condominio_id=claims.condominio_id,
        sessao_versao=usuario.sessao_versao,
        perfil=perfil,
        settings=settings,
    )
    return access_token, segundos_de_validade(TipoToken.ACCESS, settings)


def autenticar_access_token(
    session: Session, *, token: str, settings: Settings
) -> tuple[Usuario, uuid.UUID | None]:
    """Valida um access token e devolve o usuário (do banco) e o `cid` do token.

    Só cuida de *identidade*. Vínculo, perfil e permissões são conferidos por quem usa
    o usuário (autorização central, TASK-19).
    """
    try:
        claims = decodificar_token(token, tipo_esperado=TipoToken.ACCESS, settings=settings)
    except TokenInvalido as erro:
        raise _nao_autenticado() from erro

    usuario = repository.obter_usuario_por_id(session, claims.usuario_id)
    # `sv` diferente = sessão derrubada (troca de senha, por exemplo).
    if usuario is None or not usuario.ativo or usuario.sessao_versao != claims.sessao_versao:
        raise _nao_autenticado()
    return usuario, claims.condominio_id


def verificar_acesso_ao_condominio(
    session: Session, *, usuario: Usuario, condominio_id: uuid.UUID
) -> tuple[VinculoCondominio, Acesso]:
    """Passo 2 da matriz (seção 5): o vínculo ativo e o condomínio ativo, lidos do banco (R6).

    Diferente do login, aqui a Administração de condomínio fora do ar também é negada: o fluxo
    de cadastro (R7) vai ganhar uma dependência própria, em outra task. Todas as falhas são 403
    com mensagem genérica, que não confirma nada sobre o condomínio.
    """
    linha = None
    # O ADM da plataforma nunca atua em condomínio (R8), mesmo que um vínculo escape para ele.
    if not usuario.administrador_plataforma:
        linha = repository.obter_vinculo_ativo(session, usuario.id, condominio_id)
    if linha is None:
        raise ApiError(403, "forbidden", "Você não tem acesso a este condomínio.")

    vinculo, condominio = linha
    acesso = _montar_acesso(vinculo, condominio)
    if acesso.status != "ativo":
        raise ApiError(403, "forbidden", "Este condomínio não está disponível no momento.")
    return vinculo, acesso


@dataclass(frozen=True)
class DadosMe:
    usuario: Usuario
    acesso: Acesso | None
    unidades: list[Unidade]


def montar_me(session: Session, *, usuario: Usuario, condominio_id: uuid.UUID | None) -> DadosMe:
    """Dados para a interface montar menus. Perfil e unidades vêm do banco (R6)."""
    if condominio_id is None:
        return DadosMe(usuario=usuario, acesso=None, unidades=[])

    linha = None
    if not usuario.administrador_plataforma:
        linha = repository.obter_vinculo_ativo(session, usuario.id, condominio_id)
    if linha is None:
        # O token tem um `cid`, mas o vínculo não existe mais: o acesso foi retirado.
        raise ApiError(403, "forbidden", "Você não tem acesso a este condomínio.")

    vinculo, condominio = linha
    acesso = _montar_acesso(vinculo, condominio)
    if not acesso.liberado:
        raise ApiError(403, "forbidden", "Este condomínio não está disponível no momento.")

    unidades: list[Unidade] = []
    if vinculo.perfil == "morador" and vinculo.unidade_id is not None:
        unidade = repository.obter_unidade(session, vinculo.unidade_id, condominio.id)
        if unidade is not None:
            unidades.append(unidade)
    return DadosMe(usuario=usuario, acesso=acesso, unidades=unidades)
