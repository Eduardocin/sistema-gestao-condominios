"""Adiciona rascunhos retomáveis e estrutura física do condomínio."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0006"
down_revision = "20261101_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("condominios", sa.Column("cep", sa.String(length=9), nullable=True))
    op.add_column("condominios", sa.Column("logradouro", sa.String(length=200), nullable=True))
    op.add_column("condominios", sa.Column("numero", sa.String(length=20), nullable=True))
    op.add_column("condominios", sa.Column("complemento", sa.String(length=100), nullable=True))
    op.add_column("condominios", sa.Column("bairro", sa.String(length=100), nullable=True))
    op.add_column("condominios", sa.Column("cidade", sa.String(length=100), nullable=True))
    op.add_column("condominios", sa.Column("estado", sa.String(length=2), nullable=True))
    op.add_column("condominios", sa.Column("telefone", sa.String(length=20), nullable=True))
    op.create_table(
        "rascunhos_condominio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "etapa_atual",
            sa.String(length=30),
            server_default=sa.text("'dados_gerais'"),
            nullable=False,
        ),
        sa.Column("dados_gerais", sa.JSON(), nullable=True),
        sa.Column("blocos", sa.JSON(), nullable=True),
        sa.Column("unidades", sa.JSON(), nullable=True),
        sa.Column("areas_comuns", sa.JSON(), nullable=True),
        sa.Column("responsavel", sa.JSON(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "etapa_atual IN ('dados_gerais', 'blocos', 'unidades', 'areas_comuns', 'responsavel')",
            name=op.f("ck_rascunhos_condominio_etapa_atual_valida"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rascunhos_condominio")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_rascunhos_condominio_token_hash")),
    )
    op.create_index("ix_rascunhos_condominio_expira_em", "rascunhos_condominio", ["expira_em"])
    op.create_table(
        "blocos_condominio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_blocos_condominio_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocos_condominio")),
        sa.UniqueConstraint(
            "condominio_id", "nome", name=op.f("uq_blocos_condominio_condominio_id")
        ),
    )
    op.create_index(
        op.f("ix_blocos_condominio_condominio_id"),
        "blocos_condominio",
        ["condominio_id"],
    )
    op.create_table(
        "areas_comuns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("descricao", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_areas_comuns_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_areas_comuns")),
        sa.UniqueConstraint("condominio_id", "nome", name=op.f("uq_areas_comuns_condominio_id")),
    )
    op.create_index(op.f("ix_areas_comuns_condominio_id"), "areas_comuns", ["condominio_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_areas_comuns_condominio_id"), table_name="areas_comuns")
    op.drop_table("areas_comuns")
    op.drop_index(op.f("ix_blocos_condominio_condominio_id"), table_name="blocos_condominio")
    op.drop_table("blocos_condominio")
    op.drop_index("ix_rascunhos_condominio_expira_em", table_name="rascunhos_condominio")
    op.drop_table("rascunhos_condominio")
    op.drop_column("condominios", "telefone")
    op.drop_column("condominios", "estado")
    op.drop_column("condominios", "cidade")
    op.drop_column("condominios", "bairro")
    op.drop_column("condominios", "complemento")
    op.drop_column("condominios", "numero")
    op.drop_column("condominios", "logradouro")
    op.drop_column("condominios", "cep")
