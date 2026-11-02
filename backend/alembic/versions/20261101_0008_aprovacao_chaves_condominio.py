"""Adiciona aprovação de condomínios, consulta do solicitante e chaves de acesso."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0008"
down_revision = "20261101_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "condominios",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'ativo'"),
            nullable=False,
        ),
    )
    op.execute("UPDATE condominios SET status = CASE WHEN ativo THEN 'ativo' ELSE 'pendente' END")
    op.add_column("condominios", sa.Column("motivo_rejeicao", sa.String(length=1000)))
    op.add_column("condominios", sa.Column("solicitante_id", sa.Uuid()))
    op.add_column("condominios", sa.Column("token_status_solicitacao_hash", sa.String(length=64)))
    op.create_foreign_key(
        op.f("fk_condominios_solicitante_id_usuarios"),
        "condominios",
        "usuarios",
        ["solicitante_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        op.f("uq_condominios_token_status_solicitacao_hash"),
        "condominios",
        ["token_status_solicitacao_hash"],
    )
    op.create_check_constraint(
        op.f("ck_condominios_status_aprovacao_valido"),
        "condominios",
        "status IN ('pendente', 'ativo', 'rejeitado', 'desativado')",
    )
    op.create_table(
        "chaves_acesso_condominio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("codigo_hash", sa.String(length=64), nullable=False),
        sa.Column("criada_por_usuario_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_chaves_acesso_condominio_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["criada_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_chaves_acesso_condominio_criada_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chaves_acesso_condominio")),
        sa.UniqueConstraint("codigo_hash", name=op.f("uq_chaves_acesso_condominio_codigo_hash")),
    )
    op.create_index(
        "uq_chaves_acesso_condominio_disponivel",
        "chaves_acesso_condominio",
        ["condominio_id"],
        unique=True,
        postgresql_where=sa.text("usada_em IS NULL AND revogada_em IS NULL"),
    )
    op.create_index(
        "ix_chaves_acesso_condominio_expira_em",
        "chaves_acesso_condominio",
        ["condominio_id", "expira_em"],
    )
    op.drop_constraint(
        op.f("ck_eventos_auditoria_tipo_evento_valido"),
        "eventos_auditoria",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_eventos_auditoria_tipo_evento_valido"),
        "eventos_auditoria",
        "tipo_evento IN "
        "('login', 'falha_login', 'aprovacao', 'rejeicao', 'mudanca_permissao', "
        "'reserva', 'ocorrencia', 'criacao_conta', 'edicao_conta', "
        "'notificacao_condominio')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_eventos_auditoria_tipo_evento_valido"),
        "eventos_auditoria",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_eventos_auditoria_tipo_evento_valido"),
        "eventos_auditoria",
        "tipo_evento IN "
        "('login', 'falha_login', 'aprovacao', 'rejeicao', 'mudanca_permissao', "
        "'reserva', 'ocorrencia', 'criacao_conta', 'edicao_conta')",
    )
    op.drop_index("ix_chaves_acesso_condominio_expira_em", table_name="chaves_acesso_condominio")
    op.drop_index("uq_chaves_acesso_condominio_disponivel", table_name="chaves_acesso_condominio")
    op.drop_table("chaves_acesso_condominio")
    op.drop_constraint(op.f("ck_condominios_status_aprovacao_valido"), "condominios", type_="check")
    op.drop_constraint(
        op.f("uq_condominios_token_status_solicitacao_hash"), "condominios", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_condominios_solicitante_id_usuarios"), "condominios", type_="foreignkey"
    )
    op.drop_column("condominios", "token_status_solicitacao_hash")
    op.drop_column("condominios", "solicitante_id")
    op.drop_column("condominios", "motivo_rejeicao")
    op.drop_column("condominios", "status")
