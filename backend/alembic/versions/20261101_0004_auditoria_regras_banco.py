"""Reforça imutabilidade e identificação de eventos de contas compartilhadas."""

from alembic import op

revision = "20261101_0004"
down_revision = "20261031_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_eventos_auditoria_perfil_compartilhado_com_responsavel"),
        "eventos_auditoria",
        "perfil NOT IN ('administracao', 'funcionario') OR "
        "(conta_compartilhada AND nome_responsavel IS NOT NULL "
        "AND length(trim(nome_responsavel)) > 0)",
    )
    op.execute(
        """
        CREATE FUNCTION impedir_truncate_evento_auditoria()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'eventos_auditoria é somente de inserção';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eventos_auditoria_insert_only_truncate
        BEFORE TRUNCATE ON eventos_auditoria
        FOR EACH STATEMENT EXECUTE FUNCTION impedir_truncate_evento_auditoria()
        """
    )
    op.execute(
        """
        CREATE FUNCTION definir_data_evento_auditoria()
        RETURNS trigger AS $$
        BEGIN
            NEW.criado_em := now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eventos_auditoria_data_automatica
        BEFORE INSERT ON eventos_auditoria
        FOR EACH ROW EXECUTE FUNCTION definir_data_evento_auditoria()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_eventos_auditoria_data_automatica ON eventos_auditoria")
    op.execute("DROP FUNCTION definir_data_evento_auditoria()")
    op.execute("DROP TRIGGER trg_eventos_auditoria_insert_only_truncate ON eventos_auditoria")
    op.execute("DROP FUNCTION impedir_truncate_evento_auditoria()")
    op.drop_constraint(
        op.f("ck_eventos_auditoria_perfil_compartilhado_com_responsavel"),
        "eventos_auditoria",
        type_="check",
    )
