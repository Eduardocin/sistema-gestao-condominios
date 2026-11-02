"""Consultas ao banco usadas pelo login. Aqui só se lê e escreve; nenhuma regra de negócio."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario


def obter_usuario_por_email(session: Session, email: str) -> Usuario | None:
    return session.scalar(select(Usuario).where(Usuario.email == email))


def obter_usuario_por_id(session: Session, usuario_id: uuid.UUID) -> Usuario | None:
    return session.get(Usuario, usuario_id)


def listar_vinculos_ativos(
    session: Session, usuario_id: uuid.UUID
) -> list[tuple[VinculoCondominio, Condominio]]:
    """Vínculos ativos do usuário, já com o condomínio de cada um (ordem alfabética)."""
    consulta = (
        select(VinculoCondominio, Condominio)
        .join(Condominio, Condominio.id == VinculoCondominio.condominio_id)
        .where(VinculoCondominio.usuario_id == usuario_id, VinculoCondominio.ativo.is_(True))
        .order_by(Condominio.nome)
    )
    return list(session.execute(consulta).tuples().all())


def obter_vinculo_ativo(
    session: Session, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> tuple[VinculoCondominio, Condominio] | None:
    consulta = (
        select(VinculoCondominio, Condominio)
        .join(Condominio, Condominio.id == VinculoCondominio.condominio_id)
        .where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.condominio_id == condominio_id,
            VinculoCondominio.ativo.is_(True),
        )
    )
    linha = session.execute(consulta).tuples().first()
    return linha


def obter_unidade(
    session: Session, unidade_id: uuid.UUID, condominio_id: uuid.UUID
) -> Unidade | None:
    # O filtro por condomínio é de propósito: mesmo vindo de um vínculo, a unidade
    # só vale se pertencer ao condomínio do token.
    return session.scalar(
        select(Unidade).where(Unidade.id == unidade_id, Unidade.condominio_id == condominio_id)
    )


def listar_unidades_do_vinculo(
    session: Session, *, vinculo_id: uuid.UUID, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> set[uuid.UUID]:
    unidade_id = session.scalar(
        select(VinculoCondominio.unidade_id).where(
            VinculoCondominio.id == vinculo_id,
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.condominio_id == condominio_id,
            VinculoCondominio.ativo.is_(True),
        )
    )
    return {unidade_id} if unidade_id is not None else set()
