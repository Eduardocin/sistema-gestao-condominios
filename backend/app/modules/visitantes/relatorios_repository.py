"""Consultas históricas paginadas; os filtros não alteram as consultas operacionais."""

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select

from app.db.repositorio import RepositorioDoCondominio
from app.modules.unidades.models import Andar, Bloco, Unidade
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from app.modules.visitantes.repository import RepositorioVisitas

LinhaVisitaRelatorio = tuple[
    RegistroVisita, str, uuid.UUID, str, str | None, str | None, str, str | None, bool
]
LinhaVeiculoRelatorio = tuple[Veiculo, str, str | None, str | None, bool]


class RepositorioRelatorioVisitas(RepositorioVisitas):
    def pagina_relatorio(
        self,
        unidade: uuid.UUID | None,
        inicio: datetime | None,
        fim: datetime | None,
        page: int,
        size: int,
    ) -> tuple[list[LinhaVisitaRelatorio], int]:
        # A consulta existente já inclui cancelados, unidades inativas e desligados,
        # com todos os joins delimitados pelo condomínio do registro efetivo.
        consulta = self.detalhada().add_columns(Visitante.avulso)
        if unidade is not None:
            consulta = consulta.where(Visitante.unidade_id == unidade)
        if inicio is not None:
            consulta = consulta.where(RegistroVisita.entrada_em >= inicio)
        if fim is not None:
            consulta = consulta.where(RegistroVisita.entrada_em < fim)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            consulta.order_by(RegistroVisita.entrada_em.desc(), RegistroVisita.id)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
        return list(linhas), total


class RepositorioRelatorioVeiculos(RepositorioDoCondominio[Veiculo]):
    modelo = Veiculo

    def pagina_relatorio(
        self,
        unidade: uuid.UUID | None,
        inicio: datetime | None,
        fim: datetime | None,
        page: int,
        size: int,
    ) -> tuple[list[LinhaVeiculoRelatorio], int]:
        # Mesma regra de ativos da consulta operacional, aplicada à placa inteira:
        # uma linha histórica não deve contar como um dos cadastros ativos da placa.
        # Esta subconsulta independe dos filtros de unidade/período do relatório.
        duplicadas = (
            self.consulta()
            .with_only_columns(Veiculo.placa)
            .join(
                Unidade,
                and_(
                    Unidade.id == Veiculo.unidade_id, Unidade.condominio_id == Veiculo.condominio_id
                ),
            )
            .where(Veiculo.ativo.is_(True), Unidade.ativo.is_(True))
            .group_by(Veiculo.placa)
            .having(func.count(func.distinct(Veiculo.unidade_id)) > 1)
            .subquery()
        )
        consulta = (
            self.consulta()
            .add_columns(
                Unidade.identificacao, Bloco.nome, Andar.nome, duplicadas.c.placa.is_not(None)
            )
            .join(
                Unidade,
                and_(
                    Unidade.id == Veiculo.unidade_id, Unidade.condominio_id == Veiculo.condominio_id
                ),
            )
            .outerjoin(
                Andar,
                and_(Andar.id == Unidade.andar_id, Andar.condominio_id == Unidade.condominio_id),
            )
            .outerjoin(
                Bloco, and_(Bloco.id == Andar.bloco_id, Bloco.condominio_id == Andar.condominio_id)
            )
            .outerjoin(duplicadas, duplicadas.c.placa == Veiculo.placa)
        )
        if unidade is not None:
            consulta = consulta.where(Veiculo.unidade_id == unidade)
        if inicio is not None:
            consulta = consulta.where(Veiculo.criado_em >= inicio)
        if fim is not None:
            consulta = consulta.where(Veiculo.criado_em < fim)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            consulta.order_by(Veiculo.criado_em.desc(), Veiculo.id)
            .offset((page - 1) * size)
            .limit(size)
        ).tuples()
        return list(linhas), total
