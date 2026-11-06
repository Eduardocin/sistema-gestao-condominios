import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Funcionario(Base):
    """Porteiros e seguranças (US-209). Não fazem login: a portaria entra pela conta compartilhada,
    e o nome escolhido aqui identifica quem agiu (matriz, seção 9)."""

    __tablename__ = "funcionarios"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_funcionarios_id_condominio"),
        ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_funcionarios_foto",
            ondelete="RESTRICT",
        ),
        CheckConstraint("funcao IN ('porteiro', 'seguranca')", name="funcao_valida"),
        CheckConstraint("telefone ~ '^[0-9]{10,11}$'", name="telefone_digitos"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Desligado some da lista, mas continua nos registros antigos.
        CheckConstraint("ativo = (desligado_em IS NULL)", name="desligamento_com_data"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    funcao: Mapped[str] = mapped_column(String(20))
    telefone: Mapped[str | None] = mapped_column(String(11))
    email: Mapped[str | None] = mapped_column(String(254))
    foto_arquivo_id: Mapped[uuid.UUID | None]
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    desligado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResponsavelAdministracao(Base):
    """Quem opera a conta compartilhada da Administração. Alimenta o campo "responsável"
    (US-210)."""

    __tablename__ = "responsaveis_administracao"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id", name="uq_responsaveis_administracao_id_condominio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
