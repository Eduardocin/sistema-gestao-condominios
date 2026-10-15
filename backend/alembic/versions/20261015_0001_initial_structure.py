"""Usuários globais, condomínios, unidades e vínculos locais."""

import sqlalchemy as sa
from alembic import op

revision = "20261015_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column(
            "administrador_plataforma", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usuarios"),
        sa.UniqueConstraint("email", name="uq_usuarios_email"),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_usuarios_email_lowercase")),
    )
    op.create_table(
        "condominios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_condominios"),
    )
    op.create_table(
        "unidades",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("identificacao", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_unidades"),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name="fk_unidades_condominio_id_condominios",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("condominio_id", "identificacao", name="uq_unidades_condominio_id"),
        sa.UniqueConstraint("id", "condominio_id", name="uq_unidades_id"),
    )
    op.create_index("ix_unidades_condominio_id", "unidades", ["condominio_id"])
    op.create_table(
        "vinculos_condominio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("perfil", sa.String(20), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vinculos_condominio"),
        sa.UniqueConstraint(
            "usuario_id", "condominio_id", name="uq_vinculos_condominio_usuario_id"
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name="fk_vinculos_condominio_usuario_id_usuarios",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name="fk_vinculos_condominio_condominio_id_condominios",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_vinculos_condominio_unidade_id_unidades",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "perfil IN ('administracao', 'funcionario', 'morador')",
            name=op.f("ck_vinculos_condominio_perfil_local"),
        ),
    )
    op.create_index(
        "ix_vinculos_condominio_condominio_id", "vinculos_condominio", ["condominio_id"]
    )
    op.create_index(
        "ix_vinculos_condominio_unidade_id_condominio_id",
        "vinculos_condominio",
        ["unidade_id", "condominio_id"],
    )


def downgrade() -> None:
    op.drop_table("vinculos_condominio")
    op.drop_table("unidades")
    op.drop_table("condominios")
    op.drop_table("usuarios")
