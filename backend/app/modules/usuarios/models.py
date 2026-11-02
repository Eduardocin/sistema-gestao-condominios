import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "status_conta IN ('pendente', 'ativo', 'rejeitado', 'suspenso')",
            name="status_conta_valido",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    cpf: Mapped[str | None] = mapped_column(String(11), unique=True)
    status_conta: Mapped[str] = mapped_column(String(20), server_default=text("'ativo'"))
    administrador_plataforma: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Hash Argon2id; novos cadastros exigem senha, mas contas históricas/plataforma podem não ter.
    senha_hash: Mapped[str | None] = mapped_column(String(255))
    # Vira o claim `sv` do token. Somar 1 aqui derruba todas as sessões da conta de uma vez
    # (troca de senha, por exemplo), sem precisar guardar tokens no banco.
    sessao_versao: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
