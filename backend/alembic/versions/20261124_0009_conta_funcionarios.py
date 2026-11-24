"""Identidade permanente de Funcionários e data das credenciais (US-210)."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_0009"
down_revision = "20261121_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Não escolher donos, consolidar contas ou inventar datas para corrigir legados.
    # O lock impede que gravações concorrentes escapem da validação até criar os índices.
    op.execute("LOCK TABLE usuarios, vinculos_condominio IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM vinculos_condominio WHERE perfil = 'funcionario'
            GROUP BY condominio_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'US-210: condominio com multiplos vinculos de funcionario; '
              'regularizacao explicita necessaria, sem alteracoes automaticas';
          END IF;
          IF EXISTS (
            SELECT 1 FROM vinculos_condominio f
            JOIN usuarios u ON u.id = f.usuario_id
            WHERE f.perfil = 'funcionario' AND (
              u.tipo_cadastro IS NOT NULL OR u.administrador_plataforma
              OR u.telefone IS NOT NULL OR u.documento IS NOT NULL
              OR f.unidade_id IS NOT NULL
              OR EXISTS (
                SELECT 1 FROM vinculos_condominio v
                WHERE v.usuario_id = f.usuario_id AND v.id <> f.id
              )
            )
          ) THEN
            RAISE EXCEPTION 'US-210: conta de funcionario pessoal, de plataforma, com unidade '
              'ou outros vinculos; regularizacao explicita necessaria';
          END IF;
        END $$
        """
    )
    op.add_column(
        "vinculos_condominio",
        sa.Column("credenciais_atualizadas_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_vinculos_funcionario_condominio",
        "vinculos_condominio",
        ["condominio_id"],
        unique=True,
        postgresql_where=sa.text("perfil = 'funcionario'"),
    )
    op.create_index(
        "uq_vinculos_funcionario_usuario",
        "vinculos_condominio",
        ["usuario_id"],
        unique=True,
        postgresql_where=sa.text("perfil = 'funcionario'"),
    )


def downgrade() -> None:
    op.drop_index("uq_vinculos_funcionario_usuario", table_name="vinculos_condominio")
    op.drop_index("uq_vinculos_funcionario_condominio", table_name="vinculos_condominio")
    op.drop_column("vinculos_condominio", "credenciais_atualizadas_em")
