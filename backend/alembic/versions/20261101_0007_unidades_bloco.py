"""Vincula unidades geradas ao bloco correspondente."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0007"
down_revision = "20261101_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("bloco_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_blocos_condominio_id"), "blocos_condominio", ["id", "condominio_id"]
    )
    op.create_foreign_key(
        op.f("fk_unidades_bloco_id_blocos_condominio"),
        "unidades",
        "blocos_condominio",
        ["bloco_id", "condominio_id"],
        ["id", "condominio_id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_unidades_bloco_id"), "unidades", ["bloco_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_unidades_bloco_id"), table_name="unidades")
    op.drop_constraint(
        op.f("fk_unidades_bloco_id_blocos_condominio"),
        "unidades",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("uq_blocos_condominio_id"), "blocos_condominio", type_="unique")
    op.drop_column("unidades", "bloco_id")
