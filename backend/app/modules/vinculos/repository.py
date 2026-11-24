import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import ChaveAcesso, MoradorUnidade, PermissaoAba, Unidade
from app.modules.usuarios.models import TentativaChaveAcesso, Usuario


def bloquear_conta(session: Session, id_: uuid.UUID, *, compartilhada: bool = False) -> Usuario:
    # O vínculo mantém NO KEY UPDATE: serializa tentativas/criação do vínculo global.
    # O desvínculo usa SHARE, compatível com a leitura de destinatários da portaria;
    # conflita com o vínculo e serializa a decisão global em obter_vinculo(), após a unidade.
    usuario = session.scalar(
        select(Usuario)
        .where(Usuario.id == id_)
        .with_for_update(read=compartilhada, key_share=not compartilhada)
        .execution_options(populate_existing=True)
    )
    if usuario is None:
        raise RecursoNaoEncontrado
    return usuario


def tentativas_desde_sucesso(session: Session, usuario_id: uuid.UUID) -> list[TentativaChaveAcesso]:
    ultimo_sucesso = session.scalar(
        select(func.max(TentativaChaveAcesso.criado_em)).where(
            TentativaChaveAcesso.usuario_id == usuario_id, TentativaChaveAcesso.sucesso.is_(True)
        )
    )
    consulta = select(TentativaChaveAcesso).where(TentativaChaveAcesso.usuario_id == usuario_id)
    if ultimo_sucesso is not None:
        consulta = consulta.where(TentativaChaveAcesso.criado_em >= ultimo_sucesso)
    return list(
        session.scalars(consulta.order_by(TentativaChaveAcesso.criado_em, TentativaChaveAcesso.id))
    )


def registrar_tentativa(
    session: Session, usuario_id: uuid.UUID, *, sucesso: bool, momento: datetime
) -> None:
    session.add(TentativaChaveAcesso(usuario_id=usuario_id, sucesso=sucesso, criado_em=momento))
    session.flush()


def localizar_chave(session: Session, codigo: str) -> ChaveAcesso | None:
    # Exceção de bootstrap: condomínio/unidade são descobertos pela chave, nunca pelo cliente.
    return session.scalar(
        select(ChaveAcesso).where(ChaveAcesso.codigo == codigo, ChaveAcesso.revogada_em.is_(None))
    )


def bloquear_destino(session: Session, chave: ChaveAcesso) -> tuple[Condominio, Unidade] | None:
    condominio = session.scalar(
        select(Condominio)
        .where(Condominio.id == chave.condominio_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if condominio is None or condominio.status != "ativo":
        return None
    unidade = session.scalar(
        select(Unidade)
        .where(Unidade.id == chave.unidade_id, Unidade.condominio_id == condominio.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if unidade is None or not unidade.ativo:
        return None
    # Regeneração/revogação usam a mesma tranca da unidade (TASK-29). Revalidar DEPOIS dela.
    vigente = session.scalar(
        select(ChaveAcesso.id).where(
            ChaveAcesso.id == chave.id,
            ChaveAcesso.condominio_id == condominio.id,
            ChaveAcesso.unidade_id == unidade.id,
            ChaveAcesso.revogada_em.is_(None),
        )
    )
    return (condominio, unidade) if vigente else None


def obter_vinculo(
    session: Session, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> VinculoCondominio | None:
    return session.scalar(
        select(VinculoCondominio)
        .where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.condominio_id == condominio_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def criar_vinculo(
    session: Session, usuario_id: uuid.UUID, condominio_id: uuid.UUID
) -> VinculoCondominio:
    vinculo = VinculoCondominio(
        usuario_id=usuario_id, condominio_id=condominio_id, perfil="morador", ativo=True
    )
    session.add(vinculo)
    session.flush()
    return vinculo


def bloquear_condominio(session: Session, contexto: ContextoCondominio) -> Condominio:
    # Mesma ordem do vínculo por chave: conta -> condomínio (SHARE) -> unidade.
    item = session.scalar(
        select(Condominio)
        .where(Condominio.id == contexto.condominio_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise RecursoNaoEncontrado
    return item


def executor_habilitado(session: Session, contexto: ContextoCondominio) -> bool:
    return (
        session.scalar(
            select(VinculoCondominio.id)
            .join(Usuario, Usuario.id == VinculoCondominio.usuario_id)
            .where(
                VinculoCondominio.id == contexto.vinculo_id,
                VinculoCondominio.usuario_id == contexto.usuario_id,
                VinculoCondominio.condominio_id == contexto.condominio_id,
                VinculoCondominio.perfil == contexto.perfil,
                VinculoCondominio.ativo.is_(True),
                Usuario.ativo.is_(True),
                Usuario.administrador_plataforma.is_(False),
            )
        )
        is not None
    )


class RepositorioMinhasUnidades(RepositorioDoCondominio[Unidade]):
    modelo = Unidade

    def vinculadas(self):
        return (
            self.consulta()
            .join(
                MoradorUnidade,
                and_(
                    MoradorUnidade.unidade_id == Unidade.id,
                    MoradorUnidade.condominio_id == Unidade.condominio_id,
                ),
            )
            .where(
                MoradorUnidade.usuario_id == self.contexto.usuario_id,
                MoradorUnidade.status == "ativo",
                Unidade.ativo.is_(True),
            )
        )

    def obter_vinculada(self, id_: uuid.UUID) -> Unidade:
        item = self.session.scalar(self.vinculadas().where(Unidade.id == id_))
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def pagina(self, page: int, page_size: int) -> tuple[list[Unidade], int]:
        consulta = (
            self.vinculadas()
            .join(
                PermissaoAba,
                and_(
                    PermissaoAba.morador_unidade_id == MoradorUnidade.id,
                    PermissaoAba.condominio_id == MoradorUnidade.condominio_id,
                ),
            )
            .where(PermissaoAba.aba == "unidades", PermissaoAba.com_acesso.is_(True))
        )
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        items = list(
            self.session.scalars(
                consulta.order_by(Unidade.identificacao, Unidade.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        )
        return items, total

    def condominio(self) -> Condominio:
        item = self.session.scalar(
            select(Condominio).where(Condominio.id == self.contexto.condominio_id)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item


class RepositorioMoradores(RepositorioDoCondominio[MoradorUnidade]):
    modelo = MoradorUnidade

    def usuario_do_alvo(self, unidade_id: uuid.UUID, id_: uuid.UUID) -> uuid.UUID:
        # Descoberta restrita ao escopo autorizado antes de travar a conta do alvo.
        # Não adota associações legadas ligadas a perfil global incompatível.
        usuario_id = self.session.scalar(
            select(MoradorUnidade.usuario_id)
            .join(
                VinculoCondominio,
                (VinculoCondominio.usuario_id == MoradorUnidade.usuario_id)
                & (VinculoCondominio.condominio_id == MoradorUnidade.condominio_id),
            )
            .where(
                self._do_condominio(),
                MoradorUnidade.id == id_,
                MoradorUnidade.unidade_id == unidade_id,
                VinculoCondominio.perfil == "morador",
            )
        )
        if usuario_id is None:
            raise RecursoNaoEncontrado
        return usuario_id

    def associacao(self, unidade_id: uuid.UUID, id_: uuid.UUID) -> MoradorUnidade:
        item = self.session.scalar(
            self.consulta()
            .where(MoradorUnidade.id == id_, MoradorUnidade.unidade_id == unidade_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def tem_outra_unidade_ativa(self, usuario_id: uuid.UUID, *, excluindo: uuid.UUID) -> bool:
        consulta = (
            self.consulta()
            .join(
                Unidade,
                (Unidade.id == MoradorUnidade.unidade_id)
                & (Unidade.condominio_id == MoradorUnidade.condominio_id),
            )
            .where(
                MoradorUnidade.usuario_id == usuario_id,
                MoradorUnidade.id != excluindo,
                MoradorUnidade.status == "ativo",
                Unidade.ativo.is_(True),
            )
        )
        return bool(self.session.scalar(select(consulta.exists())))

    def ja_vinculado(self, unidade_id: uuid.UUID) -> bool:
        return (
            self.session.scalar(
                self.consulta().where(
                    MoradorUnidade.unidade_id == unidade_id,
                    MoradorUnidade.usuario_id == self.contexto.usuario_id,
                    MoradorUnidade.status == "ativo",
                )
            )
            is not None
        )
