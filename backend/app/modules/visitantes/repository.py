"""Consultas dos visitantes. Só aqui se fala com o banco.

Herdam de `RepositorioDoCondominio`: o filtro por condomínio vem junto (R3). As consultas partem
de `self.consulta()`, e os joins e subconsultas também amarram o condomínio.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select

from app.db.repositorio import RepositorioDoCondominio
from app.modules.unidades.models import Unidade
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from app.modules.visitantes.schemas import normalizar_placa


@dataclass(frozen=True)
class FiltrosVisitantes:
    unidade_id: uuid.UUID
    busca: str | None = None
    situacao: str | None = None
    hoje: date | None = None  # obrigatório quando há `situacao`


@dataclass(frozen=True)
class VisitanteDetalhado:
    visitante: Visitante
    unidade_identificacao: str
    ja_utilizado: bool


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class RepositorioVisitantes(RepositorioDoCondominio[Visitante]):
    modelo = Visitante

    def _tem_visita(self) -> ColumnElement[bool]:
        return exists().where(
            RegistroVisita.visitante_id == Visitante.id,
            RegistroVisita.condominio_id == Visitante.condominio_id,
        )

    def _detalhado(self) -> Select[Any]:
        """Visitante + unidade + se já houve visita. Os joins amarram o condomínio."""
        return (
            self.consulta()
            .add_columns(Unidade.identificacao, self._tem_visita().label("ja_utilizado"))
            .join(
                Unidade,
                and_(
                    Unidade.id == Visitante.unidade_id,
                    Unidade.condominio_id == Visitante.condominio_id,
                ),
            )
        )

    def _filtrados(self, filtros: FiltrosVisitantes) -> Select[Any]:
        consulta = self._detalhado().where(Visitante.unidade_id == filtros.unidade_id)
        if filtros.busca:
            padrao = f"%{_escapar_like(filtros.busca)}%"
            consulta = consulta.where(
                or_(
                    Visitante.nome.ilike(padrao, escape="\\"),
                    Visitante.cpf.like(padrao, escape="\\"),
                )
            )
        if filtros.situacao is not None:
            if filtros.hoje is None:
                raise ValueError("`hoje` é obrigatório para filtrar por situação.")
            hoje = filtros.hoje
            ativo = Visitante.cancelado_em.is_(None)
            consulta = consulta.where(
                {
                    "vigentes": and_(
                        ativo, Visitante.entrada_prevista <= hoje, Visitante.saida_prevista >= hoje
                    ),
                    "futuros": and_(ativo, Visitante.entrada_prevista > hoje),
                    "encerrados": and_(ativo, Visitante.saida_prevista < hoje),
                    "cancelados": Visitante.cancelado_em.is_not(None),
                }[filtros.situacao]
            )
        return consulta

    @staticmethod
    def _montar(linha: Any) -> VisitanteDetalhado:
        visitante, identificacao, ja_utilizado = linha
        return VisitanteDetalhado(visitante, identificacao, bool(ja_utilizado))

    def obter_detalhado(self, visitante_id: uuid.UUID) -> VisitanteDetalhado | None:
        linha = self.session.execute(self._detalhado().where(Visitante.id == visitante_id)).first()
        return None if linha is None else self._montar(linha)

    def bloquear(self, visitante_id: uuid.UUID) -> Visitante | None:
        """Trava a linha até o commit.

        `FOR UPDATE` (e não `NO KEY UPDATE`) conflita com o `FOR KEY SHARE` que a FK de
        `registros_visita` toma ao inserir uma entrada: enquanto editamos ou cancelamos, a portaria
        não consegue registrar a visita, e o contrário também vale.
        """
        return self.session.scalar(
            self.consulta().where(Visitante.id == visitante_id).with_for_update()
        )

    def tem_visita(self, visitante_id: uuid.UUID) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        RegistroVisita.condominio_id == self.contexto.condominio_id,
                        RegistroVisita.visitante_id == visitante_id,
                    )
                )
            )
        )

    def tem_visita_em_andamento(self, visitante_id: uuid.UUID) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        RegistroVisita.condominio_id == self.contexto.condominio_id,
                        RegistroVisita.visitante_id == visitante_id,
                        RegistroVisita.saida_em.is_(None),
                    )
                )
            )
        )

    def pagina(
        self, filtros: FiltrosVisitantes, *, limite: int, deslocamento: int
    ) -> tuple[list[VisitanteDetalhado], int]:
        consulta = (
            self._filtrados(filtros)
            .order_by(Visitante.entrada_prevista.desc(), Visitante.criado_em.desc(), Visitante.id)
            .limit(limite)
            .offset(deslocamento)
        )
        itens = [self._montar(linha) for linha in self.session.execute(consulta)]
        total = (
            self.session.scalar(
                select(func.count()).select_from(self._filtrados(filtros).subquery())
            )
            or 0
        )
        return itens, total


# --- veículos (US-502) ----------------------------------------------------------------------


@dataclass(frozen=True)
class FiltrosVeiculos:
    unidade_id: uuid.UUID | None = None
    busca: str | None = None


@dataclass(frozen=True)
class VeiculoDetalhado:
    veiculo: Veiculo
    unidade_identificacao: str


class RepositorioVeiculos(RepositorioDoCondominio[Veiculo]):
    modelo = Veiculo

    def _detalhado(self) -> Select[Any]:
        """Veículo + unidade. O join amarra o condomínio."""
        return (
            self.consulta()
            .add_columns(Unidade.identificacao)
            .join(
                Unidade,
                and_(
                    Unidade.id == Veiculo.unidade_id,
                    Unidade.condominio_id == Veiculo.condominio_id,
                ),
            )
        )

    def _filtrados(self, filtros: FiltrosVeiculos) -> Select[Any]:
        # A lista só traz veículos ativos; o removido continua acessível por id.
        consulta = self._detalhado().where(Veiculo.ativo.is_(True))
        if filtros.unidade_id is not None:
            consulta = consulta.where(Veiculo.unidade_id == filtros.unidade_id)
        if filtros.busca:
            padrao = f"%{_escapar_like(filtros.busca)}%"
            placa = f"%{_escapar_like(normalizar_placa(filtros.busca))}%"
            consulta = consulta.where(
                or_(
                    Veiculo.placa.like(placa, escape="\\"),
                    Veiculo.marca.ilike(padrao, escape="\\"),
                    Veiculo.modelo.ilike(padrao, escape="\\"),
                )
            )
        return consulta

    @staticmethod
    def _montar(linha: Any) -> VeiculoDetalhado:
        veiculo, identificacao = linha
        return VeiculoDetalhado(veiculo, identificacao)

    def obter_detalhado(self, veiculo_id: uuid.UUID) -> VeiculoDetalhado | None:
        linha = self.session.execute(self._detalhado().where(Veiculo.id == veiculo_id)).first()
        return None if linha is None else self._montar(linha)

    def bloquear(self, veiculo_id: uuid.UUID) -> Veiculo | None:
        """Trava a linha até o commit: duas remoções ou edições simultâneas não passam juntas."""
        return self.session.scalar(
            self.consulta().where(Veiculo.id == veiculo_id).with_for_update()
        )

    def pagina(
        self, filtros: FiltrosVeiculos, *, limite: int, deslocamento: int
    ) -> tuple[list[VeiculoDetalhado], int]:
        consulta = (
            self._filtrados(filtros)
            .order_by(Veiculo.placa, Veiculo.id)
            .limit(limite)
            .offset(deslocamento)
        )
        itens = [self._montar(linha) for linha in self.session.execute(consulta)]
        total = (
            self.session.scalar(
                select(func.count()).select_from(self._filtrados(filtros).subquery())
            )
            or 0
        )
        return itens, total
