import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Aviso(Base):
    """Aviso do condomínio com período de exibição (US-801, US-802). Com `unidade_id`, é o aviso
    automático para uma unidade, criado só pelo servidor (plataforma.md, seção 2)."""

    __tablename__ = "avisos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_avisos_unidade",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_avisos_responsavel",
            ondelete="RESTRICT",
        ),
        CheckConstraint("fim_em > inicio_em", name="periodo_valido"),
        # Aviso geral é publicado por alguém da lista; só o automático da unidade não tem
        # responsável.
        CheckConstraint(
            "unidade_id IS NOT NULL OR responsavel_id IS NOT NULL", name="geral_com_responsavel"
        ),
        Index("ix_avisos_condominio_periodo", "condominio_id", "inicio_em", "fim_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID | None]
    titulo: Mapped[str] = mapped_column(String(120))
    texto: Mapped[str] = mapped_column(Text)
    importante: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    inicio_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fim_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responsavel_id: Mapped[uuid.UUID | None]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Comunicado(Base):
    """Comunicado do ADM às Administrações (US-804)."""

    __tablename__ = "comunicados"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(120))
    texto: Mapped[str] = mapped_column(Text)
    enviado_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ComunicadoDestinatario(Base):
    """Condomínios ativos no momento do envio. Um condomínio criado depois não recebe
    comunicados antigos (plataforma.md, seção 2)."""

    __tablename__ = "comunicado_destinatarios"

    comunicado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comunicados.id", ondelete="RESTRICT"), primary_key=True
    )
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
