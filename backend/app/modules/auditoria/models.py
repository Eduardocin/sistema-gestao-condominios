import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroAuditoria(Base):
    """Trilha de ações críticas (US-1004, US-903). Só aceita inserção: o trigger
    `registros_auditoria_somente_insercao`, criado na migração 0003, recusa UPDATE e DELETE."""

    __tablename__ = "registros_auditoria"
    __table_args__ = (
        Index("ix_registros_auditoria_condominio_criado", "condominio_id", "criado_em"),
        Index("ix_registros_auditoria_criado_em", "criado_em"),
    )

    # bigint sequencial: a ordem de inserção é a ordem dos fatos (decisão 4 do DER).
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Nulo nas ações da plataforma.
    condominio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT")
    )
    # Nulo em login falho de conta inexistente.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    # Nome escolhido na lista quando a conta é compartilhada (matriz, seção 9).
    responsavel_nome: Mapped[str | None] = mapped_column(String(120))
    perfil: Mapped[str | None] = mapped_column(String(20))
    # Formato grupo.verbo, por exemplo condominio.aprovar (plataforma.md, seção 5).
    acao: Mapped[str] = mapped_column(String(60))
    recurso_tipo: Mapped[str | None] = mapped_column(String(60))
    recurso_id: Mapped[uuid.UUID | None]
    antes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    depois: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
