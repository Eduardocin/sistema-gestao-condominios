"""Consultas dos comunicados. Só aqui se fala com o banco.

O comunicado é do sistema, não de um condomínio: o ADM vê todos, e a Administração só os que
foram enviados ao seu condomínio (`comunicado_destinatarios`, preenchida no momento do envio).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.avisos.models import Comunicado, ComunicadoDestinatario
from app.modules.condominios.models import Condominio
from app.modules.usuarios.models import Usuario


@dataclass(frozen=True)
class ComunicadoDetalhado:
    comunicado: Comunicado
    enviado_por_nome: str
    total_destinatarios: int


def _total_de_destinatarios() -> Any:
    return (
        select(func.count())
        .select_from(ComunicadoDestinatario)
        .where(ComunicadoDestinatario.comunicado_id == Comunicado.id)
        .correlate(Comunicado)
        .scalar_subquery()
    )


def ids_dos_condominios_ativos(session: Session) -> list[uuid.UUID]:
    """Travados em modo compartilhado (`FOR SHARE`): um condomínio não é desativado no meio do
    envio. Um condomínio que acaba de ser aprovado entra ou não, conforme quem commitou antes."""
    return list(
        session.scalars(
            select(Condominio.id)
            .where(Condominio.status == "ativo")
            .order_by(Condominio.id)
            .with_for_update(read=True)
        )
    )


def criar(
    session: Session,
    *,
    titulo: str,
    texto: str,
    enviado_por: uuid.UUID,
    destinatarios: list[uuid.UUID],
) -> Comunicado:
    comunicado = Comunicado(titulo=titulo, texto=texto, enviado_por_usuario_id=enviado_por)
    session.add(comunicado)
    session.flush()
    session.add_all(
        ComunicadoDestinatario(comunicado_id=comunicado.id, condominio_id=condominio_id)
        for condominio_id in destinatarios
    )
    session.flush()
    session.refresh(comunicado)
    return comunicado


def detalhado(session: Session, comunicado_id: uuid.UUID) -> ComunicadoDetalhado | None:
    linha = session.execute(
        select(Comunicado, Usuario.nome, _total_de_destinatarios())
        .join(Usuario, Usuario.id == Comunicado.enviado_por_usuario_id)
        .where(Comunicado.id == comunicado_id)
    ).first()
    return None if linha is None else ComunicadoDetalhado(linha[0], linha[1], linha[2])


def pagina(
    session: Session, *, limite: int, deslocamento: int
) -> tuple[list[ComunicadoDetalhado], int]:
    linhas = session.execute(
        select(Comunicado, Usuario.nome, _total_de_destinatarios())
        .join(Usuario, Usuario.id == Comunicado.enviado_por_usuario_id)
        .order_by(Comunicado.criado_em.desc(), Comunicado.id)
        .limit(limite)
        .offset(deslocamento)
    )
    total = session.scalar(select(func.count()).select_from(Comunicado)) or 0
    return [ComunicadoDetalhado(c, nome, n) for c, nome, n in linhas], total


def destinatarios(session: Session, comunicado_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    linhas = session.execute(
        select(Condominio.id, Condominio.nome)
        .join(ComunicadoDestinatario, ComunicadoDestinatario.condominio_id == Condominio.id)
        .where(ComunicadoDestinatario.comunicado_id == comunicado_id)
        .order_by(Condominio.nome, Condominio.id)
    )
    return [(i, nome) for i, nome in linhas]


def pagina_do_condominio(
    session: Session, condominio_id: uuid.UUID, *, limite: int, deslocamento: int
) -> tuple[list[Comunicado], int]:
    """Só os comunicados enviados a este condomínio, do mais recente ao mais antigo."""
    enviados = (
        select(Comunicado)
        .join(ComunicadoDestinatario, ComunicadoDestinatario.comunicado_id == Comunicado.id)
        .where(ComunicadoDestinatario.condominio_id == condominio_id)
    )
    itens = list(
        session.scalars(
            enviados.order_by(Comunicado.criado_em.desc(), Comunicado.id)
            .limit(limite)
            .offset(deslocamento)
        )
    )
    total = session.scalar(select(func.count()).select_from(enviados.subquery())) or 0
    return itens, total
