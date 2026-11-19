"""Preserva vínculos de moradores anteriores à tabela moradores_unidade."""

from alembic import op

revision = "20261119_0007"
down_revision = "20261116_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO moradores_unidade (id, condominio_id, unidade_id, usuario_id, origem)
        SELECT gen_random_uuid(), v.condominio_id, v.unidade_id, v.usuario_id, 'cadastro'
        FROM vinculos_condominio AS v
        JOIN unidades AS u ON u.id = v.unidade_id AND u.condominio_id = v.condominio_id
        WHERE v.perfil = 'morador' AND v.ativo AND u.ativo
          AND NOT EXISTS (
              SELECT 1 FROM moradores_unidade AS m
              WHERE m.condominio_id = v.condominio_id AND m.usuario_id = v.usuario_id
          )
        """
    )


def downgrade() -> None:
    # Preserva os vínculos e o histórico que podem ter sido usados desde o upgrade.
    pass
