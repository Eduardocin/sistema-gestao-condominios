"""Proposta TASK-26 para integração por Davi na TASK-81; fora da cadeia ativa."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_arquivos_storage"
down_revision = "PENDENTE_TASK_81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "arquivos",
        sa.Column("id", sa.Uuid(), nullable=False),
        # O DER permite NULL para arquivos futuros de conta/plataforma.
        # O serviço desta entrega exige um contexto com condomínio.
        sa.Column("condominio_id", sa.Uuid(), nullable=True),
        sa.Column("chave_storage", sa.String(512), nullable=False),
        sa.Column("nome_original", sa.String(255), nullable=False),
        sa.Column("tipo_mime", sa.String(100), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=False),
        sa.Column("enviado_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_arquivos"),
        sa.ForeignKeyConstraint(["condominio_id"], ["condominios.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["enviado_por_usuario_id"], ["usuarios.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("chave_storage", name="uq_arquivos_chave_storage"),
        sa.UniqueConstraint("id", "condominio_id", name="uq_arquivos_id_condominio_id"),
        sa.CheckConstraint("tamanho_bytes > 0", name="ck_arquivos_tamanho_positivo"),
    )
    op.create_index("ix_arquivos_condominio_id", "arquivos", ["condominio_id"])


def downgrade() -> None:
    op.drop_index("ix_arquivos_condominio_id", table_name="arquivos")
    op.drop_table("arquivos")
