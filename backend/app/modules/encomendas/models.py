import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Encomenda(Base):
    """Encomenda registrada pela portaria e confirmada depois pelo morador que recebeu
    (US-401, US-403; DER, seção 4, "Encomendas: entrega e confirmação")."""

    __tablename__ = "encomendas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["unidade_id", "condominio_id"],
            ["unidades.id", "unidades.condominio_id"],
            name="fk_encomendas_unidade",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["destinatario_morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_encomendas_destinatario",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["foto_nota_arquivo_id", "condominio_id"],
            ["arquivos.id", "arquivos.condominio_id"],
            name="fk_encomendas_foto_nota",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recebido_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_encomendas_recebido_por",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["recebedor_morador_unidade_id", "condominio_id"],
            ["moradores_unidade.id", "moradores_unidade.condominio_id"],
            name="fk_encomendas_recebedor",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entregue_por_funcionario_id", "condominio_id"],
            ["funcionarios.id", "funcionarios.condominio_id"],
            name="fk_encomendas_entregue_por",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('aguardando_retirada', 'entregue_aguardando_confirmacao', "
            "'retirada_confirmada')",
            name="status_valido",
        ),
        # Cada estado exige todos os dados da sua etapa, ou nenhum (RN-45).
        CheckConstraint(
            "(status = 'aguardando_retirada'"
            " AND entregue_em IS NULL AND recebedor_morador_unidade_id IS NULL"
            " AND entregue_por_funcionario_id IS NULL"
            " AND confirmada_em IS NULL AND confirmado_por_usuario_id IS NULL)"
            " OR (status = 'entregue_aguardando_confirmacao'"
            " AND entregue_em IS NOT NULL AND recebedor_morador_unidade_id IS NOT NULL"
            " AND entregue_por_funcionario_id IS NOT NULL"
            " AND confirmada_em IS NULL AND confirmado_por_usuario_id IS NULL)"
            " OR (status = 'retirada_confirmada'"
            " AND entregue_em IS NOT NULL AND recebedor_morador_unidade_id IS NOT NULL"
            " AND entregue_por_funcionario_id IS NOT NULL"
            " AND confirmada_em IS NOT NULL AND confirmado_por_usuario_id IS NOT NULL)",
            name="etapas_completas",
        ),
        CheckConstraint(
            "entregue_em IS NULL OR entregue_em >= registrada_em", name="entrega_apos_registro"
        ),
        CheckConstraint(
            "confirmada_em IS NULL OR confirmada_em >= entregue_em", name="confirmacao_apos_entrega"
        ),
        Index(
            "ix_encomendas_condominio_status_registrada", "condominio_id", "status", "registrada_em"
        ),
        Index("ix_encomendas_unidade_registrada", "unidade_id", "registrada_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    condominio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("condominios.id", ondelete="RESTRICT"), index=True
    )
    unidade_id: Mapped[uuid.UUID]
    destinatario_morador_unidade_id: Mapped[uuid.UUID]
    descricao: Mapped[str] = mapped_column(String(200))
    foto_nota_arquivo_id: Mapped[uuid.UUID]
    recebido_por_funcionario_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(40), server_default=text("'aguardando_retirada'"))
    registrada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recebedor_morador_unidade_id: Mapped[uuid.UUID | None]
    entregue_por_funcionario_id: Mapped[uuid.UUID | None]
    confirmada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmado_por_usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT")
    )
