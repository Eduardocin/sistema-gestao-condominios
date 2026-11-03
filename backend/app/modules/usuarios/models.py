import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Telefone e documento ficam só com dígitos; a máscara é coisa da tela (DER, seção 1).
        CheckConstraint("telefone ~ '^[0-9]{10,11}$'", name="telefone_digitos"),
        CheckConstraint("documento ~ '^([0-9]{11}|[0-9]{14})$'", name="documento_cpf_cnpj"),
        CheckConstraint(
            "tipo_cadastro IN ('morador', 'administracao')", name="tipo_cadastro_valido"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # Login por e-mail ou telefone (US-101) e CPF/CNPJ da conta de Administração (US-201).
    telefone: Mapped[str | None] = mapped_column(String(11), unique=True)
    documento: Mapped[str | None] = mapped_column(String(14), unique=True)
    # Separa a conta de morador da conta de Administração, que pode cadastrar prédios
    # (nucleo.md, seção 10). Nulo nas contas compartilhadas e no ADM da plataforma.
    tipo_cadastro: Mapped[str | None] = mapped_column(String(20))
    administrador_plataforma: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Hash argon2id da senha. Nunca guardamos a senha pura. Fica opcional por enquanto porque o
    # cadastro de contas (US-104/US-201) ainda não existe; quando existir, passa a ser obrigatório.
    senha_hash: Mapped[str | None] = mapped_column(String(255))
    # Vira o claim `sv` do token. Somar 1 aqui derruba todas as sessões da conta de uma vez
    # (troca de senha, por exemplo), sem precisar guardar tokens no banco.
    sessao_versao: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    # use_alter: arquivos também aponta para usuarios, então a FK entra depois das duas tabelas.
    foto_arquivo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("arquivos.id", ondelete="RESTRICT", use_alter=True)
    )
    email_confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Consentimento de uso dos dados pessoais (US-1007).
    consentimento_dados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenRecuperacaoSenha(Base):
    """Link de uso único da recuperação de senha (US-102). Só o hash do token vai para o banco."""

    __tablename__ = "tokens_recuperacao_senha"
    __table_args__ = (CheckConstraint("expira_em > criado_em", name="validade_positiva"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TentativaChaveAcesso(Base):
    """Histórico das tentativas de vínculo por chave, para o limite de erros seguidos (US-301)."""

    __tablename__ = "tentativas_chave_acesso"
    __table_args__ = (
        Index("ix_tentativas_chave_acesso_usuario_criado", "usuario_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    sucesso: Mapped[bool] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
