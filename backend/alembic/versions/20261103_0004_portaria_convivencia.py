"""Portaria e convivência: encomendas, visitantes, áreas, reservas e ocorrências (TASK-81)."""

import sqlalchemy as sa
from alembic import op

revision = "20261103_0004"
down_revision = "20261103_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "areas_comuns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("foto_arquivo_id", sa.Uuid(), nullable=False),
        sa.Column("regras", sa.Text(), nullable=True),
        sa.Column("abre_as", sa.Time(), nullable=False),
        sa.Column("fecha_as", sa.Time(), nullable=False),
        sa.Column("capacidade", sa.SmallInteger(), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "date_part('minute', abre_as) = 0 AND date_part('second', abre_as) = 0"
            " AND date_part('minute', fecha_as) = 0 AND date_part('second', fecha_as) = 0",
            name=op.f("ck_areas_comuns_horario_hora_cheia"),
        ),
        sa.CheckConstraint("capacidade > 0", name=op.f("ck_areas_comuns_capacidade_positiva")),
        sa.CheckConstraint("fecha_as > abre_as", name=op.f("ck_areas_comuns_horario_valido")),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_areas_comuns_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_areas_comuns_foto",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_areas_comuns")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_areas_comuns_id_condominio"),
    )
    op.create_index(
        op.f("ix_areas_comuns_condominio_id"), "areas_comuns", ["condominio_id"], unique=False
    )
    op.create_index(
        "uq_areas_comuns_condominio_nome",
        "areas_comuns",
        ["condominio_id", sa.literal_column("lower(nome)")],
        unique=True,
    )
    op.create_table(
        "bloqueios_area",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(length=200), nullable=True),
        sa.Column("responsavel_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("removido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removido_por_usuario_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(removido_em IS NULL) = (removido_por_usuario_id IS NULL)",
            name=op.f("ck_bloqueios_area_remocao_completa"),
        ),
        sa.CheckConstraint(
            "data_fim >= data_inicio", name=op.f("ck_bloqueios_area_intervalo_valido")
        ),
        sa.ForeignKeyConstraint(
            ["area_id", "condominio_id"],
            ["areas_comuns.id", "areas_comuns.condominio_id"],
            name="fk_bloqueios_area_area",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_bloqueios_area_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["removido_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_bloqueios_area_removido_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_bloqueios_area_responsavel",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bloqueios_area")),
    )
    op.create_index(
        "ix_bloqueios_area_area_datas",
        "bloqueios_area",
        ["area_id", "data_inicio", "data_fim"],
        unique=False,
    )
    op.create_index(
        op.f("ix_bloqueios_area_condominio_id"), "bloqueios_area", ["condominio_id"], unique=False
    )
    op.create_table(
        "avisos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=True),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("importante", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("inicio_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fim_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("encerrado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsavel_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("fim_em > inicio_em", name=op.f("ck_avisos_periodo_valido")),
        sa.CheckConstraint(
            "unidade_id IS NOT NULL OR responsavel_id IS NOT NULL",
            name=op.f("ck_avisos_geral_com_responsavel"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_avisos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_avisos_responsavel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_avisos_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_avisos")),
    )
    op.create_index(op.f("ix_avisos_condominio_id"), "avisos", ["condominio_id"], unique=False)
    op.create_index(
        "ix_avisos_condominio_periodo",
        "avisos",
        ["condominio_id", "inicio_em", "fim_em"],
        unique=False,
    )
    op.create_table(
        "ocorrencias",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("aberta_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'em_aberto'"), nullable=False
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("resolvida_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'resolvida') = (resolvida_em IS NOT NULL)",
            name=op.f("ck_ocorrencias_resolucao_com_data"),
        ),
        sa.CheckConstraint(
            "status IN ('em_aberto', 'resolvida')", name=op.f("ck_ocorrencias_status_valido")
        ),
        sa.ForeignKeyConstraint(
            ["aberta_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_ocorrencias_aberta_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_ocorrencias_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_ocorrencias_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocorrencias")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_ocorrencias_id_condominio"),
    )
    op.create_index(
        op.f("ix_ocorrencias_condominio_id"), "ocorrencias", ["condominio_id"], unique=False
    )
    op.create_index(
        "ix_ocorrencias_condominio_status_criado",
        "ocorrencias",
        ["condominio_id", "status", "criado_em"],
        unique=False,
    )
    op.create_table(
        "reservas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("area_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'ativa'"), nullable=False
        ),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("cancelada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelada_por_usuario_id", sa.Uuid(), nullable=True),
        sa.Column("cancelada_responsavel_id", sa.Uuid(), nullable=True),
        sa.Column("motivo_cancelamento", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "(status = 'cancelada') = (cancelada_em IS NOT NULL"
            " AND cancelada_por_usuario_id IS NOT NULL)",
            name=op.f("ck_reservas_cancelamento_completo"),
        ),
        sa.CheckConstraint(
            "date_part('minute', hora_inicio) = 0 AND date_part('second', hora_inicio) = 0",
            name=op.f("ck_reservas_hora_cheia"),
        ),
        sa.CheckConstraint(
            "status IN ('ativa', 'cancelada')", name=op.f("ck_reservas_status_valido")
        ),
        sa.CheckConstraint(
            "cancelada_responsavel_id IS NULL OR motivo_cancelamento IS NOT NULL",
            name=op.f("ck_reservas_cancelamento_adm_com_motivo"),
        ),
        sa.ForeignKeyConstraint(
            ["area_id", "condominio_id"],
            ["areas_comuns.id", "areas_comuns.condominio_id"],
            name="fk_reservas_area",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelada_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_reservas_cancelada_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cancelada_responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_reservas_cancelada_responsavel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_reservas_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_reservas_unidade",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_reservas_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reservas")),
    )
    op.create_index("ix_reservas_area_data", "reservas", ["area_id", "data"], unique=False)
    op.create_index(op.f("ix_reservas_condominio_id"), "reservas", ["condominio_id"], unique=False)
    op.create_index(
        "uq_reservas_area_horario_ativa",
        "reservas",
        ["area_id", "data", "hora_inicio"],
        unique=True,
        postgresql_where=sa.text("status = 'ativa'"),
    )
    op.create_index(
        "uq_reservas_unidade_area_dia_ativa",
        "reservas",
        ["unidade_id", "area_id", "data"],
        unique=True,
        postgresql_where=sa.text("status = 'ativa'"),
    )
    op.create_table(
        "veiculos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("placa", sa.String(length=7), nullable=False),
        sa.Column("marca", sa.String(length=40), nullable=False),
        sa.Column("modelo", sa.String(length=40), nullable=False),
        sa.Column("cor", sa.String(length=40), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("removido_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "placa ~ '^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$'", name=op.f("ck_veiculos_placa_formato")
        ),
        sa.CheckConstraint(
            "ativo = (removido_em IS NULL)", name=op.f("ck_veiculos_remocao_com_data")
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_veiculos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_veiculos_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_veiculos")),
    )
    op.create_index(op.f("ix_veiculos_condominio_id"), "veiculos", ["condominio_id"], unique=False)
    op.create_index(
        "ix_veiculos_condominio_placa", "veiculos", ["condominio_id", "placa"], unique=False
    )
    op.create_index(
        "uq_veiculos_unidade_placa_ativo",
        "veiculos",
        ["unidade_id", "placa"],
        unique=True,
        postgresql_where=sa.text("ativo"),
    )
    op.create_table(
        "visitantes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("cpf", sa.String(length=11), nullable=True),
        sa.Column("idade", sa.SmallInteger(), nullable=True),
        sa.Column("observacoes", sa.String(length=500), nullable=True),
        sa.Column("entrada_prevista", sa.Date(), nullable=False),
        sa.Column("saida_prevista", sa.Date(), nullable=False),
        sa.Column("avulso", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cadastrado_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("cpf ~ '^[0-9]{11}$'", name=op.f("ck_visitantes_cpf_digitos")),
        sa.CheckConstraint("idade BETWEEN 0 AND 130", name=op.f("ck_visitantes_idade_valida")),
        sa.CheckConstraint(
            "saida_prevista >= entrada_prevista", name=op.f("ck_visitantes_periodo_valido")
        ),
        sa.ForeignKeyConstraint(
            ["cadastrado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_visitantes_cadastrado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_visitantes_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_visitantes_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visitantes")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_visitantes_id_condominio"),
    )
    op.create_index(
        op.f("ix_visitantes_condominio_id"), "visitantes", ["condominio_id"], unique=False
    )
    op.create_index(
        "ix_visitantes_condominio_nome", "visitantes", ["condominio_id", "nome"], unique=False
    )
    op.create_table(
        "encomendas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("destinatario_morador_unidade_id", sa.Uuid(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("foto_nota_arquivo_id", sa.Uuid(), nullable=False),
        sa.Column("recebido_por_funcionario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            server_default=sa.text("'aguardando_retirada'"),
            nullable=False,
        ),
        sa.Column(
            "registrada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entregue_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recebedor_morador_unidade_id", sa.Uuid(), nullable=True),
        sa.Column("entregue_por_funcionario_id", sa.Uuid(), nullable=True),
        sa.Column("confirmada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmado_por_usuario_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(status = 'aguardando_retirada' AND entregue_em IS NULL"
            " AND recebedor_morador_unidade_id IS NULL"
            " AND entregue_por_funcionario_id IS NULL AND confirmada_em IS NULL"
            " AND confirmado_por_usuario_id IS NULL)"
            " OR (status = 'entregue_aguardando_confirmacao' AND entregue_em IS NOT NULL"
            " AND recebedor_morador_unidade_id IS NOT NULL"
            " AND entregue_por_funcionario_id IS NOT NULL AND confirmada_em IS NULL"
            " AND confirmado_por_usuario_id IS NULL) OR (status = 'retirada_confirmada'"
            " AND entregue_em IS NOT NULL AND recebedor_morador_unidade_id IS NOT NULL"
            " AND entregue_por_funcionario_id IS NOT NULL AND confirmada_em IS NOT NULL"
            " AND confirmado_por_usuario_id IS NOT NULL)",
            name=op.f("ck_encomendas_etapas_completas"),
        ),
        sa.CheckConstraint(
            "status IN ('aguardando_retirada', 'entregue_aguardando_confirmacao',"
            " 'retirada_confirmada')",
            name=op.f("ck_encomendas_status_valido"),
        ),
        sa.CheckConstraint(
            "confirmada_em IS NULL OR confirmada_em >= entregue_em",
            name=op.f("ck_encomendas_confirmacao_apos_entrega"),
        ),
        sa.CheckConstraint(
            "entregue_em IS NULL OR entregue_em >= registrada_em",
            name=op.f("ck_encomendas_entrega_apos_registro"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_encomendas_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["confirmado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_encomendas_confirmado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destinatario_morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_encomendas_destinatario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entregue_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_encomendas_entregue_por",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["foto_nota_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_encomendas_foto_nota",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recebedor_morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_encomendas_recebedor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recebido_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_encomendas_recebido_por",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_encomendas_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_encomendas")),
    )
    op.create_index(
        op.f("ix_encomendas_condominio_id"), "encomendas", ["condominio_id"], unique=False
    )
    op.create_index(
        "ix_encomendas_condominio_status_registrada",
        "encomendas",
        ["condominio_id", "status", "registrada_em"],
        unique=False,
    )
    op.create_index(
        "ix_encomendas_unidade_registrada",
        "encomendas",
        ["unidade_id", "registrada_em"],
        unique=False,
    )
    op.create_table(
        "ocorrencia_interacoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("ocorrencia_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("responsavel_id", sa.Uuid(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "tipo <> 'resposta' OR responsavel_id IS NOT NULL",
            name=op.f("ck_ocorrencia_interacoes_resposta_com_responsavel"),
        ),
        sa.CheckConstraint(
            "tipo IN ('resposta', 'comentario', 'resolucao', 'reabertura')",
            name=op.f("ck_ocorrencia_interacoes_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_ocorrencia_interacoes_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id", "condominio_id"],
            ["ocorrencias.id", "ocorrencias.condominio_id"],
            name="fk_ocorrencia_interacoes_ocorrencia",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["responsavel_id", "condominio_id"],
            ["responsaveis_administracao.id", "responsaveis_administracao.condominio_id"],
            name="fk_ocorrencia_interacoes_responsavel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_ocorrencia_interacoes_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocorrencia_interacoes")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_ocorrencia_interacoes_id_condominio"),
    )
    op.create_index(
        op.f("ix_ocorrencia_interacoes_condominio_id"),
        "ocorrencia_interacoes",
        ["condominio_id"],
        unique=False,
    )
    op.create_index(
        "ix_ocorrencia_interacoes_ocorrencia_criado",
        "ocorrencia_interacoes",
        ["ocorrencia_id", "criado_em"],
        unique=False,
    )
    op.create_table(
        "registros_visita",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("visitante_id", sa.Uuid(), nullable=False),
        sa.Column(
            "entrada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("entrada_por_funcionario_id", sa.Uuid(), nullable=False),
        sa.Column("saida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("saida_por_funcionario_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(saida_em IS NULL) = (saida_por_funcionario_id IS NULL)",
            name=op.f("ck_registros_visita_saida_completa"),
        ),
        sa.CheckConstraint(
            "saida_em IS NULL OR saida_em >= entrada_em",
            name=op.f("ck_registros_visita_saida_apos_entrada"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_registros_visita_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entrada_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_registros_visita_entrada_por",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["saida_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_registros_visita_saida_por",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["visitante_id", "condominio_id"],
            ["visitantes.id", "visitantes.condominio_id"],
            name="fk_registros_visita_visitante",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registros_visita")),
    )
    op.create_index(
        op.f("ix_registros_visita_condominio_id"),
        "registros_visita",
        ["condominio_id"],
        unique=False,
    )
    op.create_index(
        "uq_registros_visita_em_aberto",
        "registros_visita",
        ["visitante_id"],
        unique=True,
        postgresql_where=sa.text("saida_em IS NULL"),
    )
    op.create_table(
        "ocorrencia_anexos",
        sa.Column("ocorrencia_id", sa.Uuid(), nullable=False),
        sa.Column("arquivo_id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("interacao_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_ocorrencia_anexos_arquivo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_ocorrencia_anexos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["interacao_id", "condominio_id"],
            ["ocorrencia_interacoes.id", "ocorrencia_interacoes.condominio_id"],
            name="fk_ocorrencia_anexos_interacao",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ocorrencia_id", "condominio_id"],
            ["ocorrencias.id", "ocorrencias.condominio_id"],
            name="fk_ocorrencia_anexos_ocorrencia",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ocorrencia_id", "arquivo_id", name=op.f("pk_ocorrencia_anexos")),
    )
    op.create_index(
        op.f("ix_ocorrencia_anexos_condominio_id"),
        "ocorrencia_anexos",
        ["condominio_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ocorrencia_anexos_condominio_id"), table_name="ocorrencia_anexos")
    op.drop_table("ocorrencia_anexos")
    op.drop_index(
        "uq_registros_visita_em_aberto",
        table_name="registros_visita",
        postgresql_where=sa.text("saida_em IS NULL"),
    )
    op.drop_index(op.f("ix_registros_visita_condominio_id"), table_name="registros_visita")
    op.drop_table("registros_visita")
    op.drop_index("ix_ocorrencia_interacoes_ocorrencia_criado", table_name="ocorrencia_interacoes")
    op.drop_index(
        op.f("ix_ocorrencia_interacoes_condominio_id"), table_name="ocorrencia_interacoes"
    )
    op.drop_table("ocorrencia_interacoes")
    op.drop_index("ix_encomendas_unidade_registrada", table_name="encomendas")
    op.drop_index("ix_encomendas_condominio_status_registrada", table_name="encomendas")
    op.drop_index(op.f("ix_encomendas_condominio_id"), table_name="encomendas")
    op.drop_table("encomendas")
    op.drop_index("ix_visitantes_condominio_nome", table_name="visitantes")
    op.drop_index(op.f("ix_visitantes_condominio_id"), table_name="visitantes")
    op.drop_table("visitantes")
    op.drop_index(
        "uq_veiculos_unidade_placa_ativo", table_name="veiculos", postgresql_where=sa.text("ativo")
    )
    op.drop_index("ix_veiculos_condominio_placa", table_name="veiculos")
    op.drop_index(op.f("ix_veiculos_condominio_id"), table_name="veiculos")
    op.drop_table("veiculos")
    op.drop_index(
        "uq_reservas_unidade_area_dia_ativa",
        table_name="reservas",
        postgresql_where=sa.text("status = 'ativa'"),
    )
    op.drop_index(
        "uq_reservas_area_horario_ativa",
        table_name="reservas",
        postgresql_where=sa.text("status = 'ativa'"),
    )
    op.drop_index(op.f("ix_reservas_condominio_id"), table_name="reservas")
    op.drop_index("ix_reservas_area_data", table_name="reservas")
    op.drop_table("reservas")
    op.drop_index("ix_ocorrencias_condominio_status_criado", table_name="ocorrencias")
    op.drop_index(op.f("ix_ocorrencias_condominio_id"), table_name="ocorrencias")
    op.drop_table("ocorrencias")
    op.drop_index("ix_avisos_condominio_periodo", table_name="avisos")
    op.drop_index(op.f("ix_avisos_condominio_id"), table_name="avisos")
    op.drop_table("avisos")
    op.drop_index(op.f("ix_bloqueios_area_condominio_id"), table_name="bloqueios_area")
    op.drop_index("ix_bloqueios_area_area_datas", table_name="bloqueios_area")
    op.drop_table("bloqueios_area")
    op.drop_index("uq_areas_comuns_condominio_nome", table_name="areas_comuns")
    op.drop_index(op.f("ix_areas_comuns_condominio_id"), table_name="areas_comuns")
    op.drop_table("areas_comuns")
