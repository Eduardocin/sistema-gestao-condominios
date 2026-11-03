import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AreaComum(Base):
    """Área reservável (US-601). Grade de 1 hora entre `abre_as` e `fecha_as`."""

    __tablename__ = "areas_comuns"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_areas_comuns_id_condominio"),
        ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_areas_comuns_foto",
            ondelete="RESTRICT",
        ),
        CheckConstraint("fecha_as > abre_as", name="horario_valido"),
        # Horas quebradas criariam um último slot parcial (convivencia.md, seção 2).
        CheckConstraint(
            "date_part('minute', abre_as) = 0 AND date_part('second', abre_as) = 0"
            " AND date_part('minute', fecha_as) = 0 AND date_part('second', fecha_as) = 0",
            name="horario_hora_cheia",
        ),
        CheckConstraint("capacidade > 0", name="capacidade_positiva"),
        # Nome único no condomínio, sem diferenciar maiúsculas (convivencia.md, seção 2).
        Index(
            "uq_areas_comuns_condominio_nome",
            "condominio_id",
            func.lower(text("nome")),
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(100))
    foto_arquivo_id: Mapped[uuid.UUID]
    regras: Mapped[str | None] = mapped_column(Text)
    abre_as: Mapped[time] = mapped_column(Time)
    fecha_as: Mapped[time] = mapped_column(Time)
    capacidade: Mapped[int] = mapped_column(SmallInteger)
    # Área desativada não aceita novas reservas (US-601).
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class BloqueioArea(Base):
    """Datas indisponíveis por manutenção (US-602)."""

    __tablename__ = "bloqueios_area"
    __table_args__ = (
        ForeignKeyConstraint(
            ["area_id", "condominio_id"],
            ["areas_comuns.id", "areas_comuns.condominio_id"],
            name="fk_bloqueios_area_area",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_bloqueios_area_responsavel",
            ondelete="RESTRICT",
        ),
        CheckConstraint("data_fim >= data_inicio", name="intervalo_valido"),
        CheckConstraint(
            "(removido_em IS NULL) = (removido_por_usuario_id IS NULL)", name="remocao_completa"
        ),
        Index("ix_bloqueios_area_area_datas", "area_id", "data_inicio", "data_fim"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    area_id: Mapped[uuid.UUID]
    data_inicio: Mapped[date] = mapped_column(Date)
    data_fim: Mapped[date] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(String(200))
    responsavel_id: Mapped[uuid.UUID]
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bloqueio lançado por engano é removido, não apagado (convivencia.md, pendências).
    removido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removido_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )


class Reserva(Base):
    """Slot de 1 hora de uma área comum (US-603 a US-605)."""

    __tablename__ = "reservas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["area_id", "condominio_id"],
            ["areas_comuns.id", "areas_comuns.condominio_id"],
            name="fk_reservas_area",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_reservas_unidade",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["cancelada_responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_reservas_cancelada_responsavel",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('ativa', 'cancelada')", name="status_valido"),
        CheckConstraint(
            "date_part('minute', hora_inicio) = 0 AND date_part('second', hora_inicio) = 0",
            name="hora_cheia",
        ),
        CheckConstraint(
            "(status = 'cancelada') = (cancelada_em IS NOT NULL"
            " AND cancelada_por_usuario_id IS NOT NULL)",
            name="cancelamento_completo",
        ),
        # Cancelamento pela Administração exige motivo (US-605).
        CheckConstraint(
            "cancelada_responsavel_id IS NULL OR motivo_cancelamento IS NOT NULL",
            name="cancelamento_adm_com_motivo",
        ),
        # Os nomes destes dois índices são o contrato com o service de reservas, que traduz a
        # violação no `reason` do 409 (convivencia.md, seção 4.2). Não renomear.
        Index(
            "uq_reservas_unidade_area_dia_ativa",
            "unidade_id",
            "area_id",
            "data",
            unique=True,
            postgresql_where=text("status = 'ativa'"),
        ),
        Index(
            "uq_reservas_area_horario_ativa",
            "area_id",
            "data",
            "hora_inicio",
            unique=True,
            postgresql_where=text("status = 'ativa'"),
        ),
        Index("ix_reservas_area_data", "area_id", "data"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    area_id: Mapped[uuid.UUID]
    unidade_id: Mapped[uuid.UUID]
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    data: Mapped[date] = mapped_column(Date)
    hora_inicio: Mapped[time] = mapped_column(Time)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ativa'"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelada_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    cancelada_responsavel_id: Mapped[uuid.UUID | None]
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))
