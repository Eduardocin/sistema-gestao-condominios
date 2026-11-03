"""Plataforma: comunicados e destinatários, chamados de suporte e fila de e-mails (TASK-81)."""

import sqlalchemy as sa
from alembic import op

revision = "20261103_0005"
down_revision = "20261103_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comunicados",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("enviado_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["enviado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_comunicados_enviado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comunicados")),
    )
    op.create_table(
        "chamados",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'aberto'"), nullable=False
        ),
        sa.Column("aberto_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("atendido_por_usuario_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'encerrado') = (encerrado_em IS NOT NULL)",
            name=op.f("ck_chamados_encerramento_com_data"),
        ),
        sa.CheckConstraint(
            "status = 'aberto' OR atendido_por_usuario_id IS NOT NULL",
            name=op.f("ck_chamados_atendimento_com_adm"),
        ),
        sa.CheckConstraint(
            "status IN ('aberto', 'em_atendimento', 'encerrado')",
            name=op.f("ck_chamados_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["aberto_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_chamados_aberto_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["atendido_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_chamados_atendido_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_chamados_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chamados")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_chamados_id_condominio"),
    )
    op.create_index(op.f("ix_chamados_condominio_id"), "chamados", ["condominio_id"], unique=False)
    op.create_index("ix_chamados_status_criado", "chamados", ["status", "criado_em"], unique=False)
    op.create_table(
        "comunicado_destinatarios",
        sa.Column("comunicado_id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["comunicado_id"],
            ["comunicados.id"],
            name=op.f("fk_comunicado_destinatarios_comunicado_id_comunicados"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_comunicado_destinatarios_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "comunicado_id", "condominio_id", name=op.f("pk_comunicado_destinatarios")
        ),
    )
    op.create_index(
        op.f("ix_comunicado_destinatarios_condominio_id"),
        "comunicado_destinatarios",
        ["condominio_id"],
        unique=False,
    )
    op.create_table(
        "envios_email",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=True),
        sa.Column("destinatario", sa.String(length=254), nullable=False),
        sa.Column("evento", sa.String(length=40), nullable=False),
        sa.Column("recurso_tipo", sa.String(length=60), nullable=True),
        sa.Column("recurso_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'pendente'"), nullable=False
        ),
        sa.Column("tentativas", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("ultimo_erro", sa.Text(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'enviado') = (enviado_em IS NOT NULL)",
            name=op.f("ck_envios_email_envio_com_data"),
        ),
        sa.CheckConstraint(
            "evento IN ('recuperacao_senha', 'condominio_aprovado', 'encomenda_registrada',"
            " 'reserva_cancelada')",
            name=op.f("ck_envios_email_evento_valido"),
        ),
        sa.CheckConstraint(
            "status IN ('pendente', 'enviado', 'falhou')",
            name=op.f("ck_envios_email_status_valido"),
        ),
        sa.CheckConstraint("tentativas >= 0", name=op.f("ck_envios_email_tentativas_validas")),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_envios_email_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_envios_email")),
    )
    op.create_index(
        op.f("ix_envios_email_condominio_id"), "envios_email", ["condominio_id"], unique=False
    )
    op.create_index(
        "ix_envios_email_pendentes",
        "envios_email",
        ["status"],
        unique=False,
        postgresql_where=sa.text("status <> 'enviado'"),
    )
    op.create_index(
        "ix_envios_email_recurso", "envios_email", ["recurso_tipo", "recurso_id"], unique=False
    )
    op.create_table(
        "chamado_anexos",
        sa.Column("chamado_id", sa.Uuid(), nullable=False),
        sa.Column("arquivo_id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_chamado_anexos_arquivo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chamado_id", "condominio_id"],
            ["chamados.id", "chamados.condominio_id"],
            name="fk_chamado_anexos_chamado",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_chamado_anexos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("chamado_id", "arquivo_id", name=op.f("pk_chamado_anexos")),
    )
    op.create_index(
        op.f("ix_chamado_anexos_condominio_id"), "chamado_anexos", ["condominio_id"], unique=False
    )
    op.create_table(
        "chamado_mensagens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("chamado_id", sa.Uuid(), nullable=False),
        sa.Column("autor_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["autor_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_chamado_mensagens_autor_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chamado_id", "condominio_id"],
            ["chamados.id", "chamados.condominio_id"],
            name="fk_chamado_mensagens_chamado",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_chamado_mensagens_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chamado_mensagens")),
    )
    op.create_index(
        "ix_chamado_mensagens_chamado_criado",
        "chamado_mensagens",
        ["chamado_id", "criado_em"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chamado_mensagens_condominio_id"),
        "chamado_mensagens",
        ["condominio_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chamado_mensagens_condominio_id"), table_name="chamado_mensagens")
    op.drop_index("ix_chamado_mensagens_chamado_criado", table_name="chamado_mensagens")
    op.drop_table("chamado_mensagens")
    op.drop_index(op.f("ix_chamado_anexos_condominio_id"), table_name="chamado_anexos")
    op.drop_table("chamado_anexos")
    op.drop_index("ix_envios_email_recurso", table_name="envios_email")
    op.drop_index(
        "ix_envios_email_pendentes",
        table_name="envios_email",
        postgresql_where=sa.text("status <> 'enviado'"),
    )
    op.drop_index(op.f("ix_envios_email_condominio_id"), table_name="envios_email")
    op.drop_table("envios_email")
    op.drop_index(
        op.f("ix_comunicado_destinatarios_condominio_id"), table_name="comunicado_destinatarios"
    )
    op.drop_table("comunicado_destinatarios")
    op.drop_index("ix_chamados_status_criado", table_name="chamados")
    op.drop_index(op.f("ix_chamados_condominio_id"), table_name="chamados")
    op.drop_table("chamados")
    op.drop_table("comunicados")
