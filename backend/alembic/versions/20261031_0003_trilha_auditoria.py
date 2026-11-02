"""Trilha de auditoria somente de inserção."""

import sqlalchemy as sa
from alembic import op

revision = "20261031_0003"
down_revision = "20261028_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eventos_auditoria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("ator", sa.String(length=254), nullable=True),
        sa.Column("perfil", sa.String(length=30), nullable=True),
        sa.Column("condominio_id", sa.Uuid(), nullable=True),
        sa.Column("tipo_evento", sa.String(length=30), nullable=False),
        sa.Column("recurso", sa.String(length=100), nullable=False),
        sa.Column("recurso_id", sa.String(length=100), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("dados_antes", sa.JSON(), nullable=True),
        sa.Column("dados_depois", sa.JSON(), nullable=True),
        sa.Column("conta_compartilhada", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("nome_responsavel", sa.String(length=150), nullable=True),
        sa.CheckConstraint(
            "tipo_evento IN "
            "('login', 'falha_login', 'aprovacao', 'rejeicao', 'mudanca_permissao', "
            "'reserva', 'ocorrencia')",
            name=op.f("ck_eventos_auditoria_tipo_evento_valido"),
        ),
        sa.CheckConstraint(
            "NOT conta_compartilhada OR "
            "(nome_responsavel IS NOT NULL AND length(trim(nome_responsavel)) > 0)",
            name=op.f("ck_eventos_auditoria_responsavel_conta_compartilhada"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_eventos_auditoria_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_eventos_auditoria_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eventos_auditoria")),
    )
    op.create_index(
        "ix_eventos_auditoria_condominio_criado_em",
        "eventos_auditoria",
        ["condominio_id", "criado_em"],
    )
    op.create_index(
        "ix_eventos_auditoria_usuario_criado_em",
        "eventos_auditoria",
        ["usuario_id", "criado_em"],
    )
    op.execute(
        """
        CREATE FUNCTION impedir_alteracao_evento_auditoria()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'eventos_auditoria é somente de inserção';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eventos_auditoria_insert_only
        BEFORE UPDATE OR DELETE ON eventos_auditoria
        FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evento_auditoria()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_eventos_auditoria_insert_only ON eventos_auditoria")
    op.execute("DROP FUNCTION impedir_alteracao_evento_auditoria()")
    op.drop_table("eventos_auditoria")
