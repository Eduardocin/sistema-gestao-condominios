"""Entrega do e-mail: `console` (log) ou `smtp`. Escolhido por `EMAIL_BACKEND`."""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Mensagem:
    destinatario: str
    assunto: str
    corpo: str


class EmailBackend(Protocol):
    def enviar(self, mensagem: Mensagem) -> None:
        """Envia ou levanta qualquer exceção; o worker anota a falha e tenta de novo."""


class ConsoleBackend:
    """Escreve no log em vez de enviar; o corpo vai junto, para ver o texto em desenvolvimento."""

    def enviar(self, mensagem: Mensagem) -> None:
        logger.info(
            "E-mail (console) para=%s assunto=%r\n%s",
            mensagem.destinatario,
            mensagem.assunto,
            mensagem.corpo,
        )


class SmtpBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def enviar(self, mensagem: Mensagem) -> None:
        cfg = self.settings
        email = EmailMessage()
        email["From"] = cfg.smtp_from
        email["To"] = mensagem.destinatario
        email["Subject"] = mensagem.assunto
        email.set_content(mensagem.corpo)
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds) as smtp:
            if cfg.smtp_starttls:
                smtp.starttls()
            if cfg.smtp_user and cfg.smtp_password:
                smtp.login(cfg.smtp_user, cfg.smtp_password.get_secret_value())
            smtp.send_message(email)


def obter_backend(settings: Settings) -> EmailBackend:
    return SmtpBackend(settings) if settings.email_backend == "smtp" else ConsoleBackend()
