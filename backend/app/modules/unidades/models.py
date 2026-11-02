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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Unidade(Base):
    __tablename__ = "unidades"
    __table_args__ = (
        UniqueConstraint("condominio_id", "identificacao"),
        UniqueConstraint("id", "condominio_id"),
        ForeignKeyConstraint(
            ["bloco_id", "condominio_id"],
            ["blocos_condominio.id", "blocos_condominio.condominio_id"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    bloco_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    identificacao: Mapped[str] = mapped_column(String(80))


class SolicitacaoVinculoUnidade(Base):
    __tablename__ = "solicitacoes_vinculo_unidade"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente', 'aprovado', 'rejeitado')",
            name="status_valido",
        ),
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_solicitacoes_vinculo_unidade_aberta",
            "usuario_id",
            "condominio_id",
            unique=True,
            postgresql_where=text("status IN ('pendente', 'aprovado')"),
        ),
        Index(
            "uq_solicitacoes_vinculo_unidade_responsavel_principal",
            "unidade_id",
            unique=True,
            postgresql_where=text("status = 'aprovado' AND responsavel_principal"),
        ),
        Index(
            "ix_solicitacoes_vinculo_unidade_fila",
            "condominio_id",
            "status",
            "solicitado_em",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT")
    )
    unidade_id: Mapped[uuid.UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pendente'"))
    responsavel_principal: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    motivo_rejeicao: Mapped[str | None] = mapped_column(String(1000))
    solicitado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decidido_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
