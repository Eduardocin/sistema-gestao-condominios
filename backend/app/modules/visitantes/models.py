import uuid
from datetime import date, datetime

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Visitante(Base):
    """Cadastro do visitante feito pelo morador (US-501) ou avulso pela portaria (US-504).
    Vale para várias entradas dentro do período (decisão 2 do DER)."""

    __tablename__ = "visitantes"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_visitantes_id_condominio"),
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_visitantes_unidade",
            ondelete="RESTRICT",
        ),
        CheckConstraint("saida_prevista >= entrada_prevista", name="periodo_valido"),
        CheckConstraint("cpf ~ '^[0-9]{11}$'", name="cpf_digitos"),
        CheckConstraint("idade BETWEEN 0 AND 130", name="idade_valida"),
        Index("ix_visitantes_condominio_nome", "condominio_id", "nome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(String(150))
    cpf: Mapped[str | None] = mapped_column(String(11))
    idade: Mapped[int | None] = mapped_column(SmallInteger)
    observacoes: Mapped[str | None] = mapped_column(String(500))
    # Datas inclusivas no fuso do condomínio (portaria.md, seção de autorização).
    entrada_prevista: Mapped[date] = mapped_column(Date)
    saida_prevista: Mapped[date] = mapped_column(Date)
    avulso: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    cadastrado_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistroVisita(Base):
    """Cada entrada e saída registrada na portaria (US-503)."""

    __tablename__ = "registros_visita"
    __table_args__ = (
        ForeignKeyConstraint(
            ["visitante_id", "condominio_id"],
            ["visitantes.id", "visitantes.condominio_id"],
            name="fk_registros_visita_visitante",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entrada_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_registros_visita_entrada_por",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["saida_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_registros_visita_saida_por",
            ondelete="RESTRICT",
        ),
        CheckConstraint("saida_em IS NULL OR saida_em >= entrada_em", name="saida_apos_entrada"),
        CheckConstraint(
            "(saida_em IS NULL) = (saida_por_funcionario_id IS NULL)", name="saida_completa"
        ),
        # No máximo uma visita em aberto por visitante (regra 11).
        Index(
            "uq_registros_visita_em_aberto",
            "visitante_id",
            unique=True,
            postgresql_where=text("saida_em IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    visitante_id: Mapped[uuid.UUID]
    entrada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entrada_por_funcionario_id: Mapped[uuid.UUID]
    saida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    saida_por_funcionario_id: Mapped[uuid.UUID | None]


class Veiculo(Base):
    """Veículos da unidade, consultados pela portaria (US-502, US-505)."""

    __tablename__ = "veiculos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_veiculos_unidade",
            ondelete="RESTRICT",
        ),
        # Placa antiga ou Mercosul, maiúscula e sem hífen (regra 13).
        CheckConstraint("placa ~ '^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'", name="placa_formato"),
        CheckConstraint("ativo = (removido_em IS NULL)", name="remocao_com_data"),
        # Entre unidades a placa pode repetir; a US-502 pede só um aviso (regra 14).
        Index(
            "uq_veiculos_unidade_placa_ativo",
            "unidade_id",
            "placa",
            unique=True,
            postgresql_where=text("ativo"),
        ),
        Index("ix_veiculos_condominio_placa", "condominio_id", "placa"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    placa: Mapped[str] = mapped_column(String(7))
    marca: Mapped[str] = mapped_column(String(40))
    modelo: Mapped[str] = mapped_column(String(40))
    cor: Mapped[str] = mapped_column(String(40))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    removido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
