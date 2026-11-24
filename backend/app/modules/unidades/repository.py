import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.unidades.models import (
    Andar,
    Bloco,
    ChaveAcesso,
    MoradorUnidade,
    ProprietarioUnidade,
    Unidade,
)
from app.modules.unidades.schemas import FiltrosUnidades, MoradorSaida
from app.modules.usuarios.models import Usuario


class RepositorioUnidades(RepositorioDoCondominio[Unidade]):
    modelo = Unidade

    def moradores(self, id_: uuid.UUID) -> list[MoradorSaida]:
        linhas = self.session.execute(
            select(MoradorUnidade, Usuario.nome)
            .join(Usuario, Usuario.id == MoradorUnidade.usuario_id)
            .where(
                MoradorUnidade.unidade_id == id_,
                MoradorUnidade.condominio_id == self.contexto.condominio_id,
            )
            .order_by(MoradorUnidade.vinculado_em, MoradorUnidade.id)
        )
        return [
            MoradorSaida(
                id=m.id,
                nome=nome,
                parentesco=m.parentesco,
                status=m.status,
                vinculado_em=m.vinculado_em,
            )
            for m, nome in linhas
        ]

    def bloquear(self, id_: uuid.UUID) -> Unidade:
        item = self.session.scalar(
            self.consulta()
            .where(Unidade.id == id_)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def localizacao(self, unidade: Unidade) -> tuple[str | None, str | None]:
        linha = self.session.execute(
            select(Bloco.nome, Andar.nome)
            .join(
                Andar, (Andar.bloco_id == Bloco.id) & (Andar.condominio_id == Bloco.condominio_id)
            )
            .where(Andar.id == unidade.andar_id, Andar.condominio_id == self.contexto.condominio_id)
        ).first()
        return (linha[0], linha[1]) if linha else (None, None)

    def pagina(self, filtros: FiltrosUnidades) -> tuple[list[Unidade], int]:
        consulta = self.consulta().where(Unidade.ativo == filtros.ativo)
        if filtros.andar_id:
            consulta = consulta.where(Unidade.andar_id == filtros.andar_id)
        if filtros.bloco_id:
            consulta = consulta.join(
                Andar,
                (Andar.id == Unidade.andar_id) & (Andar.condominio_id == Unidade.condominio_id),
            ).where(Andar.bloco_id == filtros.bloco_id)
        if filtros.busca:
            consulta = consulta.where(
                Unidade.identificacao.icontains(filtros.busca, autoescape=True)
            )
        if filtros.sem_proprietario is not None:
            existe = (
                select(ProprietarioUnidade.id)
                .where(
                    ProprietarioUnidade.unidade_id == Unidade.id,
                    ProprietarioUnidade.condominio_id == self.contexto.condominio_id,
                )
                .exists()
            )
            consulta = consulta.where(~existe if filtros.sem_proprietario else existe)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        items = list(
            self.session.scalars(
                consulta.order_by(Unidade.identificacao, Unidade.id)
                .offset((filtros.page - 1) * filtros.page_size)
                .limit(filtros.page_size)
            )
        )
        return items, total


class RepositorioProprietarios(RepositorioDoCondominio[ProprietarioUnidade]):
    modelo = ProprietarioUnidade

    def da_unidade(self, id_: uuid.UUID) -> ProprietarioUnidade | None:
        return self.session.scalar(self.consulta().where(ProprietarioUnidade.unidade_id == id_))


class RepositorioChaves(RepositorioDoCondominio[ChaveAcesso]):
    modelo = ChaveAcesso

    def vigente(self, id_: uuid.UUID) -> ChaveAcesso | None:
        return self.session.scalar(
            self.consulta()
            .where(ChaveAcesso.unidade_id == id_, ChaveAcesso.revogada_em.is_(None))
            .execution_options(populate_existing=True)
        )


def inserir_chave(
    session: Session, unidade: Unidade, codigo: str, momento: datetime
) -> ChaveAcesso:
    # O chamador já bloqueou a unidade (ou o condomínio durante a aprovação).
    chave = ChaveAcesso(
        condominio_id=unidade.condominio_id,
        unidade_id=unidade.id,
        codigo=codigo,
        criada_em=momento,
    )
    session.add(chave)
    session.flush()
    return chave
