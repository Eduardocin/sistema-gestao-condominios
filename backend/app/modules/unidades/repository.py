import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import BlocoCondominio, VinculoCondominio
from app.modules.unidades.models import SolicitacaoVinculoUnidade, Unidade
from app.modules.usuarios.models import Usuario


def obter_unidade(
    session: Session, *, condominio_id: uuid.UUID, bloco: str, identificacao: str
) -> Unidade | None:
    return session.scalar(
        select(Unidade)
        .join(BlocoCondominio, BlocoCondominio.id == Unidade.bloco_id)
        .where(
            Unidade.condominio_id == condominio_id,
            BlocoCondominio.condominio_id == condominio_id,
            BlocoCondominio.nome == bloco,
            Unidade.identificacao == identificacao,
        )
    )


def obter_vinculo_morador(
    session: Session, *, usuario_id: uuid.UUID, condominio_id: uuid.UUID, lock: bool = False
) -> VinculoCondominio | None:
    consulta = select(VinculoCondominio).where(
        VinculoCondominio.usuario_id == usuario_id,
        VinculoCondominio.condominio_id == condominio_id,
        VinculoCondominio.perfil == "morador",
    )
    if lock:
        consulta = consulta.with_for_update()
    return session.scalar(consulta)


def obter_solicitacao(
    session: Session, solicitacao_id: uuid.UUID, *, lock: bool = False
) -> SolicitacaoVinculoUnidade | None:
    consulta = select(SolicitacaoVinculoUnidade).where(
        SolicitacaoVinculoUnidade.id == solicitacao_id
    )
    if lock:
        consulta = consulta.with_for_update()
    return session.scalar(consulta)


def listar_pendentes(
    session: Session, *, condominio_id: uuid.UUID
) -> list[tuple[SolicitacaoVinculoUnidade, Usuario, Unidade, BlocoCondominio]]:
    consulta = (
        select(SolicitacaoVinculoUnidade, Usuario, Unidade, BlocoCondominio)
        .join(Usuario, Usuario.id == SolicitacaoVinculoUnidade.usuario_id)
        .join(Unidade, Unidade.id == SolicitacaoVinculoUnidade.unidade_id)
        .join(BlocoCondominio, BlocoCondominio.id == Unidade.bloco_id)
        .where(
            SolicitacaoVinculoUnidade.condominio_id == condominio_id,
            SolicitacaoVinculoUnidade.status == "pendente",
        )
        .order_by(
            SolicitacaoVinculoUnidade.solicitado_em,
            SolicitacaoVinculoUnidade.id,
        )
    )
    return list(session.execute(consulta).tuples().all())


def obter_vinculo_administracao(
    session: Session, *, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> VinculoCondominio | None:
    return session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.condominio_id == condominio_id,
            VinculoCondominio.perfil == "administracao",
            VinculoCondominio.ativo.is_(True),
        )
    )


def obter_principal_aprovado(
    session: Session, *, unidade_id: uuid.UUID, exceto_id: uuid.UUID
) -> SolicitacaoVinculoUnidade | None:
    return session.scalar(
        select(SolicitacaoVinculoUnidade).where(
            SolicitacaoVinculoUnidade.unidade_id == unidade_id,
            SolicitacaoVinculoUnidade.status == "aprovado",
            SolicitacaoVinculoUnidade.responsavel_principal.is_(True),
            SolicitacaoVinculoUnidade.id != exceto_id,
        )
    )
