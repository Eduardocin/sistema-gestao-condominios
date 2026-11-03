"""Núcleo do DER: contas, condomínio, estrutura, vínculos, arquivos e auditoria (TASK-81)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_0003"
down_revision = "20261028_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Usuários: contato, documento, foto e consentimento (US-101, US-201, US-1007).
    op.add_column("usuarios", sa.Column("telefone", sa.String(11), nullable=True))
    op.add_column("usuarios", sa.Column("documento", sa.String(14), nullable=True))
    op.add_column("usuarios", sa.Column("tipo_cadastro", sa.String(20), nullable=True))
    op.add_column("usuarios", sa.Column("foto_arquivo_id", sa.Uuid(), nullable=True))
    op.add_column(
        "usuarios", sa.Column("email_confirmado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "usuarios", sa.Column("consentimento_dados_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_usuarios_telefone"), "usuarios", ["telefone"])
    op.create_unique_constraint(op.f("uq_usuarios_documento"), "usuarios", ["documento"])
    op.create_check_constraint(
        op.f("ck_usuarios_telefone_digitos"), "usuarios", "telefone ~ '^[0-9]{10,11}$'"
    )
    op.create_check_constraint(
        op.f("ck_usuarios_documento_cpf_cnpj"),
        "usuarios",
        "documento ~ '^([0-9]{11}|[0-9]{14})$'",
    )
    op.create_check_constraint(
        op.f("ck_usuarios_tipo_cadastro_valido"),
        "usuarios",
        "tipo_cadastro IN ('morador', 'administracao')",
    )

    # Condomínios: o booleano `ativo` vira os quatro status do fluxo de aprovação (regra 7).
    # Os registros existentes mantêm o significado: ativo -> 'ativo', inativo -> 'desativado'.
    op.add_column(
        "condominios",
        sa.Column("status", sa.String(20), server_default=sa.text("'pendente'"), nullable=False),
    )
    op.execute("UPDATE condominios SET status = CASE WHEN ativo THEN 'ativo' ELSE 'desativado' END")
    op.drop_column("condominios", "ativo")
    op.add_column("condominios", sa.Column("motivo_rejeicao", sa.String(500), nullable=True))
    op.add_column("condominios", sa.Column("cnpj", sa.String(14), nullable=True))
    op.add_column("condominios", sa.Column("cep", sa.String(8), nullable=True))
    op.add_column("condominios", sa.Column("logradouro", sa.String(150), nullable=True))
    op.add_column("condominios", sa.Column("numero", sa.String(20), nullable=True))
    op.add_column("condominios", sa.Column("complemento", sa.String(80), nullable=True))
    op.add_column("condominios", sa.Column("bairro", sa.String(80), nullable=True))
    op.add_column("condominios", sa.Column("cidade", sa.String(80), nullable=True))
    op.add_column("condominios", sa.Column("uf", sa.String(2), nullable=True))
    op.add_column("condominios", sa.Column("logo_arquivo_id", sa.Uuid(), nullable=True))
    op.add_column("condominios", sa.Column("criado_por_usuario_id", sa.Uuid(), nullable=True))
    op.add_column("condominios", sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "condominios", sa.Column("aprovado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(op.f("uq_condominios_cnpj"), "condominios", ["cnpj"])
    op.create_foreign_key(
        op.f("fk_condominios_criado_por_usuario_id_usuarios"),
        "condominios",
        "usuarios",
        ["criado_por_usuario_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_condominios_status_valido"),
        "condominios",
        "status IN ('pendente', 'ativo', 'rejeitado', 'desativado')",
    )
    op.create_check_constraint(
        op.f("ck_condominios_rejeicao_com_motivo"),
        "condominios",
        "status <> 'rejeitado' OR motivo_rejeicao IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_condominios_cnpj_digitos"), "condominios", "cnpj ~ '^[0-9]{14}$'"
    )
    op.create_check_constraint(
        op.f("ck_condominios_cep_digitos"), "condominios", "cep ~ '^[0-9]{8}$'"
    )
    op.create_check_constraint(op.f("ck_condominios_uf_sigla"), "condominios", "uf ~ '^[A-Z]{2}$'")

    # Unidades ganham andar e desativação (US-202, US-205).
    op.add_column("unidades", sa.Column("andar_id", sa.Uuid(), nullable=True))
    op.add_column(
        "unidades",
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )

    op.create_table(
        "tentativas_chave_acesso",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_tentativas_chave_acesso_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tentativas_chave_acesso")),
    )
    op.create_index(
        "ix_tentativas_chave_acesso_usuario_criado",
        "tentativas_chave_acesso",
        ["usuario_id", "criado_em"],
        unique=False,
    )
    op.create_table(
        "tokens_recuperacao_senha",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expira_em > criado_em", name=op.f("ck_tokens_recuperacao_senha_validade_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_tokens_recuperacao_senha_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tokens_recuperacao_senha")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_tokens_recuperacao_senha_token_hash")),
    )
    op.create_index(
        op.f("ix_tokens_recuperacao_senha_usuario_id"),
        "tokens_recuperacao_senha",
        ["usuario_id"],
        unique=False,
    )
    op.create_table(
        "arquivos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=True),
        sa.Column("chave_storage", sa.String(length=512), nullable=False),
        sa.Column("nome_original", sa.String(length=255), nullable=False),
        sa.Column("tipo_mime", sa.String(length=100), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=False),
        sa.Column("enviado_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("tamanho_bytes > 0", name=op.f("ck_arquivos_tamanho_positivo")),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_arquivos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["enviado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_arquivos_enviado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arquivos")),
        sa.UniqueConstraint("chave_storage", name=op.f("uq_arquivos_chave_storage")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_arquivos_id_condominio_id"),
    )
    op.create_index(op.f("ix_arquivos_condominio_id"), "arquivos", ["condominio_id"], unique=False)
    op.create_table(
        "blocos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=50), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_blocos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocos")),
        sa.UniqueConstraint("condominio_id", "nome", name="uq_blocos_condominio_nome"),
        sa.UniqueConstraint("id", "condominio_id", name="uq_blocos_id_condominio"),
    )
    op.create_index(op.f("ix_blocos_condominio_id"), "blocos", ["condominio_id"], unique=False)
    op.create_table(
        "condominio_analises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("evento", sa.String(length=20), nullable=False),
        sa.Column("motivo", sa.String(length=500), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "evento <> 'rejeitado' OR motivo IS NOT NULL",
            name=op.f("ck_condominio_analises_rejeicao_com_motivo"),
        ),
        sa.CheckConstraint(
            "evento IN ('enviado', 'reenviado', 'aprovado', 'rejeitado', 'desativado',"
            " 'reativado')",
            name=op.f("ck_condominio_analises_evento_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_condominio_analises_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_condominio_analises_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_condominio_analises")),
    )
    op.create_index(
        op.f("ix_condominio_analises_condominio_id"),
        "condominio_analises",
        ["condominio_id"],
        unique=False,
    )
    op.create_table(
        "registros_auditoria",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("responsavel_nome", sa.String(length=120), nullable=True),
        sa.Column("perfil", sa.String(length=20), nullable=True),
        sa.Column("acao", sa.String(length=60), nullable=False),
        sa.Column("recurso_tipo", sa.String(length=60), nullable=True),
        sa.Column("recurso_id", sa.Uuid(), nullable=True),
        sa.Column("antes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("depois", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_registros_auditoria_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_registros_auditoria_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_registros_auditoria")),
    )
    op.create_index(
        "ix_registros_auditoria_condominio_criado",
        "registros_auditoria",
        ["condominio_id", "criado_em"],
        unique=False,
    )
    op.create_index(
        "ix_registros_auditoria_criado_em", "registros_auditoria", ["criado_em"], unique=False
    )
    op.create_table(
        "responsaveis_administracao",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_responsaveis_administracao_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_responsaveis_administracao")),
        sa.UniqueConstraint(
            "id", "condominio_id", name="uq_responsaveis_administracao_id_condominio"
        ),
    )
    op.create_index(
        op.f("ix_responsaveis_administracao_condominio_id"),
        "responsaveis_administracao",
        ["condominio_id"],
        unique=False,
    )
    op.create_table(
        "andares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("bloco_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=50), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["bloco_id", "condominio_id"],
            ["blocos.id", "blocos.condominio_id"],
            name="fk_andares_bloco",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_andares_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_andares")),
        sa.UniqueConstraint("bloco_id", "nome", name="uq_andares_bloco_nome"),
        sa.UniqueConstraint("id", "condominio_id", name="uq_andares_id_condominio"),
    )
    op.create_index(op.f("ix_andares_condominio_id"), "andares", ["condominio_id"], unique=False)
    op.create_table(
        "condominio_documentos",
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("arquivo_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_condominio_documentos_arquivo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_condominio_documentos_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "condominio_id", "arquivo_id", name=op.f("pk_condominio_documentos")
        ),
    )
    op.create_table(
        "funcionarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("funcao", sa.String(length=20), nullable=False),
        sa.Column("telefone", sa.String(length=11), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("foto_arquivo_id", sa.Uuid(), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("desligado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "funcao IN ('porteiro', 'seguranca')", name=op.f("ck_funcionarios_funcao_valida")
        ),
        sa.CheckConstraint(
            "telefone ~ '^[0-9]{10,11}$'", name=op.f("ck_funcionarios_telefone_digitos")
        ),
        sa.CheckConstraint(
            "ativo = (desligado_em IS NULL)", name=op.f("ck_funcionarios_desligamento_com_data")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_funcionarios_email_lowercase")),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_funcionarios_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_funcionarios_foto",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_funcionarios")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_funcionarios_id_condominio"),
    )
    op.create_index(
        op.f("ix_funcionarios_condominio_id"), "funcionarios", ["condominio_id"], unique=False
    )
    op.create_table(
        "chaves_acesso",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column(
            "criada_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "revogada_em IS NULL OR revogada_em >= criada_em",
            name=op.f("ck_chaves_acesso_revogacao_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_chaves_acesso_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_chaves_acesso_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chaves_acesso")),
        sa.UniqueConstraint("codigo", name=op.f("uq_chaves_acesso_codigo")),
    )
    op.create_index(
        op.f("ix_chaves_acesso_condominio_id"), "chaves_acesso", ["condominio_id"], unique=False
    )
    op.create_index(
        "uq_chaves_acesso_unidade_vigente",
        "chaves_acesso",
        ["unidade_id"],
        unique=True,
        postgresql_where=sa.text("revogada_em IS NULL"),
    )
    op.create_table(
        "convites_morador",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("parentesco", sa.String(length=50), nullable=True),
        sa.Column(
            "permissoes_iniciais",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("convidado_por_usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aceito_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_convites_morador_email_lowercase")
        ),
        sa.CheckConstraint(
            "expira_em > criado_em", name=op.f("ck_convites_morador_validade_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_convites_morador_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["convidado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_convites_morador_convidado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_convites_morador_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_convites_morador")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_convites_morador_token_hash")),
    )
    op.create_index(
        op.f("ix_convites_morador_condominio_id"),
        "convites_morador",
        ["condominio_id"],
        unique=False,
    )
    op.create_table(
        "moradores_unidade",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'ativo'"), nullable=False
        ),
        sa.Column("origem", sa.String(length=20), nullable=False),
        sa.Column("parentesco", sa.String(length=50), nullable=True),
        sa.Column(
            "vinculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("desvinculado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("desvinculado_por_usuario_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(status = 'desvinculado') = (desvinculado_em IS NOT NULL)",
            name=op.f("ck_moradores_unidade_desvinculo_com_data"),
        ),
        sa.CheckConstraint(
            "origem IN ('chave', 'convite', 'cadastro')",
            name=op.f("ck_moradores_unidade_origem_valida"),
        ),
        sa.CheckConstraint(
            "status IN ('ativo', 'desvinculado')", name=op.f("ck_moradores_unidade_status_valido")
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_moradores_unidade_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["desvinculado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_moradores_unidade_desvinculado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_moradores_unidade_unidade",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_moradores_unidade_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moradores_unidade")),
        sa.UniqueConstraint("id", "condominio_id", name="uq_moradores_unidade_id_condominio"),
    )
    op.create_index(
        op.f("ix_moradores_unidade_condominio_id"),
        "moradores_unidade",
        ["condominio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_moradores_unidade_usuario_id"), "moradores_unidade", ["usuario_id"], unique=False
    )
    op.create_index(
        "uq_moradores_unidade_ativo",
        "moradores_unidade",
        ["unidade_id", "usuario_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.create_table(
        "proprietarios_unidade",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("unidade_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("documento", sa.String(length=14), nullable=True),
        sa.Column(
            "emails",
            postgresql.ARRAY(sa.String(length=254)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "whatsapps",
            postgresql.ARRAY(sa.String(length=11)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("telefone", sa.String(length=11), nullable=True),
        sa.Column("foto_arquivo_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "documento ~ '^([0-9]{11}|[0-9]{14})$'",
            name=op.f("ck_proprietarios_unidade_documento_cpf_cnpj"),
        ),
        sa.CheckConstraint(
            "telefone ~ '^[0-9]{10,11}$'", name=op.f("ck_proprietarios_unidade_telefone_digitos")
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_proprietarios_unidade_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_proprietarios_unidade_foto",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_proprietarios_unidade_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proprietarios_unidade")),
        sa.UniqueConstraint("unidade_id", name=op.f("uq_proprietarios_unidade_unidade_id")),
    )
    op.create_index(
        op.f("ix_proprietarios_unidade_condominio_id"),
        "proprietarios_unidade",
        ["condominio_id"],
        unique=False,
    )
    op.create_table(
        "permissoes_aba",
        sa.Column("morador_unidade_id", sa.Uuid(), nullable=False),
        sa.Column("aba", sa.String(length=20), nullable=False),
        sa.Column("condominio_id", sa.Uuid(), nullable=False),
        sa.Column("com_acesso", sa.Boolean(), nullable=False),
        sa.Column("alterado_por_usuario_id", sa.Uuid(), nullable=True),
        sa.Column(
            "alterado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "aba IN ('unidades', 'visitantes', 'veiculos', 'reservas', 'encomendas',"
            " 'ocorrencias', 'usuarios')",
            name=op.f("ck_permissoes_aba_aba_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["alterado_por_usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_permissoes_aba_alterado_por_usuario_id_usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["condominio_id"],
            ["condominios.id"],
            name=op.f("fk_permissoes_aba_condominio_id_condominios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_permissoes_aba_morador_unidade",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("morador_unidade_id", "aba", name=op.f("pk_permissoes_aba")),
    )
    op.create_index(
        op.f("ix_permissoes_aba_condominio_id"), "permissoes_aba", ["condominio_id"], unique=False
    )

    # Fotos e logo apontam para arquivos, que só existe a partir daqui.
    op.create_foreign_key(
        op.f("fk_usuarios_foto_arquivo_id_arquivos"),
        "usuarios",
        "arquivos",
        ["foto_arquivo_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_condominios_logo_arquivo_id_arquivos"),
        "condominios",
        "arquivos",
        ["logo_arquivo_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # "101" passa a ser único por andar, não por condomínio (regra 18). Unidades antigas, ainda
    # sem andar, continuam únicas por condomínio.
    op.drop_constraint("uq_unidades_condominio_id", "unidades", type_="unique")
    op.create_unique_constraint(
        "uq_unidades_andar_identificacao", "unidades", ["andar_id", "identificacao"]
    )
    op.create_index(
        "uq_unidades_condominio_identificacao_sem_andar",
        "unidades",
        ["condominio_id", "identificacao"],
        unique=True,
        postgresql_where=sa.text("andar_id IS NULL"),
    )
    op.create_foreign_key(
        "fk_unidades_andar",
        "unidades",
        "andares",
        ["andar_id", "condominio_id"],
        ["id", "condominio_id"],
        ondelete="RESTRICT",
    )

    # Auditoria só de inserção (regra 21): nem a aplicação nem um SQL manual editam ou apagam.
    op.execute(
        """
        CREATE FUNCTION registros_auditoria_somente_insercao() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'registros_auditoria aceita apenas INSERT (% recusado)', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER registros_auditoria_somente_insercao
        BEFORE UPDATE OR DELETE OR TRUNCATE ON registros_auditoria
        FOR EACH STATEMENT EXECUTE FUNCTION registros_auditoria_somente_insercao()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER registros_auditoria_somente_insercao ON registros_auditoria")
    op.execute("DROP FUNCTION registros_auditoria_somente_insercao()")

    op.drop_constraint("fk_unidades_andar", "unidades", type_="foreignkey")
    op.drop_index("uq_unidades_condominio_identificacao_sem_andar", table_name="unidades")
    op.drop_constraint("uq_unidades_andar_identificacao", "unidades", type_="unique")
    op.create_unique_constraint(
        "uq_unidades_condominio_id", "unidades", ["condominio_id", "identificacao"]
    )
    op.drop_constraint(
        op.f("fk_condominios_logo_arquivo_id_arquivos"), "condominios", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_usuarios_foto_arquivo_id_arquivos"), "usuarios", type_="foreignkey")

    op.drop_index(op.f("ix_permissoes_aba_condominio_id"), table_name="permissoes_aba")
    op.drop_table("permissoes_aba")
    op.drop_index(
        op.f("ix_proprietarios_unidade_condominio_id"), table_name="proprietarios_unidade"
    )
    op.drop_table("proprietarios_unidade")
    op.drop_index(
        "uq_moradores_unidade_ativo",
        table_name="moradores_unidade",
        postgresql_where=sa.text("status = 'ativo'"),
    )
    op.drop_index(op.f("ix_moradores_unidade_usuario_id"), table_name="moradores_unidade")
    op.drop_index(op.f("ix_moradores_unidade_condominio_id"), table_name="moradores_unidade")
    op.drop_table("moradores_unidade")
    op.drop_index(op.f("ix_convites_morador_condominio_id"), table_name="convites_morador")
    op.drop_table("convites_morador")
    op.drop_index(
        "uq_chaves_acesso_unidade_vigente",
        table_name="chaves_acesso",
        postgresql_where=sa.text("revogada_em IS NULL"),
    )
    op.drop_index(op.f("ix_chaves_acesso_condominio_id"), table_name="chaves_acesso")
    op.drop_table("chaves_acesso")
    op.drop_index(op.f("ix_funcionarios_condominio_id"), table_name="funcionarios")
    op.drop_table("funcionarios")
    op.drop_table("condominio_documentos")
    op.drop_index(op.f("ix_andares_condominio_id"), table_name="andares")
    op.drop_table("andares")
    op.drop_index(
        op.f("ix_responsaveis_administracao_condominio_id"), table_name="responsaveis_administracao"
    )
    op.drop_table("responsaveis_administracao")
    op.drop_index("ix_registros_auditoria_criado_em", table_name="registros_auditoria")
    op.drop_index("ix_registros_auditoria_condominio_criado", table_name="registros_auditoria")
    op.drop_table("registros_auditoria")
    op.drop_index(op.f("ix_condominio_analises_condominio_id"), table_name="condominio_analises")
    op.drop_table("condominio_analises")
    op.drop_index(op.f("ix_blocos_condominio_id"), table_name="blocos")
    op.drop_table("blocos")
    op.drop_index(op.f("ix_arquivos_condominio_id"), table_name="arquivos")
    op.drop_table("arquivos")
    op.drop_index(
        op.f("ix_tokens_recuperacao_senha_usuario_id"), table_name="tokens_recuperacao_senha"
    )
    op.drop_table("tokens_recuperacao_senha")
    op.drop_index("ix_tentativas_chave_acesso_usuario_criado", table_name="tentativas_chave_acesso")
    op.drop_table("tentativas_chave_acesso")

    op.drop_column("unidades", "ativo")
    op.drop_column("unidades", "andar_id")

    op.add_column(
        "condominios",
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.execute("UPDATE condominios SET ativo = (status = 'ativo')")
    for nome in ("uf_sigla", "cep_digitos", "cnpj_digitos", "rejeicao_com_motivo", "status_valido"):
        op.drop_constraint(op.f(f"ck_condominios_{nome}"), "condominios", type_="check")
    op.drop_constraint(
        op.f("fk_condominios_criado_por_usuario_id_usuarios"), "condominios", type_="foreignkey"
    )
    op.drop_constraint(op.f("uq_condominios_cnpj"), "condominios", type_="unique")
    for coluna in (
        "aprovado_em",
        "enviado_em",
        "criado_por_usuario_id",
        "logo_arquivo_id",
        "uf",
        "cidade",
        "bairro",
        "complemento",
        "numero",
        "logradouro",
        "cep",
        "cnpj",
        "motivo_rejeicao",
        "status",
    ):
        op.drop_column("condominios", coluna)

    for nome in ("tipo_cadastro_valido", "documento_cpf_cnpj", "telefone_digitos"):
        op.drop_constraint(op.f(f"ck_usuarios_{nome}"), "usuarios", type_="check")
    op.drop_constraint(op.f("uq_usuarios_documento"), "usuarios", type_="unique")
    op.drop_constraint(op.f("uq_usuarios_telefone"), "usuarios", type_="unique")
    for coluna in (
        "consentimento_dados_em",
        "email_confirmado_em",
        "foto_arquivo_id",
        "tipo_cadastro",
        "documento",
        "telefone",
    ):
        op.drop_column("usuarios", coluna)
