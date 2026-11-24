import uuid

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import aliased

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.unidades.models import Andar, Bloco, Unidade
from app.modules.visitantes.models import Veiculo

Linha = tuple[Veiculo, str, str | None, str | None, bool]


class RepositorioVeiculos(RepositorioDoCondominio[Veiculo]):
    modelo = Veiculo

    def quantidade_ativa(self, unidade_id: uuid.UUID) -> int:
        consulta = self.consulta().where(Veiculo.unidade_id == unidade_id, Veiculo.ativo.is_(True))
        return self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0

    def placa_ativa(self, unidade_id: uuid.UUID, placa: str) -> bool:
        consulta = self.consulta().where(
            Veiculo.unidade_id == unidade_id, Veiculo.placa == placa, Veiculo.ativo.is_(True)
        )
        return bool(self.session.scalar(select(consulta.exists())))

    def _detalhada(self) -> Select[Linha]:
        outro = aliased(Veiculo)
        outra_unidade = aliased(Unidade)
        duplicada = (
            select(outro.id)
            .join(
                outra_unidade,
                and_(
                    outra_unidade.id == outro.unidade_id,
                    outra_unidade.condominio_id == outro.condominio_id,
                ),
            )
            .where(
                outro.condominio_id == Veiculo.condominio_id,
                outro.unidade_id != Veiculo.unidade_id,
                outro.placa == Veiculo.placa,
                outro.ativo.is_(True),
                outra_unidade.ativo.is_(True),
            )
            .exists()
        )
        return (
            self.consulta()
            .add_columns(Unidade.identificacao, Bloco.nome, Andar.nome, duplicada)
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
        )

    def detalhe(self, id_: uuid.UUID, *, somente_ativos: bool = True) -> Linha:
        consulta = self._detalhada().where(Veiculo.id == id_)
        if somente_ativos:
            consulta = consulta.where(Veiculo.ativo.is_(True), Unidade.ativo.is_(True))
        item = (
            self.session.execute(consulta.execution_options(populate_existing=True))
            .tuples()
            .one_or_none()
        )
        if item is None:
            raise RecursoNaoEncontrado
        return item

    def pagina(
        self, unidade_id: uuid.UUID | None, busca: str | None, page: int, size: int
    ) -> tuple[list[Linha], int]:
        consulta = self._detalhada().where(Veiculo.ativo.is_(True), Unidade.ativo.is_(True))
        if unidade_id is not None:
            consulta = consulta.where(Veiculo.unidade_id == unidade_id)
        termo = (busca or "").strip()
        if termo:
            placa = "".join(termo.upper().replace("-", "").split())
            filtros = [
                Veiculo.marca.icontains(termo, autoescape=True),
                Veiculo.modelo.icontains(termo, autoescape=True),
            ]
            if placa:
                filtros.append(Veiculo.placa.icontains(placa, autoescape=True))
            consulta = consulta.where(or_(*filtros))
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        items = self.session.execute(
            consulta.order_by(Veiculo.placa, Veiculo.id).offset((page - 1) * size).limit(size)
        ).tuples()
        return list(items), total
