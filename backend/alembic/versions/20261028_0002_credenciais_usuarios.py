"""Credenciais de login em usuarios: hash da senha e versão da sessão."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0002"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nulo de propósito: contas que já existem ainda não têm senha e simplesmente não conseguem
    # entrar até definirem uma. O cadastro (US-104) vai exigir a senha na criação.
    op.add_column("usuarios", sa.Column("senha_hash", sa.String(255), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column("sessao_versao", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("usuarios", "sessao_versao")
    op.drop_column("usuarios", "senha_hash")
