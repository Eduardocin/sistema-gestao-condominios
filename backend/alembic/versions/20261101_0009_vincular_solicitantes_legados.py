"""Associa solicitações anteriores à conta de Administração já vinculada."""

import sqlalchemy as sa
from alembic import op

revision = "20261101_0009"
down_revision = "20261101_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE condominios AS c
            SET solicitante_id = vinculo.usuario_id
            FROM vinculos_condominio AS vinculo
            WHERE c.solicitante_id IS NULL
              AND c.status = 'pendente'
              AND vinculo.condominio_id = c.id
              AND vinculo.perfil = 'administracao'
            """
        )
    )
    op.execute(
        """
        UPDATE condominios
        SET status = 'desativado'
        WHERE status = 'pendente' AND solicitante_id IS NULL
        """
    )


def downgrade() -> None:
    pass
