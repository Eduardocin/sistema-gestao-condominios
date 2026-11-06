import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnvioEmail(Base):
    """Fila de e-mails no padrão outbox: entra na mesma transação da operação principal
    (US-803; plataforma.md, seção 6)."""

    __tablename__ = "envios_email"
    __table_args__ = (
        CheckConstraint(
            "evento IN ('recuperacao_senha', 'condominio_aprovado', 'encomenda_registrada', "
            "'reserva_cancelada')",
            name="evento_valido",
        ),
        CheckConstraint("status IN ('pendente', 'enviado', 'falhou')", name="status_valido"),
        CheckConstraint("(status = 'enviado') = (enviado_em IS NOT NULL)", name="envio_com_data"),
        CheckConstraint("tentativas >= 0", name="tentativas_validas"),
        # Fila de reenvio: só o que ainda não saiu (US-803).
        Index(
            "ix_envios_email_pendentes",
            "status",
            postgresql_where=text("status <> 'enviado'"),
        ),
        Index("ix_envios_email_recurso", "recurso_tipo", "recurso_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    destinatario: Mapped[str] = mapped_column(String(254))
    evento: Mapped[str] = mapped_column(String(40))
    # O que foi enviado, para montar o corpo no reenvio (plataforma.md, pendências).
    recurso_tipo: Mapped[str | None] = mapped_column(String(60))
    recurso_id: Mapped[uuid.UUID | None]
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pendente'"))
    tentativas: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
