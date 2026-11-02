"""Adiciona solicitações e decisões de vínculo entre moradores e unidades."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0010"
down_revision = "20261101_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_vinculo_unidade",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pendente'"), nullable=False
        ),
        sa.Column(
            "responsavel_principal", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("motivo_rejeicao", sa.String(length=1000), nullable=True),
        sa.Column(
            "solicitado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decidido_por_usuario_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente', 'aprovado', 'rejeitado')",
            name=op.f("ck_solicitacoes_vinculo_unidade_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_solicitacoes_vinculo_unidade_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_solicitacoes_vinculo_unidade_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name=op.f("fk_solicitacoes_vinculo_unidade_unidade_id_unidades"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decidido_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_solicitacoes_vinculo_unidade_decidido_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitacoes_vinculo_unidade")),
    )
    op.create_index(
        "uq_solicitacoes_vinculo_unidade_aberta",
        "solicitacoes_vinculo_unidade",
        ["usuario_id", "condominio_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pendente', 'aprovado')"),
    )
    op.create_index(
        "uq_solicitacoes_vinculo_unidade_responsavel_principal",
        "solicitacoes_vinculo_unidade",
        ["unidade_id"],
        unique=True,
        postgresql_where=sa.text("status = 'aprovado' AND responsavel_principal"),
    )
    op.create_index(
        "ix_solicitacoes_vinculo_unidade_fila",
        "solicitacoes_vinculo_unidade",
        ["condominio_id", "status", "solicitado_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_solicitacoes_vinculo_unidade_fila", table_name="solicitacoes_vinculo_unidade")
    op.drop_index(
        "uq_solicitacoes_vinculo_unidade_responsavel_principal",
        table_name="solicitacoes_vinculo_unidade",
    )
    op.drop_index(
        "uq_solicitacoes_vinculo_unidade_aberta",
        table_name="solicitacoes_vinculo_unidade",
    )
    op.drop_table("solicitacoes_vinculo_unidade")
