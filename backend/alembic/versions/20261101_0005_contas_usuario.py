"""Adiciona CPF e estado de aprovação das contas."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0005"
down_revision = "20261101_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("cpf", sa.String(length=11), nullable=True))
    op.create_unique_constraint(op.f("uq_usuarios_cpf"), "usuarios", ["cpf"])
    op.add_column(
        "usuarios",
        sa.Column(
            "status_conta",
            sa.String(length=20),
            server_default=sa.text("'ativo'"),
            nullable=False,
        ),
    )
    op.execute("UPDATE usuarios SET status_conta = 'suspenso' WHERE ativo = false")
    op.create_check_constraint(
        op.f("ck_usuarios_status_conta_valido"),
        "usuarios",
        "status_conta IN ('pendente', 'ativo', 'rejeitado', 'suspenso')",
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
        "'reserva', 'ocorrencia', 'criacao_conta', 'edicao_conta')",
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
        "'reserva', 'ocorrencia')",
    )
    op.drop_constraint(op.f("ck_usuarios_status_conta_valido"), "usuarios", type_="check")
    op.drop_column("usuarios", "status_conta")
    op.drop_constraint(op.f("uq_usuarios_cpf"), "usuarios", type_="unique")
    op.drop_column("usuarios", "cpf")
