import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Arquivo(Base):
    """Metadados de um objeto do storage (US-1003). O conteúdo nunca vai para o banco."""

    __tablename__ = "arquivos"
    __table_args__ = (
        # Alvo das FKs compostas: um arquivo só pode ser usado dentro do próprio condomínio.
        UniqueConstraint("id", "condominio_id", name="uq_arquivos_id_condominio_id"),
        CheckConstraint("tamanho_bytes > 0", name="tamanho_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Nulo para arquivos da conta (foto do usuário) ou da plataforma.
    condominio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    chave_storage: Mapped[str] = mapped_column(String(512), unique=True)
    nome_original: Mapped[str] = mapped_column(String(255))
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    enviado_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
