import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TipoEventoAuditoria(StrEnum):
    LOGIN = "login"
    FALHA_LOGIN = "falha_login"
    APROVACAO = "aprovacao"
    REJEICAO = "rejeicao"
    MUDANCA_PERMISSAO = "mudanca_permissao"
    RESERVA = "reserva"
    OCORRENCIA = "ocorrencia"
    CRIACAO_CONTA = "criacao_conta"
    EDICAO_CONTA = "edicao_conta"
    NOTIFICACAO_CONDOMINIO = "notificacao_condominio"


PERFIS_CONTAS_COMPARTILHADAS = frozenset({"administracao", "funcionario"})


class EventoAuditoria(Base):
    __tablename__ = "eventos_auditoria"
    __table_args__ = (
        CheckConstraint(
            "tipo_evento IN "
            "('login', 'falha_login', 'aprovacao', 'rejeicao', 'mudanca_permissao', "
            "'reserva', 'ocorrencia', 'criacao_conta', 'edicao_conta', "
            "'notificacao_condominio')",
            name="tipo_evento_valido",
        ),
        CheckConstraint(
            "NOT conta_compartilhada OR "
            "(nome_responsavel IS NOT NULL AND length(trim(nome_responsavel)) > 0)",
            name="responsavel_conta_compartilhada",
        ),
        CheckConstraint(
            "perfil NOT IN ('administracao', 'funcionario') OR "
            "(conta_compartilhada AND nome_responsavel IS NOT NULL "
            "AND length(trim(nome_responsavel)) > 0)",
            name="perfil_compartilhado_com_responsavel",
        ),
        Index("ix_eventos_auditoria_condominio_criado_em", "condominio_id", "criado_em"),
        Index("ix_eventos_auditoria_usuario_criado_em", "usuario_id", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
    ator: Mapped[str | None] = mapped_column(String(254))
    perfil: Mapped[str | None] = mapped_column(String(30))
    condominio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT")
    )
    tipo_evento: Mapped[str] = mapped_column(String(30))
    recurso: Mapped[str] = mapped_column(String(100))
    recurso_id: Mapped[str | None] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(45))
    dados_antes: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    dados_depois: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    conta_compartilhada: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    nome_responsavel: Mapped[str | None] = mapped_column(String(150))
