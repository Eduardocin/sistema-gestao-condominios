import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.usuarios.models import Usuario


def obter_por_email(
    session: Session, email: str, *, exceto_usuario_id: uuid.UUID | None = None
) -> Usuario | None:
    consulta = select(Usuario).where(Usuario.email == email)
    if exceto_usuario_id is not None:
        consulta = consulta.where(Usuario.id != exceto_usuario_id)
    return session.scalar(consulta)


def obter_por_cpf(
    session: Session, cpf: str, *, exceto_usuario_id: uuid.UUID | None = None
) -> Usuario | None:
    consulta = select(Usuario).where(Usuario.cpf == cpf)
    if exceto_usuario_id is not None:
        consulta = consulta.where(Usuario.id != exceto_usuario_id)
    return session.scalar(consulta)


def obter_condominio(session: Session, condominio_id: uuid.UUID) -> Condominio | None:
    return session.get(Condominio, condominio_id)


def listar_vinculos(
    session: Session, usuario_id: uuid.UUID
) -> list[tuple[VinculoCondominio, Condominio]]:
    consulta = (
        select(VinculoCondominio, Condominio)
        .join(Condominio, Condominio.id == VinculoCondominio.condominio_id)
        .where(VinculoCondominio.usuario_id == usuario_id, VinculoCondominio.ativo.is_(True))
        .order_by(Condominio.nome)
    )
    return list(session.execute(consulta).tuples().all())


def perfil_no_condominio(
    session: Session, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> str | None:
    return session.scalar(
        select(VinculoCondominio.perfil).where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.condominio_id == condominio_id,
            VinculoCondominio.ativo.is_(True),
        )
    )
