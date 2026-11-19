"""Cadastro e consultas do condomínio.

O cadastro/listagem da Administração usa os vínculos da conta. A análise global por ID
é exclusiva das rotas de plataforma. Na criação, o escopo dos filhos é o UUID gerado
pelo servidor; o cliente não fornece IDs de condomínio, bloco, andar ou criador.
"""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.condominios.models import (
    Condominio,
    CondominioAnalise,
    CondominioDocumento,
    VinculoCondominio,
)
from app.modules.condominios.schemas import (
    BlocoEntrada,
    CadastroCondominio,
    ContagemEstrutura,
    FiltrosFila,
)
from app.modules.notificacoes.models import EnvioEmail
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Andar, Bloco, Unidade
from app.modules.usuarios.models import Usuario


def criar_condominio(
    session: Session, dados: CadastroCondominio, *, usuario_id: uuid.UUID, momento: datetime
) -> Condominio:
    condominio = Condominio(
        nome=dados.nome,
        cnpj=dados.cnpj,
        **dados.endereco.model_dump(),
        status="pendente",
        criado_por_usuario_id=usuario_id,
        enviado_em=momento,
    )
    session.add(condominio)
    session.flush()
    return condominio


def criar_estrutura(
    session: Session, *, condominio_id: uuid.UUID, dados: list[BlocoEntrada]
) -> ContagemEstrutura:
    blocos = [Bloco(condominio_id=condominio_id, nome=bloco.nome, ativo=True) for bloco in dados]
    session.add_all(blocos)
    session.flush()
    # Flush por nível garante as FKs sem consultas/flush para cada unidade.
    andares = [
        (
            Andar(
                condominio_id=condominio_id,
                bloco_id=bloco.id,
                nome=andar.nome,
                ordem=andar.ordem,
                ativo=True,
            ),
            andar,
        )
        for bloco, entrada in zip(blocos, dados, strict=True)
        for andar in entrada.andares
    ]
    session.add_all([andar for andar, _ in andares])
    session.flush()
    unidades = [
        Unidade(
            condominio_id=condominio_id, andar_id=andar.id, identificacao=identificacao, ativo=True
        )
        for andar, entrada in andares
        for identificacao in entrada.unidades
    ]
    session.add_all(unidades)
    session.flush()
    return ContagemEstrutura(blocos=len(blocos), andares=len(andares), unidades=len(unidades))


def vincular_criador(session: Session, *, condominio_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    session.add(
        VinculoCondominio(
            condominio_id=condominio_id, usuario_id=usuario_id, perfil="administracao", ativo=True
        )
    )
    session.flush()


def registrar_envio(
    session: Session, *, condominio_id: uuid.UUID, usuario_id: uuid.UUID, momento: datetime
) -> None:
    session.add(
        CondominioAnalise(
            condominio_id=condominio_id, usuario_id=usuario_id, evento="enviado", criado_em=momento
        )
    )
    session.flush()


def listar_da_administracao(session: Session, usuario_id: uuid.UUID) -> list[Condominio]:
    consulta = (
        select(Condominio)
        .join(VinculoCondominio, VinculoCondominio.condominio_id == Condominio.id)
        .where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.perfil == "administracao",
            VinculoCondominio.ativo.is_(True),
        )
        .order_by(Condominio.nome, Condominio.id)
    )
    return list(session.scalars(consulta))


def obter_plataforma(session: Session, id_: uuid.UUID, *, bloquear: bool = False) -> Condominio:
    # Consulta global permitida exclusivamente pelas dependências de plataforma.
    consulta = select(Condominio).where(Condominio.id == id_)
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    item = session.scalar(consulta)
    if item is None:
        raise RecursoNaoEncontrado
    return item


def listar_fila(session: Session, filtros: FiltrosFila) -> tuple[list[Condominio], int]:
    consulta = select(Condominio).where(Condominio.status == filtros.status)
    if filtros.busca:
        consulta = consulta.where(
            or_(
                Condominio.nome.icontains(filtros.busca, autoescape=True),
                Condominio.cnpj.contains(filtros.busca, autoescape=True),
            )
        )
    total = session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    items = list(
        session.scalars(
            consulta.order_by(Condominio.enviado_em.asc().nullsfirst(), Condominio.id)
            .offset((filtros.page - 1) * filtros.page_size)
            .limit(filtros.page_size)
        )
    )
    return items, total


def administracao_do_cadastro(session: Session, condominio: Condominio) -> Usuario | None:
    return session.scalar(select(Usuario).where(Usuario.id == condominio.criado_por_usuario_id))


def documentos_da_analise(session: Session, id_: uuid.UUID) -> list[Arquivo]:
    return list(
        session.scalars(
            select(Arquivo)
            .join(
                CondominioDocumento,
                and_(
                    CondominioDocumento.arquivo_id == Arquivo.id,
                    CondominioDocumento.condominio_id == Arquivo.condominio_id,
                ),
            )
            .where(CondominioDocumento.condominio_id == id_)
            .order_by(Arquivo.criado_em, Arquivo.id)
        )
    )


def estrutura_da_analise(
    session: Session, id_: uuid.UUID
) -> tuple[list[Bloco], list[Andar], list[Unidade]]:
    return (
        list(
            session.scalars(
                select(Bloco).where(Bloco.condominio_id == id_).order_by(Bloco.nome, Bloco.id)
            )
        ),
        list(
            session.scalars(
                select(Andar).where(Andar.condominio_id == id_).order_by(Andar.ordem, Andar.id)
            )
        ),
        list(
            session.scalars(
                select(Unidade)
                .where(Unidade.condominio_id == id_)
                .order_by(Unidade.identificacao, Unidade.id)
            )
        ),
    )


def possiveis_duplicidades(session: Session, condominio: Condominio) -> list[Condominio]:
    criterios = []
    if condominio.cidade and condominio.uf:
        cidade = and_(
            func.lower(func.trim(Condominio.cidade)) == condominio.cidade.strip().lower(),
            Condominio.uf == condominio.uf,
        )
        criterios.append(
            and_(cidade, func.lower(func.trim(Condominio.nome)) == condominio.nome.strip().lower())
        )
        if condominio.logradouro and condominio.numero:
            criterios.append(
                and_(
                    cidade,
                    func.lower(func.trim(Condominio.logradouro))
                    == condominio.logradouro.strip().lower(),
                    func.lower(func.trim(Condominio.numero)) == condominio.numero.strip().lower(),
                )
            )
    if not criterios:
        return []
    return list(
        session.scalars(
            select(Condominio)
            .where(Condominio.id != condominio.id, or_(*criterios))
            .order_by(Condominio.nome, Condominio.id)
        )
    )


def historico(session: Session, id_: uuid.UUID) -> list[CondominioAnalise]:
    return list(
        session.scalars(
            select(CondominioAnalise)
            .where(CondominioAnalise.condominio_id == id_)
            .order_by(CondominioAnalise.criado_em, CondominioAnalise.id)
        )
    )


def registrar_decisao(
    session: Session,
    *,
    condominio_id: uuid.UUID,
    usuario_id: uuid.UUID,
    evento: str,
    motivo: str | None,
    momento: datetime,
) -> None:
    session.add(
        CondominioAnalise(
            condominio_id=condominio_id,
            usuario_id=usuario_id,
            evento=evento,
            motivo=motivo,
            criado_em=momento,
        )
    )
    session.flush()


def enfileirar_aprovacao(session: Session, condominio: Condominio, momento: datetime) -> None:
    administracao = administracao_do_cadastro(session, condominio)
    if administracao is None:
        # Legados sem remetente precisam de correção; nunca adivinhar destinatário.
        raise ApiError(
            409,
            "conflict",
            "Cadastro sem Administração responsável.",
            reason="cadastro_sem_administracao",
        )
    session.add(
        EnvioEmail(
            condominio_id=condominio.id,
            destinatario=administracao.email,
            evento="condominio_aprovado",
            recurso_tipo="condominio",
            recurso_id=condominio.id,
            status="pendente",
            criado_em=momento,
        )
    )
    session.flush()
