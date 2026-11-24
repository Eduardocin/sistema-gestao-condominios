"""Adiciona a transportadora opcional das encomendas."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_0010"
down_revision = "20261124_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("encomendas", sa.Column("transportadora", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("encomendas", "transportadora")
