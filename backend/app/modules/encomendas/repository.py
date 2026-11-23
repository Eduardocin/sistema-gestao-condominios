from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.contexto import ContextoCondominio
from app.core.tempo import FUSO_CONDOMINIO
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import Andar, Bloco, MoradorUnidade, PermissaoAba, Unidade
from app.modules.usuarios.models import Usuario

_DestinatarioLink = aliased(MoradorUnidade)
_DestinatarioUsuario = aliased(Usuario)
_FuncionarioRecebimento = aliased(Funcionario)
_RecebedorLink = aliased(MoradorUnidade)
_RecebedorUsuario = aliased(Usuario)
_FuncionarioEntrega = aliased(Funcionario)
_MoradorConfirmacao = aliased(Usuario)


@dataclass(frozen=True)
class LinhaEncomenda:
    encomenda: Encomenda
    unidade_id: UUID
    unidade_identificacao: str
    destinatario_id: UUID
    destinatario_nome: str
    recebimento_funcionario_id: UUID
    recebimento_funcionario_nome: str
    recebedor_id: UUID | None
    recebedor_usuario_id: UUID | None
    recebedor_status: str | None
    recebedor_nome: str | None
    entrega_funcionario_id: UUID | None
    entrega_funcionario_nome: str | None
    confirmacao_morador_id: UUID | None
    confirmacao_morador_nome: str | None


@dataclass(frozen=True)
class ReferenciasRecebimento:
    funcionario: Funcionario
    destinatario_email: str


@dataclass(frozen=True)
class ReferenciasEntrega:
    funcionario: Funcionario
    recebedor: MoradorUnidade


def _filtros(
    contexto: ContextoCondominio,
    *,
    busca: str | None = None,
    status: str | None = None,
    unidade_id: UUID | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
):
    filtros = [Encomenda.condominio_id == contexto.condominio_id]
    if unidade_id is not None:
        filtros.append(Encomenda.unidade_id == unidade_id)
    # O período é de datas de negócio (inclusivas) no fuso do condomínio, não em UTC.
    if data_de is not None:
        filtros.append(
            Encomenda.registrada_em >= datetime.combine(data_de, time.min, FUSO_CONDOMINIO)
        )
    if data_ate is not None:
        filtros.append(
            Encomenda.registrada_em
            < datetime.combine(data_ate + timedelta(days=1), time.min, FUSO_CONDOMINIO)
        )
    if contexto.perfil == "morador":
        link = aliased(MoradorUnidade)
        permissao = aliased(PermissaoAba)
        acesso = (
            select(1)
            .select_from(link)
            .join(
                permissao,
                and_(
                    permissao.morador_unidade_id == link.id,
                    permissao.condominio_id == link.condominio_id,
                ),
            )
            .where(
                link.usuario_id == contexto.usuario_id,
                link.unidade_id == Encomenda.unidade_id,
                link.condominio_id == contexto.condominio_id,
                link.status == "ativo",
                permissao.aba == "encomendas",
                permissao.com_acesso.is_(True),
            )
            .exists()
        )
        filtros.append(acesso)
    if status is not None:
        filtros.append(Encomenda.status == status)
    termo = busca.strip() if busca else ""
    if termo:
        padrao = f"%{termo}%"
        filtros.append(
            or_(
                Encomenda.descricao.ilike(padrao),
                Unidade.identificacao.ilike(padrao),
                _DestinatarioUsuario.nome.ilike(padrao),
            )
        )
    return filtros


def _consulta_linhas(contexto: ContextoCondominio):
    return (
        select(
            Encomenda,
            Unidade.id,
            Unidade.identificacao,
            _DestinatarioLink.id,
            _DestinatarioUsuario.nome,
            _FuncionarioRecebimento.id,
            _FuncionarioRecebimento.nome,
            _RecebedorLink.id,
            _RecebedorLink.usuario_id,
            _RecebedorLink.status,
            _RecebedorUsuario.nome,
            _FuncionarioEntrega.id,
            _FuncionarioEntrega.nome,
            _MoradorConfirmacao.id,
            _MoradorConfirmacao.nome,
        )
        .select_from(Encomenda)
        .join(
            Unidade,
            and_(
                Unidade.id == Encomenda.unidade_id,
                Unidade.condominio_id == Encomenda.condominio_id,
            ),
        )
        .join(
            _DestinatarioLink,
            and_(
                _DestinatarioLink.id == Encomenda.destinatario_morador_unidade_id,
                _DestinatarioLink.condominio_id == Encomenda.condominio_id,
            ),
        )
        .join(_DestinatarioUsuario, _DestinatarioUsuario.id == _DestinatarioLink.usuario_id)
        .join(
            _FuncionarioRecebimento,
            and_(
                _FuncionarioRecebimento.id == Encomenda.recebido_por_funcionario_id,
                _FuncionarioRecebimento.condominio_id == Encomenda.condominio_id,
            ),
        )
        .outerjoin(
            _RecebedorLink,
            and_(
                _RecebedorLink.id == Encomenda.recebedor_morador_unidade_id,
                _RecebedorLink.condominio_id == Encomenda.condominio_id,
            ),
        )
        .outerjoin(_RecebedorUsuario, _RecebedorUsuario.id == _RecebedorLink.usuario_id)
        .outerjoin(
            _FuncionarioEntrega,
            and_(
                _FuncionarioEntrega.id == Encomenda.entregue_por_funcionario_id,
                _FuncionarioEntrega.condominio_id == Encomenda.condominio_id,
            ),
        )
        .outerjoin(
            _MoradorConfirmacao,
            and_(
                _MoradorConfirmacao.id == Encomenda.confirmado_por_usuario_id,
                _MoradorConfirmacao.id == _RecebedorLink.usuario_id,
            ),
        )
        .where(Encomenda.condominio_id == contexto.condominio_id)
    )


def listar(
    session: Session,
    contexto: ContextoCondominio,
    *,
    busca: str | None,
    status: str | None,
    unidade_id: UUID | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    page: int,
    page_size: int,
) -> tuple[list[LinhaEncomenda], int]:
    filtros = _filtros(
        contexto,
        busca=busca,
        status=status,
        unidade_id=unidade_id,
        data_de=data_de,
        data_ate=data_ate,
    )
    consulta = (
        _consulta_linhas(contexto)
        .where(*filtros)
        .order_by(Encomenda.registrada_em.desc(), Encomenda.id.desc())
    )
    linhas = session.execute(consulta.offset((page - 1) * page_size).limit(page_size)).tuples()
    consulta_total = (
        select(func.count(Encomenda.id))
        .select_from(Encomenda)
        .join(
            Unidade,
            and_(
                Unidade.id == Encomenda.unidade_id,
                Unidade.condominio_id == Encomenda.condominio_id,
            ),
        )
        .join(
            _DestinatarioLink,
            and_(
                _DestinatarioLink.id == Encomenda.destinatario_morador_unidade_id,
                _DestinatarioLink.condominio_id == Encomenda.condominio_id,
            ),
        )
        .join(_DestinatarioUsuario, _DestinatarioUsuario.id == _DestinatarioLink.usuario_id)
        .where(*filtros)
    )
    total = session.scalar(consulta_total) or 0
    return [LinhaEncomenda(*linha) for linha in linhas], total


def contagem_por_unidade_e_status(
    session: Session,
    contexto: ContextoCondominio,
    *,
    unidade_id: UUID | None,
    data_de: date | None,
    data_ate: date | None,
) -> list[tuple[UUID, str, str, int]]:
    """(unidade, identificação, status, quantidade) das encomendas do período (US-404)."""
    filtros = _filtros(contexto, unidade_id=unidade_id, data_de=data_de, data_ate=data_ate)
    consulta = (
        select(Unidade.id, Unidade.identificacao, Encomenda.status, func.count(Encomenda.id))
        .select_from(Encomenda)
        .join(
            Unidade,
            and_(
                Unidade.id == Encomenda.unidade_id,
                Unidade.condominio_id == Encomenda.condominio_id,
            ),
        )
        .where(*filtros)
        .group_by(Unidade.id, Unidade.identificacao, Encomenda.status)
    )
    return [
        (unidade, ident, status, total)
        for unidade, ident, status, total in session.execute(consulta)
    ]


def obter(session: Session, condominio_id: UUID, encomenda_id: UUID) -> Encomenda | None:
    return session.scalar(
        select(Encomenda).where(
            Encomenda.id == encomenda_id,
            Encomenda.condominio_id == condominio_id,
        )
    )


def obter_para_atualizacao(
    session: Session, condominio_id: UUID, encomenda_id: UUID
) -> Encomenda | None:
    return session.scalar(
        select(Encomenda)
        .where(
            Encomenda.id == encomenda_id,
            Encomenda.condominio_id == condominio_id,
        )
        .with_for_update()
    )


def obter_linha(
    session: Session, contexto: ContextoCondominio, encomenda_id: UUID
) -> LinhaEncomenda | None:
    linha = (
        session.execute(_consulta_linhas(contexto).where(Encomenda.id == encomenda_id))
        .tuples()
        .one_or_none()
    )
    return LinhaEncomenda(*linha) if linha is not None else None


def listar_unidades(
    session: Session,
    condominio_id: UUID,
    *,
    busca: str | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[Unidade, str | None, str | None]], int]:
    filtros = [Unidade.condominio_id == condominio_id, Unidade.ativo.is_(True)]
    termo = busca.strip() if busca else ""
    if termo:
        filtros.append(Unidade.identificacao.ilike(f"%{termo}%"))
    consulta = (
        select(Unidade, Bloco.nome, Andar.nome)
        .outerjoin(Andar, and_(Andar.id == Unidade.andar_id, Andar.condominio_id == condominio_id))
        .outerjoin(Bloco, and_(Bloco.id == Andar.bloco_id, Bloco.condominio_id == condominio_id))
        .where(*filtros)
        .order_by(Unidade.identificacao, Bloco.nome, Andar.ordem, Andar.nome, Unidade.id)
    )
    total = session.scalar(select(func.count(Unidade.id)).where(*filtros)) or 0
    unidades = session.execute(consulta.offset((page - 1) * page_size).limit(page_size)).tuples()
    return list(unidades), total


def obter_unidade_ativa(session: Session, condominio_id: UUID, unidade_id: UUID) -> Unidade | None:
    return session.scalar(
        select(Unidade).where(
            Unidade.id == unidade_id,
            Unidade.condominio_id == condominio_id,
            Unidade.ativo.is_(True),
        )
    )


def obter_referencias_recebimento(
    session: Session,
    condominio_id: UUID,
    *,
    unidade_id: UUID,
    destinatario_morador_unidade_id: UUID,
    recebido_por_funcionario_id: UUID,
) -> ReferenciasRecebimento | None:
    unidade = session.scalar(
        select(Unidade)
        .where(
            Unidade.id == unidade_id,
            Unidade.condominio_id == condominio_id,
            Unidade.ativo.is_(True),
        )
        .with_for_update(read=True)
    )
    if unidade is None:
        return None

    destinatario = session.execute(
        select(MoradorUnidade, Usuario.email)
        .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
        .where(
            MoradorUnidade.id == destinatario_morador_unidade_id,
            MoradorUnidade.condominio_id == condominio_id,
            MoradorUnidade.unidade_id == unidade.id,
            MoradorUnidade.status == "ativo",
            Usuario.ativo.is_(True),
        )
        .with_for_update(read=True)
    ).one_or_none()
    if destinatario is None:
        return None

    funcionario = session.scalar(
        select(Funcionario)
        .where(
            Funcionario.id == recebido_por_funcionario_id,
            Funcionario.condominio_id == condominio_id,
            Funcionario.ativo.is_(True),
        )
        .with_for_update(read=True)
    )
    if funcionario is None:
        return None

    return ReferenciasRecebimento(
        funcionario=funcionario,
        destinatario_email=destinatario.email,
    )


def obter_referencias_entrega(
    session: Session,
    condominio_id: UUID,
    unidade_id: UUID,
    *,
    recebedor_morador_unidade_id: UUID,
    entregue_por_funcionario_id: UUID,
) -> ReferenciasEntrega | None:
    recebedor = session.scalar(
        select(MoradorUnidade)
        .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
        .where(
            MoradorUnidade.id == recebedor_morador_unidade_id,
            MoradorUnidade.condominio_id == condominio_id,
            MoradorUnidade.unidade_id == unidade_id,
            MoradorUnidade.status == "ativo",
            Usuario.ativo.is_(True),
            select(1)
            .select_from(PermissaoAba)
            .where(
                PermissaoAba.morador_unidade_id == MoradorUnidade.id,
                PermissaoAba.condominio_id == condominio_id,
                PermissaoAba.aba == "encomendas",
                PermissaoAba.com_acesso.is_(True),
            )
            .exists(),
        )
        .with_for_update(read=True)
    )
    if recebedor is None:
        return None

    funcionario = session.scalar(
        select(Funcionario)
        .where(
            Funcionario.id == entregue_por_funcionario_id,
            Funcionario.condominio_id == condominio_id,
            Funcionario.ativo.is_(True),
        )
        .with_for_update(read=True)
    )
    if funcionario is None:
        return None

    return ReferenciasEntrega(
        funcionario=funcionario,
        recebedor=recebedor,
    )


def recebedor_ativo(
    session: Session,
    condominio_id: UUID,
    unidade_id: UUID,
    morador_unidade_id: UUID,
    usuario_id: UUID,
) -> bool:
    return (
        session.scalar(
            select(MoradorUnidade.id)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
            .where(
                MoradorUnidade.id == morador_unidade_id,
                MoradorUnidade.condominio_id == condominio_id,
                MoradorUnidade.unidade_id == unidade_id,
                MoradorUnidade.usuario_id == usuario_id,
                MoradorUnidade.status == "ativo",
                Usuario.ativo.is_(True),
                select(1)
                .select_from(PermissaoAba)
                .where(
                    PermissaoAba.morador_unidade_id == MoradorUnidade.id,
                    PermissaoAba.condominio_id == condominio_id,
                    PermissaoAba.aba == "encomendas",
                    PermissaoAba.com_acesso.is_(True),
                )
                .exists(),
            )
            .with_for_update(read=True)
        )
        is not None
    )


def listar_moradores(
    session: Session,
    condominio_id: UUID,
    unidade_id: UUID,
    *,
    page: int,
    page_size: int,
    somente_confirmaveis: bool = False,
) -> tuple[list[tuple[MoradorUnidade, str]], int]:
    filtros = [
        MoradorUnidade.condominio_id == condominio_id,
        MoradorUnidade.unidade_id == unidade_id,
        MoradorUnidade.status == "ativo",
        Usuario.ativo.is_(True),
    ]
    if somente_confirmaveis:
        filtros.append(
            select(1)
            .select_from(PermissaoAba)
            .where(
                PermissaoAba.morador_unidade_id == MoradorUnidade.id,
                PermissaoAba.condominio_id == condominio_id,
                PermissaoAba.aba == "encomendas",
                PermissaoAba.com_acesso.is_(True),
            )
            .exists()
        )
    consulta = (
        select(MoradorUnidade, Usuario.nome)
        .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
        .where(*filtros)
        .order_by(Usuario.nome, MoradorUnidade.id)
    )
    total = (
        session.scalar(
            select(func.count(MoradorUnidade.id))
            .select_from(MoradorUnidade)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
            .where(*filtros)
        )
        or 0
    )
    moradores = (
        session.execute(consulta.offset((page - 1) * page_size).limit(page_size)).tuples().all()
    )
    return list(moradores), total
