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


class Ocorrencia(Base):
    """Ocorrência aberta pelo morador (US-701). Reabrir é um evento do histórico, não um
    terceiro estado (RN-69)."""

    __tablename__ = "ocorrencias"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_ocorrencias_id_condominio"),
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_ocorrencias_unidade",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('em_aberto', 'resolvida')", name="status_valido"),
        CheckConstraint(
            "(status = 'resolvida') = (resolvida_em IS NOT NULL)", name="resolucao_com_data"
        ),
        Index("ix_ocorrencias_condominio_status_criado", "condominio_id", "status", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    aberta_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    titulo: Mapped[str] = mapped_column(String(120))
    detalhe: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'em_aberto'"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OcorrenciaInteracao(Base):
    """Histórico de respostas, comentários, resolução e reabertura (US-703, US-704)."""

    __tablename__ = "ocorrencia_interacoes"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_ocorrencia_interacoes_id_condominio"),
        ForeignKeyConstraint(
            ["ocorrencia_id", "condominio_id"],
            ["ocorrencias.id", "ocorrencias.condominio_id"],
            name="fk_ocorrencia_interacoes_ocorrencia",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_ocorrencia_interacoes_responsavel",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "tipo IN ('resposta', 'comentario', 'resolucao', 'reabertura')", name="tipo_valido"
        ),
        # A resposta da Administração guarda o responsável escolhido na lista (US-703).
        CheckConstraint(
            "tipo <> 'resposta' OR responsavel_id IS NOT NULL", name="resposta_com_responsavel"
        ),
        Index("ix_ocorrencia_interacoes_ocorrencia_criado", "ocorrencia_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    ocorrencia_id: Mapped[uuid.UUID]
    tipo: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str | None] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    responsavel_id: Mapped[uuid.UUID | None]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OcorrenciaAnexo(Base):
    """Fotos e vídeos da ocorrência; sem `interacao_id`, é anexo da abertura (US-701)."""

    __tablename__ = "ocorrencia_anexos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ocorrencia_id", "condominio_id"],
            ["ocorrencias.id", "ocorrencias.condominio_id"],
            name="fk_ocorrencia_anexos_ocorrencia",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_ocorrencia_anexos_arquivo",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["interacao_id", "condominio_id"],
            ["ocorrencia_interacoes.id", "ocorrencia_interacoes.condominio_id"],
            name="fk_ocorrencia_anexos_interacao",
            ondelete="RESTRICT",
        ),
    )

    ocorrencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    arquivo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    interacao_id: Mapped[uuid.UUID | None]
