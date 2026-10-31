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

class Condominio(Base):
    __tablename__ = "condominios"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(150))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VinculoCondominio(Base):
    __tablename__ = "vinculos_condominio"
    __table_args__ = (
        UniqueConstraint("usuario_id", "condominio_id"),
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "perfil IN ('administracao', 'funcionario', 'morador')", name="perfil_local"
        ),
        Index("ix_vinculos_condominio_condominio_id", "condominio_id"),
        Index("ix_vinculos_condominio_unidade_id_condominio_id", "unidade_id", "condominio_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT")
    )
    unidade_id: Mapped[uuid.UUID | None]
    perfil: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
