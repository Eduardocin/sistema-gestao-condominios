"""Índices das listagens por condomínio, status e data que faltavam na 0003-0005 (TASK-81)."""

import sqlalchemy as sa
from alembic import op

revision = "20261116_0006"
down_revision = "20261103_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GET /reservas (convivencia.md): Administração por status e período; Morador por unidade.
    op.create_index(
        "ix_reservas_condominio_status_data", "reservas", ["condominio_id", "status", "data"]
    )
    op.create_index("ix_reservas_unidade_data", "reservas", ["unidade_id", "data"])
    # GET /ocorrencias do Morador: unidade obrigatória, status opcional, mais recentes primeiro.
    op.create_index(
        "ix_ocorrencias_unidade_status_criado",
        "ocorrencias",
        ["unidade_id", "status", "criado_em"],
    )
    # GET /visitas (portaria.md): histórico do condomínio e visitas ainda em aberto.
    op.create_index(
        "ix_registros_visita_condominio_entrada",
        "registros_visita",
        ["condominio_id", "entrada_em"],
    )
    op.create_index(
        "ix_registros_visita_condominio_em_aberto",
        "registros_visita",
        ["condominio_id", "entrada_em"],
        postgresql_where=sa.text("saida_em IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_registros_visita_condominio_em_aberto", table_name="registros_visita")
    op.drop_index("ix_registros_visita_condominio_entrada", table_name="registros_visita")
    op.drop_index("ix_ocorrencias_unidade_status_criado", table_name="ocorrencias")
    op.drop_index("ix_reservas_unidade_data", table_name="reservas")
    op.drop_index("ix_reservas_condominio_status_data", table_name="reservas")
