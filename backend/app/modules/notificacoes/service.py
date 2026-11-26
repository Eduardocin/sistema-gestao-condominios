"""Envio da fila (worker) e acompanhamento pelo ADM da plataforma (US-803).

O e-mail entra em `envios_email` na transação da operação principal (outbox). Aqui ele sai: o
worker pega um envio por vez, monta o corpo a partir do banco, entrega e marca `enviado`. A
falha do e-mail nunca volta para a operação principal, que já foi confirmada.
"""

import logging
import smtplib
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.notificacoes import repository
from app.modules.notificacoes.corpo import CorpoIndisponivel, montar
from app.modules.notificacoes.models import EnvioEmail
from app.modules.notificacoes.repository import FiltrosEnvios
from app.modules.notificacoes.schemas import (
    ConsultaDeEnvios,
    EnvioSaida,
    PaginaDeEnvios,
    ResultadoDoLote,
)
from app.modules.notificacoes.smtp import EmailBackend

logger = logging.getLogger(__name__)

LIMITE_DO_LOTE = 50
EVENTO_SEM_REENVIO = "recuperacao_senha"


def _descrever_erro(erro: Exception) -> str:
    """O que vai para `ultimo_erro`: só o tipo (e o código SMTP), nunca a mensagem, que pode
    trazer o endereço, o servidor ou um trecho do corpo."""
    if isinstance(erro, CorpoIndisponivel):
        return str(erro)
    if isinstance(erro, smtplib.SMTPResponseException):
        return f"{type(erro).__name__} {erro.smtp_code}"
    return type(erro).__name__


def processar_pendentes(
    fabrica_de_sessoes: Callable[[], Session],
    backend: EmailBackend,
    *,
    max_tentativas: int,
    limite: int = LIMITE_DO_LOTE,
    agora: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ResultadoDoLote:
    """Envia os pendentes, um por transação. Quem falha volta para a próxima rodada (o intervalo
    do worker faz o papel do espaçamento entre tentativas), nunca para esta."""
    resultado = ResultadoDoLote()
    vistos: set[uuid.UUID] = set()
    for _ in range(limite):
        with fabrica_de_sessoes() as session:
            envio = repository.proximo_pendente(
                session, max_tentativas=max_tentativas, ignorar=vistos
            )
            if envio is None:
                return resultado
            vistos.add(envio.id)
            _entregar(session, envio, backend, max_tentativas, agora, resultado)
            session.commit()
    return resultado


def _entregar(
    session: Session,
    envio: EnvioEmail,
    backend: EmailBackend,
    max_tentativas: int,
    agora: Callable[[], datetime],
    resultado: ResultadoDoLote,
) -> None:
    try:
        backend.enviar(montar(session, envio))
    except Exception as erro:
        envio.tentativas += 1
        envio.ultimo_erro = _descrever_erro(erro)
        sem_chance = isinstance(erro, CorpoIndisponivel)  # repetir não muda o texto
        if sem_chance or envio.tentativas >= max_tentativas:
            envio.status = "falhou"
            resultado.esgotados += 1
        resultado.falhas += 1
        logger.warning(
            "Falha ao enviar e-mail id=%s evento=%s: %s", envio.id, envio.evento, envio.ultimo_erro
        )
        return
    envio.status = "enviado"
    envio.enviado_em = agora()
    envio.ultimo_erro = None
    resultado.enviados += 1


# --- acompanhamento (ADM da plataforma) -------------------------------------------------------


def mascarar(email: str) -> str:
    """`ana@exemplo.com` -> `a***@exemplo.com`."""
    local, _, dominio = email.partition("@")
    return f"{local[:1]}***@{dominio}" if dominio else "***"


def _saida(envio: EnvioEmail) -> EnvioSaida:
    return EnvioSaida(
        id=envio.id,
        evento=envio.evento,
        destinatario=mascarar(envio.destinatario),
        status=envio.status,
        tentativas=envio.tentativas,
        ultimo_erro=envio.ultimo_erro,
        criado_em=envio.criado_em,
        enviado_em=envio.enviado_em,
    )


def listar(session: Session, consulta: ConsultaDeEnvios) -> PaginaDeEnvios:
    itens, total = repository.pagina(
        session,
        FiltrosEnvios(
            status=consulta.status,
            evento=consulta.evento,
            condominio_id=consulta.condominio_id,
            de=consulta.de,
            ate=consulta.ate,
        ),
        limite=consulta.page_size,
        deslocamento=(consulta.page - 1) * consulta.page_size,
    )
    return PaginaDeEnvios(
        items=[_saida(e) for e in itens],
        page=consulta.page,
        page_size=consulta.page_size,
        total=total,
    )


def reenviar(session: Session, envio_id: uuid.UUID) -> EnvioSaida:
    """Só `falhou` volta para a fila, e nunca `recuperacao_senha` (o token em texto não é
    guardado). O worker entrega; esta rota só recoloca na fila."""
    envio = repository.obter(session, envio_id)
    if envio is None:
        raise RecursoNaoEncontrado
    if envio.evento == EVENTO_SEM_REENVIO:
        raise ApiError(
            409,
            "conflict",
            "Esse e-mail não pode ser reenviado: peça uma nova recuperação de senha.",
            reason="reenvio_nao_permitido",
        )
    reposto = repository.recolocar_na_fila(session, envio_id)
    if reposto is None:
        session.rollback()
        raise ApiError(
            409, "conflict", "Só um envio que falhou pode ser reenviado.", reason="envio_nao_falhou"
        )
    session.commit()
    return _saida(reposto)
