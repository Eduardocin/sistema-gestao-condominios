import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import ChaveAcesso, Condominio, VinculoCondominio
from app.modules.usuarios.models import Usuario


def listar_pendentes(session: Session) -> list[tuple[Condominio, Usuario | None]]:
    consulta = (
        select(Condominio, Usuario)
        .outerjoin(Usuario, Usuario.id == Condominio.solicitante_id)
        .where(Condominio.status == "pendente")
        .order_by(Condominio.criado_em, Condominio.id)
    )
    return list(session.execute(consulta).tuples().all())


def obter_condominio(
    session: Session, condominio_id: uuid.UUID, *, lock: bool = False
) -> Condominio | None:
    consulta = select(Condominio).where(Condominio.id == condominio_id)
    if lock:
        consulta = consulta.with_for_update()
    return session.scalar(consulta)


def obter_administracao(
    session: Session, condominio_id: uuid.UUID, *, lock: bool = False
) -> tuple[Usuario, VinculoCondominio] | None:
    consulta = (
        select(Usuario, VinculoCondominio)
        .join(VinculoCondominio, VinculoCondominio.usuario_id == Usuario.id)
        .where(
            VinculoCondominio.condominio_id == condominio_id,
            VinculoCondominio.perfil == "administracao",
        )
        .order_by(VinculoCondominio.criado_em)
        .limit(1)
    )
    if lock:
        consulta = consulta.with_for_update()
    return session.execute(consulta).tuples().first()


def obter_chave_disponivel(
    session: Session, condominio_id: uuid.UUID, *, lock: bool = False
) -> ChaveAcesso | None:
    consulta = select(ChaveAcesso).where(
        ChaveAcesso.condominio_id == condominio_id,
        ChaveAcesso.usada_em.is_(None),
        ChaveAcesso.revogada_em.is_(None),
    )
    if lock:
        consulta = consulta.with_for_update()
    return session.scalar(consulta)


def obter_chave_por_hash(
    session: Session, codigo_hash: str, *, lock: bool = False
) -> tuple[ChaveAcesso, Condominio] | None:
    consulta = (
        select(ChaveAcesso, Condominio)
        .join(Condominio, Condominio.id == ChaveAcesso.condominio_id)
        .where(ChaveAcesso.codigo_hash == codigo_hash)
    )
    if lock:
        consulta = consulta.with_for_update(of=ChaveAcesso)
    return session.execute(consulta).tuples().first()


def obter_solicitacao_por_token(
    session: Session, condominio_id: uuid.UUID, token_hash: str
) -> Condominio | None:
    return session.scalar(
        select(Condominio).where(
            Condominio.id == condominio_id,
            Condominio.token_status_solicitacao_hash == token_hash,
        )
    )
