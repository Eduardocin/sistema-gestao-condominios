"""Consultas ao banco do login e da autorização. Só lê e escreve; sem regra de negócio."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import MoradorUnidade, PermissaoAba, Unidade
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


def listar_unidades_do_morador(
    session: Session, *, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> set[uuid.UUID]:
    """Unidades em que o usuário mora hoje neste condomínio (ADR 0003).

    Lê `moradores_unidade`, só os vínculos ativos: quem foi desvinculado deixa de enxergar a
    unidade na requisição seguinte (R6). A coluna antiga `vinculos_condominio.unidade_id` não é
    mais consultada aqui.
    """
    consulta = select(MoradorUnidade.unidade_id).where(
        MoradorUnidade.usuario_id == usuario_id,
        MoradorUnidade.condominio_id == condominio_id,
        MoradorUnidade.status == "ativo",
    )
    return set(session.scalars(consulta))


def morador_tem_acesso_a_aba(
    session: Session,
    *,
    usuario_id: uuid.UUID,
    condominio_id: uuid.UUID,
    unidade_id: uuid.UUID,
    aba: str,
) -> bool:
    """O morador está Com Acesso a esta aba, nesta unidade? (US-304)

    A permissão é por morador *e* unidade: estar Com Acesso na 101 não vale para a 102. Sem a
    linha da aba (ou com o vínculo desfeito), a resposta é False: negar por padrão.
    """
    com_acesso = session.scalar(
        select(PermissaoAba.com_acesso)
        .join(
            MoradorUnidade,
            (MoradorUnidade.id == PermissaoAba.morador_unidade_id)
            & (MoradorUnidade.condominio_id == PermissaoAba.condominio_id),
        )
        .where(
            MoradorUnidade.usuario_id == usuario_id,
            MoradorUnidade.condominio_id == condominio_id,
            MoradorUnidade.unidade_id == unidade_id,
            MoradorUnidade.status == "ativo",
            PermissaoAba.aba == aba,
        )
    )
    return com_acesso is True
