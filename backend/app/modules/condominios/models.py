import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente', 'ativo', 'rejeitado', 'desativado')",
            name="status_aprovacao_valido",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(150))
    cep: Mapped[str | None] = mapped_column(String(9))
    logradouro: Mapped[str | None] = mapped_column(String(200))
    numero: Mapped[str | None] = mapped_column(String(20))
    complemento: Mapped[str | None] = mapped_column(String(100))
    bairro: Mapped[str | None] = mapped_column(String(100))
    cidade: Mapped[str | None] = mapped_column(String(100))
    estado: Mapped[str | None] = mapped_column(String(2))
    telefone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ativo'"))
    motivo_rejeicao: Mapped[str | None] = mapped_column(String(1000))
    solicitante_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    token_status_solicitacao_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BlocoCondominio(Base):
    __tablename__ = "blocos_condominio"
    __table_args__ = (
        UniqueConstraint("condominio_id", "nome"),
        UniqueConstraint("id", "condominio_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(80))


class AreaComum(Base):
    __tablename__ = "areas_comuns"
    __table_args__ = (UniqueConstraint("condominio_id", "nome"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(100))
    descricao: Mapped[str | None] = mapped_column(String(500))


class RascunhoCondominio(Base):
    __tablename__ = "rascunhos_condominio"
    __table_args__ = (
        CheckConstraint(
            "etapa_atual IN ('dados_gerais', 'blocos', 'unidades', 'areas_comuns', 'responsavel')",
            name="etapa_atual_valida",
        ),
        Index("ix_rascunhos_condominio_expira_em", "expira_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    etapa_atual: Mapped[str] = mapped_column(String(30), server_default=text("'dados_gerais'"))
    dados_gerais: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    blocos: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    unidades: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    areas_comuns: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    responsavel: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChaveAcesso(Base):
    __tablename__ = "chaves_acesso_condominio"
    __table_args__ = (
        Index(
            "uq_chaves_acesso_condominio_disponivel",
            "condominio_id",
            unique=True,
            postgresql_where=text("usada_em IS NULL AND revogada_em IS NULL"),
        ),
        Index("ix_chaves_acesso_condominio_expira_em", "condominio_id", "expira_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT")
    )
    codigo_hash: Mapped[str] = mapped_column(String(64), unique=True)
    criada_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
