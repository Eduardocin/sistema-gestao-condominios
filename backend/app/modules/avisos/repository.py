import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, or_, select

from app.core.errors import RecursoNaoEncontrado
from app.core.permissoes import Perfil
from app.db.repositorio import RepositorioDoCondominio
from app.modules.avisos.models import Aviso
from app.modules.avisos.schemas import SituacaoFiltro
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.unidades.models import MoradorUnidade, Unidade


@dataclass(frozen=True)
class AvisoDetalhado:
    aviso: Aviso
    unidade_identificacao: str | None
    responsavel_nome: str | None


class RepositorioAvisos(RepositorioDoCondominio[Aviso]):
    modelo = Aviso

    def visiveis(self, momento: datetime, situacao: SituacaoFiltro) -> Select[tuple[Aviso]]:
        consulta = self.consulta()
        if self.contexto.perfil != Perfil.ADMINISTRACAO:
            situacao = "vigentes"
            publico: ColumnElement[bool] = Aviso.unidade_id.is_(None)
            if self.contexto.perfil == Perfil.MORADOR:
                minha_unidade = select(MoradorUnidade.id).where(
                    MoradorUnidade.condominio_id == self.contexto.condominio_id,
                    MoradorUnidade.usuario_id == self.contexto.usuario_id,
                    MoradorUnidade.unidade_id == Aviso.unidade_id,
                    MoradorUnidade.status == "ativo",
                )
                publico = or_(publico, minha_unidade.exists())
            consulta = consulta.where(publico)
        if situacao == "vigentes":
            consulta = consulta.where(
                Aviso.encerrado_em.is_(None), Aviso.inicio_em <= momento, Aviso.fim_em > momento
            )
        elif situacao == "agendados":
            consulta = consulta.where(Aviso.encerrado_em.is_(None), Aviso.inicio_em > momento)
        elif situacao == "encerrados":
            consulta = consulta.where(or_(Aviso.encerrado_em.is_not(None), Aviso.fim_em <= momento))
        return consulta

    def _detalhada(self, consulta: Select[tuple[Aviso]]) -> Select[Any]:
        return (
            consulta.add_columns(Unidade.identificacao, ResponsavelAdministracao.nome)
            .outerjoin(
                Unidade,
                and_(Unidade.id == Aviso.unidade_id, Unidade.condominio_id == Aviso.condominio_id),
            )
            .outerjoin(
                ResponsavelAdministracao,
                and_(
                    ResponsavelAdministracao.id == Aviso.responsavel_id,
                    ResponsavelAdministracao.condominio_id == Aviso.condominio_id,
                ),
            )
        )

    def pagina(
        self, *, momento: datetime, situacao: SituacaoFiltro, page: int, page_size: int
    ) -> tuple[list[AvisoDetalhado], int]:
        consulta = self.visiveis(momento, situacao)
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        linhas = self.session.execute(
            self._detalhada(consulta)
            .order_by(Aviso.importante.desc(), Aviso.inicio_em.desc(), Aviso.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        return [AvisoDetalhado(*linha) for linha in linhas], total

    def obter_detalhado(self, aviso_id: uuid.UUID, momento: datetime) -> AvisoDetalhado:
        linha = self.session.execute(
            self._detalhada(self.visiveis(momento, "todos").where(Aviso.id == aviso_id))
        ).one_or_none()
        if linha is None:
            raise RecursoNaoEncontrado
        return AvisoDetalhado(*linha)

    def bloquear(self, aviso_id: uuid.UUID) -> Aviso:
        aviso = self.session.scalar(
            self.consulta()
            .where(Aviso.id == aviso_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if aviso is None:
            raise RecursoNaoEncontrado
        return aviso
