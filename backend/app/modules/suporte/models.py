import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Chamado(Base):
    """Chamado de suporte da Administração para o ADM (US-901, US-902)."""

    __tablename__ = "chamados"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_chamados_id_condominio"),
        CheckConstraint(
            "status IN ('aberto', 'em_atendimento', 'encerrado')", name="status_valido"
        ),
        CheckConstraint(
            "(status = 'encerrado') = (encerrado_em IS NOT NULL)", name="encerramento_com_data"
        ),
        CheckConstraint(
            "status = 'aberto' OR atendido_por_usuario_id IS NOT NULL", name="atendimento_com_adm"
        ),
        Index("ix_chamados_status_criado", "status", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'aberto'"))
    aberto_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    atendido_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    encerrado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChamadoMensagem(Base):
    """Histórico do atendimento, preservado depois de encerrar (US-902)."""

    __tablename__ = "chamado_mensagens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chamado_id", "condominio_id"],
            ["chamados.id", "chamados.condominio_id"],
            name="fk_chamado_mensagens_chamado",
            ondelete="RESTRICT",
        ),
        Index("ix_chamado_mensagens_chamado_criado", "chamado_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    chamado_id: Mapped[uuid.UUID]
    autor_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChamadoAnexo(Base):
    __tablename__ = "chamado_anexos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["chamado_id", "condominio_id"],
            ["chamados.id", "chamados.condominio_id"],
            name="fk_chamado_anexos_chamado",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_chamado_anexos_arquivo",
            ondelete="RESTRICT",
        ),
    )

    chamado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    arquivo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
