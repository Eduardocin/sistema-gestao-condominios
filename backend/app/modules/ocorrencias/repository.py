"""Consultas do módulo de ocorrências. Só aqui se fala com o banco.

Todos herdam de `RepositorioDoCondominio`: o filtro por condomínio vem junto (R3). As consultas
partem de `self.consulta()`, que já vem filtrada; os joins também amarram o condomínio.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, select

from app.core.tempo import FUSO_CONDOMINIO
from app.db.repositorio import RepositorioDoCondominio
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo, OcorrenciaInteracao
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario


@dataclass(frozen=True)
class FiltrosOcorrencias:
    unidade_id: uuid.UUID | None = None
    status: str | None = None
    de: date | None = None
    ate: date | None = None


@dataclass(frozen=True)
class OcorrenciaDetalhada:
    ocorrencia: Ocorrencia
    unidade_identificacao: str
    aberta_por_nome: str


@dataclass(frozen=True)
class InteracaoDetalhada:
    interacao: OcorrenciaInteracao
    autor_nome: str
    autor_tipo: str


@dataclass(frozen=True)
class UltimaInteracao:
    em: datetime
    responsavel_id: uuid.UUID | None


class RepositorioOcorrencias(RepositorioDoCondominio[Ocorrencia]):
    modelo = Ocorrencia

    def _detalhada(self) -> Select[Any]:
        """Ocorrência + unidade + quem abriu. Os joins amarram o condomínio."""
        return (
            self.consulta()
            .add_columns(Unidade.identificacao, Usuario.nome)
            .join(
                Unidade,
                and_(
                    Unidade.id == Ocorrencia.unidade_id,
                    Unidade.condominio_id == Ocorrencia.condominio_id,
                ),
            )
            .join(Usuario, Usuario.id == Ocorrencia.aberta_por_usuario_id)
        )

    def _filtradas(self, filtros: FiltrosOcorrencias) -> Select[Any]:
        consulta = self._detalhada()
        if filtros.unidade_id is not None:
            consulta = consulta.where(Ocorrencia.unidade_id == filtros.unidade_id)
        if filtros.status is not None:
            consulta = consulta.where(Ocorrencia.status == filtros.status)
        # O período é de datas de negócio no fuso do condomínio, não em UTC.
        if filtros.de is not None:
            consulta = consulta.where(
                Ocorrencia.criado_em >= datetime.combine(filtros.de, time.min, FUSO_CONDOMINIO)
            )
        if filtros.ate is not None:
            if filtros.ate < date.max:
                limite_fim = datetime.combine(
                    filtros.ate + timedelta(days=1), time.min, FUSO_CONDOMINIO
                )
                consulta = consulta.where(Ocorrencia.criado_em < limite_fim)
            else:
                consulta = consulta.where(
                    Ocorrencia.criado_em <= datetime.combine(date.max, time.max, FUSO_CONDOMINIO)
                )
        return consulta

    @staticmethod
    def _montar(linha: Any) -> OcorrenciaDetalhada:
        ocorrencia, identificacao, autor_nome = linha
        return OcorrenciaDetalhada(ocorrencia, identificacao, autor_nome)

    def obter_detalhada(self, ocorrencia_id: uuid.UUID) -> OcorrenciaDetalhada | None:
        linha = self.session.execute(
            self._detalhada().where(Ocorrencia.id == ocorrencia_id)
        ).first()
        return None if linha is None else self._montar(linha)

    def bloquear(self, ocorrencia_id: uuid.UUID) -> Ocorrencia | None:
        """Trava a linha até o commit: duas resoluções simultâneas não passam juntas."""
        return self.session.scalar(
            self.consulta()
            .where(Ocorrencia.id == ocorrencia_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def pagina(
        self, filtros: FiltrosOcorrencias, *, limite: int, deslocamento: int
    ) -> tuple[list[OcorrenciaDetalhada], int]:
        consulta = (
            self._filtradas(filtros)
            .order_by(Ocorrencia.criado_em.desc(), Ocorrencia.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        itens = [self._montar(linha) for linha in self.session.execute(consulta)]
        total = (
            self.session.scalar(
                select(func.count()).select_from(self._filtradas(filtros).subquery())
            )
            or 0
        )
        return itens, total

    def ultimas_interacoes(
        self, ocorrencia_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, UltimaInteracao]:
        """A interação mais recente de cada ocorrência da página, em uma única consulta."""
        if not ocorrencia_ids:
            return {}
        ranking = (
            select(
                OcorrenciaInteracao.ocorrencia_id,
                OcorrenciaInteracao.criado_em,
                OcorrenciaInteracao.responsavel_id,
                func.row_number()
                .over(
                    partition_by=OcorrenciaInteracao.ocorrencia_id,
                    order_by=(
                        OcorrenciaInteracao.criado_em.desc(),
                        OcorrenciaInteracao.id.desc(),
                    ),
                )
                .label("posicao"),
            )
            .where(
                OcorrenciaInteracao.condominio_id == self.contexto.condominio_id,
                OcorrenciaInteracao.ocorrencia_id.in_(ocorrencia_ids),
            )
            .subquery()
        )
        consulta = select(
            ranking.c.ocorrencia_id, ranking.c.criado_em, ranking.c.responsavel_id
        ).where(ranking.c.posicao == 1)
        return {
            linha.ocorrencia_id: UltimaInteracao(linha.criado_em, linha.responsavel_id)
            for linha in self.session.execute(consulta)
        }

    def interacoes(self, ocorrencia_id: uuid.UUID) -> list[InteracaoDetalhada]:
        consulta = (
            select(OcorrenciaInteracao, Usuario.nome, ResponsavelAdministracao.nome)
            .join(Usuario, Usuario.id == OcorrenciaInteracao.usuario_id)
            .outerjoin(
                ResponsavelAdministracao,
                and_(
                    ResponsavelAdministracao.id == OcorrenciaInteracao.responsavel_id,
                    ResponsavelAdministracao.condominio_id == OcorrenciaInteracao.condominio_id,
                ),
            )
            .where(
                OcorrenciaInteracao.condominio_id == self.contexto.condominio_id,
                OcorrenciaInteracao.ocorrencia_id == ocorrencia_id,
            )
            .order_by(OcorrenciaInteracao.criado_em, OcorrenciaInteracao.id)
        )
        return [
            InteracaoDetalhada(
                interacao=interacao,
                autor_nome=responsavel_nome or usuario_nome,
                autor_tipo="administracao" if interacao.responsavel_id else "morador",
            )
            for interacao, usuario_nome, responsavel_nome in self.session.execute(consulta)
        ]

    def anexos(self, ocorrencia_id: uuid.UUID) -> list[OcorrenciaAnexo]:
        consulta = (
            select(OcorrenciaAnexo)
            .where(
                OcorrenciaAnexo.condominio_id == self.contexto.condominio_id,
                OcorrenciaAnexo.ocorrencia_id == ocorrencia_id,
            )
            .order_by(OcorrenciaAnexo.arquivo_id)
        )
        return list(self.session.scalars(consulta))


class RepositorioInteracoes(RepositorioDoCondominio[OcorrenciaInteracao]):
    modelo = OcorrenciaInteracao


class RepositorioAnexos(RepositorioDoCondominio[OcorrenciaAnexo]):
    modelo = OcorrenciaAnexo


class RepositorioArquivos(RepositorioDoCondominio[Arquivo]):
    modelo = Arquivo

    def buscar(self, arquivo_id: uuid.UUID) -> Arquivo | None:
        """O arquivo do próprio condomínio, ou None (arquivo da conta/outro prédio não conta)."""
        return self.session.scalar(self.consulta().where(Arquivo.id == arquivo_id))
