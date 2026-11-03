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

STATUS_CONDOMINIO = ("pendente", "ativo", "rejeitado", "desativado")


class Condominio(Base):
    __tablename__ = "condominios"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendente', 'ativo', 'rejeitado', 'desativado')", name="status_valido"
        ),
        # Rejeitar exige motivo, que a Administração lê no painel (US-203, US-204).
        CheckConstraint(
            "status <> 'rejeitado' OR motivo_rejeicao IS NOT NULL", name="rejeicao_com_motivo"
        ),
        CheckConstraint("cnpj ~ '^[0-9]{14}$'", name="cnpj_digitos"),
        CheckConstraint("cep ~ '^[0-9]{8}$'", name="cep_digitos"),
        CheckConstraint("uf ~ '^[A-Z]{2}$'", name="uf_sigla"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(150))
    # Fluxo de aprovação: nasce pendente e só o ADM deixa ativo (regra 7 do DER).
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pendente'"))
    motivo_rejeicao: Mapped[str | None] = mapped_column(String(500))
    # Opcional no banco só por causa dos registros anteriores ao cadastro (US-202);
    # o service do cadastro exige o CNPJ.
    cnpj: Mapped[str | None] = mapped_column(String(14), unique=True)
    cep: Mapped[str | None] = mapped_column(String(8))
    logradouro: Mapped[str | None] = mapped_column(String(150))
    numero: Mapped[str | None] = mapped_column(String(20))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(String(2))
    logo_arquivo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("arquivos.id", ondelete="RESTRICT", use_alter=True)
    )
    criado_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VinculoCondominio(Base):
    """A conta atua neste condomínio com este perfil. As unidades do Morador ficam em
    `moradores_unidade` (ADR 0003)."""

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
    # Legado da 0001: substituída por `moradores_unidade` e removida quando o login deixar de ler.
    unidade_id: Mapped[uuid.UUID | None]
    perfil: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CondominioAnalise(Base):
    """Histórico de envios e decisões do cadastro (US-203, US-204, US-208)."""

    __tablename__ = "condominio_analises"
    __table_args__ = (
        CheckConstraint(
            "evento IN ('enviado', 'reenviado', 'aprovado', 'rejeitado', 'desativado',"
            " 'reativado')",
            name="evento_valido",
        ),
        CheckConstraint("evento <> 'rejeitado' OR motivo IS NOT NULL", name="rejeicao_com_motivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    evento: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CondominioDocumento(Base):
    """Documentos anexados ao cadastro do prédio, que o ADM analisa na fila (US-203)."""

    __tablename__ = "condominio_documentos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_condominio_documentos_arquivo",
            ondelete="RESTRICT",
        ),
    )

    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), primary_key=True
    )
    arquivo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
