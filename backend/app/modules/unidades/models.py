import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ABAS_MORADOR = (
    "unidades",
    "visitantes",
    "veiculos",
    "reservas",
    "encomendas",
    "ocorrencias",
    "usuarios",
)


class Bloco(Base):
    __tablename__ = "blocos"
    __table_args__ = (
        UniqueConstraint("condominio_id", "nome", name="uq_blocos_condominio_nome"),
        UniqueConstraint("id", "condominio_id", name="uq_blocos_id_condominio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    nome: Mapped[str] = mapped_column(String(50))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Andar(Base):
    __tablename__ = "andares"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bloco_id", "condominio_id"],
            ["blocos.id", "blocos.condominio_id"],
            name="fk_andares_bloco",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("bloco_id", "nome", name="uq_andares_bloco_nome"),
        UniqueConstraint("id", "condominio_id", name="uq_andares_id_condominio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    bloco_id: Mapped[uuid.UUID]
    nome: Mapped[str] = mapped_column(String(50))
    # Posição do andar no bloco, para a árvore do assistente (US-202).
    ordem: Mapped[int] = mapped_column(SmallInteger)
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Unidade(Base):
    __tablename__ = "unidades"
    __table_args__ = (
        UniqueConstraint("id", "condominio_id"),
        ForeignKeyConstraint(
            ["andar_id", "condominio_id"],
            ["andares.id", "andares.condominio_id"],
            name="fk_unidades_andar",
            ondelete="RESTRICT",
        ),
        # "101" pode existir em blocos diferentes, mas não duas vezes no mesmo andar (regra 18).
        UniqueConstraint("andar_id", "identificacao", name="uq_unidades_andar_identificacao"),
        # Unidades da 0001 ainda não têm andar: para elas vale a regra antiga, por condomínio.
        Index(
            "uq_unidades_condominio_identificacao_sem_andar",
            "condominio_id",
            "identificacao",
            unique=True,
            postgresql_where=text("andar_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    # Opcional só pelas unidades criadas antes da estrutura bloco/andar; o assistente sempre
    # preenche.
    andar_id: Mapped[uuid.UUID | None]
    identificacao: Mapped[str] = mapped_column(String(80))
    # Unidade com dados vinculados é desativada, nunca apagada (US-205).
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class ProprietarioUnidade(Base):
    """Proprietário cadastrado pela Administração (US-207). Dados pessoais: o documento não vai
    para o Morador (nucleo.md, seção 10)."""

    __tablename__ = "proprietarios_unidade"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_proprietarios_unidade_unidade",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["foto_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_proprietarios_unidade_foto",
            ondelete="RESTRICT",
        ),
        CheckConstraint("documento ~ '^([0-9]{11}|[0-9]{14})$'", name="documento_cpf_cnpj"),
        CheckConstraint("telefone ~ '^[0-9]{10,11}$'", name="telefone_digitos"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    nome: Mapped[str] = mapped_column(String(150))
    documento: Mapped[str | None] = mapped_column(String(14))
    emails: Mapped[list[str]] = mapped_column(ARRAY(String(254)), server_default=text("'{}'"))
    whatsapps: Mapped[list[str]] = mapped_column(ARRAY(String(11)), server_default=text("'{}'"))
    telefone: Mapped[str | None] = mapped_column(String(11))
    foto_arquivo_id: Mapped[uuid.UUID | None]


class ChaveAcesso(Base):
    """Chave que o Morador digita uma vez para se vincular à unidade (US-207, US-301)."""

    __tablename__ = "chaves_acesso"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_chaves_acesso_unidade",
            ondelete="RESTRICT",
        ),
        # Regenerar revoga a anterior: só uma chave vigente por unidade (regra 5).
        Index(
            "uq_chaves_acesso_unidade_vigente",
            "unidade_id",
            unique=True,
            postgresql_where=text("revogada_em IS NULL"),
        ),
        CheckConstraint("revogada_em IS NULL OR revogada_em >= criada_em", name="revogacao_valida"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    # Único em todo o sistema, inclusive entre chaves revogadas (regra 4).
    codigo: Mapped[str] = mapped_column(String(32), unique=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revogada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MoradorUnidade(Base):
    """Unidades de cada Morador (ADR 0003): um morador pode estar em várias unidades."""

    __tablename__ = "moradores_unidade"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_moradores_unidade_unidade",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "condominio_id", name="uq_moradores_unidade_id_condominio"),
        # Não se vincula duas vezes à mesma unidade; depois de desvinculado, pode voltar (regra 19).
        Index(
            "uq_moradores_unidade_ativo",
            "unidade_id",
            "usuario_id",
            unique=True,
            postgresql_where=text("status = 'ativo'"),
        ),
        CheckConstraint("status IN ('ativo', 'desvinculado')", name="status_valido"),
        CheckConstraint("origem IN ('chave', 'convite', 'cadastro')", name="origem_valida"),
        CheckConstraint(
            "(status = 'desvinculado') = (desvinculado_em IS NOT NULL)",
            name="desvinculo_com_data",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), server_default=text("'ativo'"))
    origem: Mapped[str] = mapped_column(String(20))
    # Grau de parentesco com o proprietário (US-303).
    parentesco: Mapped[str | None] = mapped_column(String(50))
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    desvinculado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desvinculado_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )


class PermissaoAba(Base):
    """Com Acesso ou Sem Acesso por aba, para cada morador em cada unidade (US-304)."""

    __tablename__ = "permissoes_aba"
    __table_args__ = (
        ForeignKeyConstraint(
            ["morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_permissoes_aba_morador_unidade",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "aba IN ('unidades', 'visitantes', 'veiculos', 'reservas', 'encomendas', "
            "'ocorrencias', 'usuarios')",
            name="aba_valida",
        ),
    )

    morador_unidade_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    aba: Mapped[str] = mapped_column(String(20), primary_key=True)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    com_acesso: Mapped[bool] = mapped_column(Boolean)
    alterado_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    alterado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConviteMorador(Base):
    """Convite por e-mail que gera o vínculo quando é aceito (US-303)."""

    __tablename__ = "convites_morador"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_convites_morador_unidade",
            ondelete="RESTRICT",
        ),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("expira_em > criado_em", name="validade_positiva"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    email: Mapped[str] = mapped_column(String(254))
    parentesco: Mapped[str | None] = mapped_column(String(50))
    # Abas que o convidado recebe ao aceitar, no formato {"aba": true|false}.
    permissoes_iniciais: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    convidado_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    aceito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
