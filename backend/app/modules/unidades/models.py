import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Unidade(Base):
    __tablename__ = "unidades"
    __table_args__ = (
        UniqueConstraint("condominio_id", "identificacao"),
        UniqueConstraint("id", "condominio_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    identificacao: Mapped[str] = mapped_column(String(80))
