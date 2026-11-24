"""Consultas do módulo de reservas. Só aqui se fala com o banco.

Todos herdam de `RepositorioDoCondominio`: o filtro por condomínio vem junto (R3). As consultas
partem de `self.consulta()`, que já vem filtrada; os joins também amarram o condomínio.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select

from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.notificacoes.models import EnvioEmail
from app.modules.reservas.models import AreaComum, BloqueioArea, Reserva
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario


class RepositorioAreasComuns(RepositorioDoCondominio[AreaComum]):
    modelo = AreaComum

    def _filtradas(self, ativa: bool | None) -> Select[tuple[AreaComum]]:
        consulta = self.consulta()
        if ativa is not None:
            consulta = consulta.where(AreaComum.ativa.is_(ativa))
        return consulta

    def obter_travada(self, area_id: uuid.UUID, *, compartilhada: bool) -> AreaComum:
        """A área travada até o commit, ou 404 (inexistente ou de outro condomínio).

        Quem reserva trava em modo compartilhado e quem bloqueia datas, em modo exclusivo: os dois
        não andam juntos. Assim a reserva criada durante um bloqueio entra na prévia dele, ou então
        vê o bloqueio já gravado e recebe 409 `area_bloqueada`.
        """
        area = self.session.scalar(
            self.consulta().where(AreaComum.id == area_id).with_for_update(read=compartilhada)
        )
        if area is None:
            raise RecursoNaoEncontrado
        return area

    def contar(self, *, ativa: bool | None) -> int:
        consulta = select(func.count()).select_from(self._filtradas(ativa).subquery())
        return self.session.scalar(consulta) or 0

    def listar_pagina(
        self, *, ativa: bool | None, limite: int, deslocamento: int
    ) -> list[AreaComum]:
        """Por nome (sem diferenciar maiúsculas); o ID desempata para a paginação ser estável."""
        consulta = (
            self._filtradas(ativa)
            .order_by(func.lower(AreaComum.nome), AreaComum.id)
            .limit(limite)
            .offset(deslocamento)
        )
        return list(self.session.scalars(consulta))


class RepositorioArquivos(RepositorioDoCondominio[Arquivo]):
    modelo = Arquivo

    def existe(self, arquivo_id: uuid.UUID) -> bool:
        """O arquivo existe NESTE condomínio? Arquivo de outro condomínio (ou da conta/plataforma,
        que não têm condomínio) conta como inexistente."""
        consulta = self.consulta().where(Arquivo.id == arquivo_id)
        return self.session.scalar(select(consulta.exists())) or False


class RepositorioBloqueios(RepositorioDoCondominio[BloqueioArea]):
    """Bloqueios de datas da área (US-602). Removido (`removido_em`) não vale mais."""

    modelo = BloqueioArea

    def _ativos_da_area(self, area_id: uuid.UUID) -> Select[tuple[BloqueioArea]]:
        # Bloqueio removido (removido_em preenchido) não vale mais.
        return self.consulta().where(
            BloqueioArea.area_id == area_id, BloqueioArea.removido_em.is_(None)
        )

    def cobre(self, area_id: uuid.UUID, dia: date) -> bool:
        consulta = self._ativos_da_area(area_id).where(
            BloqueioArea.data_inicio <= dia, BloqueioArea.data_fim >= dia
        )
        return self.session.scalar(select(consulta.exists())) or False

    def pagina(
        self,
        area_id: uuid.UUID,
        *,
        data_de: date | None,
        data_ate: date | None,
        limite: int,
        deslocamento: int,
    ) -> tuple[list[tuple[BloqueioArea, str]], int]:
        """Bloqueios ativos da área que tocam [data_de, data_ate], do mais recente ao mais antigo,
        com o nome do responsável."""
        condicoes: list[ColumnElement[bool]] = []
        if data_de is not None:
            condicoes.append(BloqueioArea.data_fim >= data_de)
        if data_ate is not None:
            condicoes.append(BloqueioArea.data_inicio <= data_ate)
        base = self._ativos_da_area(area_id).where(*condicoes)
        consulta = (
            base.add_columns(ResponsavelAdministracao.nome)
            .join(
                ResponsavelAdministracao,
                and_(
                    ResponsavelAdministracao.id == BloqueioArea.responsavel_id,
                    ResponsavelAdministracao.condominio_id == BloqueioArea.condominio_id,
                ),
            )
            .order_by(BloqueioArea.data_inicio.desc(), BloqueioArea.id)
            .limit(limite)
            .offset(deslocamento)
        )
        itens = [(bloqueio, nome) for bloqueio, nome in self.session.execute(consulta)]
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        return itens, total

    def intervalos_entre(
        self, area_id: uuid.UUID, inicio: date, fim: date
    ) -> list[tuple[date, date]]:
        """(data_inicio, data_fim) dos bloqueios ativos que tocam [inicio, fim]."""
        consulta = self._ativos_da_area(area_id).where(
            BloqueioArea.data_inicio <= fim, BloqueioArea.data_fim >= inicio
        )
        return [(b.data_inicio, b.data_fim) for b in self.session.scalars(consulta)]


@dataclass(frozen=True)
class ReservaDetalhada:
    """A reserva com os nomes que a resposta mostra (área, unidade, quem reservou, responsável)."""

    reserva: Reserva
    area_nome: str
    unidade_identificacao: str
    reservada_por_nome: str
    responsavel_nome: str | None


@dataclass(frozen=True)
class FiltrosAdministracao:
    area_id: uuid.UUID | None = None
    unidade_id: uuid.UUID | None = None
    data_de: date | None = None
    data_ate: date | None = None
    status: str | None = None


class RepositorioReservas(RepositorioDoCondominio[Reserva]):
    modelo = Reserva

    # --- Fase 1: mudança de horário da área ------------------------------------------------

    def existe_ativa_fora_do_horario(
        self, area_id: uuid.UUID, *, a_partir_de: date, abre_as: time, fecha_as: time
    ) -> bool:
        """Há reserva ATIVA, de `a_partir_de` em diante, cujo slot de 1h não cabe em abre/fecha?

        O slot que começa em `hora_inicio` ocupa [hora_inicio, hora_inicio + 1h]. Cabe quando
        `abre_as <= hora_inicio` e `hora_inicio + 1h <= fecha_as`. Como `fecha_as` > `abre_as`
        e ambos são hora cheia, `fecha_as` é pelo menos 01:00 e a conta abaixo não estoura.
        """
        ultimo_inicio = time(fecha_as.hour - 1)
        fora: ColumnElement[bool] = or_(
            Reserva.hora_inicio < abre_as, Reserva.hora_inicio > ultimo_inicio
        )
        consulta = self.consulta().where(
            Reserva.area_id == area_id,
            Reserva.status == "ativa",
            Reserva.data >= a_partir_de,
            fora,
        )
        return self.session.scalar(select(consulta.exists())) or False

    # --- agenda e calendário ---------------------------------------------------------------

    def ativas_do_dia(self, area_id: uuid.UUID, dia: date) -> list[Reserva]:
        consulta = self.consulta().where(
            Reserva.area_id == area_id, Reserva.data == dia, Reserva.status == "ativa"
        )
        return list(self.session.scalars(consulta))

    def horarios_ocupados(
        self, area_id: uuid.UUID, inicio: date, fim: date
    ) -> set[tuple[date, time]]:
        consulta = (
            self.consulta()
            .with_only_columns(Reserva.data, Reserva.hora_inicio)
            .where(
                Reserva.area_id == area_id,
                Reserva.status == "ativa",
                Reserva.data.between(inicio, fim),
            )
        )
        return {(dia, hora) for dia, hora in self.session.execute(consulta).tuples()}

    def dias_com_reserva_ativa_da_unidade(
        self, area_id: uuid.UUID, unidade_id: uuid.UUID, inicio: date, fim: date
    ) -> set[date]:
        consulta = self.consulta().where(
            Reserva.area_id == area_id,
            Reserva.unidade_id == unidade_id,
            Reserva.status == "ativa",
            Reserva.data.between(inicio, fim),
        )
        return {reserva.data for reserva in self.session.scalars(consulta)}

    # --- bloqueio de datas (US-602) --------------------------------------------------------

    def afetadas_por_bloqueio(
        self, area_id: uuid.UUID, inicio: date, fim: date, *, hoje: date, hora_agora: time
    ) -> list[ReservaDetalhada]:
        """Reservas ativas da área entre `inicio` e `fim` (inclusive) que ainda não começaram.

        A que já começou não se cancela (`reserva_encerrada`), então o bloqueio não a afeta.
        """
        ainda_nao_comecou = or_(
            Reserva.data > hoje, and_(Reserva.data == hoje, Reserva.hora_inicio > hora_agora)
        )
        consulta = (
            self._detalhada()
            .where(
                Reserva.area_id == area_id,
                Reserva.status == "ativa",
                Reserva.data.between(inicio, fim),
                ainda_nao_comecou,
            )
            .order_by(Reserva.data, Reserva.hora_inicio, Reserva.id)
        )
        return [self._montar(linha) for linha in self.session.execute(consulta)]

    # --- e-mail do cancelamento (US-803) ---------------------------------------------------

    def enfileirar_cancelamento(self, reserva: Reserva) -> None:
        """Entra na fila (outbox) junto com o cancelamento: se a transação cair, o e-mail some;
        se confirmar, ele está garantido. Vai para quem fez a reserva."""
        destinatario = self.session.scalar(
            select(Usuario.email).where(Usuario.id == reserva.usuario_id)
        )
        if destinatario is None:  # a FK impede; sem e-mail não há o que enviar
            return
        self.session.add(
            EnvioEmail(
                condominio_id=self.contexto.condominio_id,
                destinatario=destinatario,
                evento="reserva_cancelada",
                recurso_tipo="reserva",
                recurso_id=reserva.id,
            )
        )

    # --- objeto completo -------------------------------------------------------------------

    def _detalhada(self) -> Select[Any]:
        """Reserva + nomes. Os joins amarram o condomínio além da chave (as FKs são compostas)."""
        return (
            self.consulta()
            .add_columns(
                AreaComum.nome,
                Unidade.identificacao,
                Usuario.nome,
                ResponsavelAdministracao.nome,
            )
            .join(
                AreaComum,
                and_(
                    AreaComum.id == Reserva.area_id,
                    AreaComum.condominio_id == Reserva.condominio_id,
                ),
            )
            .join(
                Unidade,
                and_(
                    Unidade.id == Reserva.unidade_id,
                    Unidade.condominio_id == Reserva.condominio_id,
                ),
            )
            .join(Usuario, Usuario.id == Reserva.usuario_id)
            .outerjoin(
                ResponsavelAdministracao,
                and_(
                    ResponsavelAdministracao.id == Reserva.cancelada_responsavel_id,
                    ResponsavelAdministracao.condominio_id == Reserva.condominio_id,
                ),
            )
        )

    @staticmethod
    def _montar(linha: Any) -> ReservaDetalhada:
        reserva, area_nome, identificacao, usuario_nome, responsavel_nome = linha
        return ReservaDetalhada(reserva, area_nome, identificacao, usuario_nome, responsavel_nome)

    def obter_detalhada(self, reserva_id: uuid.UUID) -> ReservaDetalhada | None:
        linha = self.session.execute(self._detalhada().where(Reserva.id == reserva_id)).first()
        return None if linha is None else self._montar(linha)

    def bloquear(self, reserva_id: uuid.UUID) -> Reserva | None:
        """A reserva travada até o fim da transação: dois cancelamentos simultâneos não passam
        juntos pela checagem de status."""
        consulta = (
            self.consulta()
            .where(Reserva.id == reserva_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(consulta)

    def _contar(self, consulta: Select[Any]) -> int:
        return self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0

    def _pagina(
        self, consulta: Select[Any], *ordem: Any, limite: int, deslocamento: int
    ) -> list[ReservaDetalhada]:
        consulta = consulta.order_by(*ordem, Reserva.id).limit(limite).offset(deslocamento)
        return [self._montar(linha) for linha in self.session.execute(consulta)]

    def pagina_da_unidade(
        self,
        unidade_id: uuid.UUID,
        *,
        hoje: date,
        hora_agora: time,
        limite: int,
        deslocamento: int,
    ) -> tuple[list[ReservaDetalhada], int]:
        """Lista do Morador (US-604): futuras primeiro, da mais próxima para a mais distante;
        depois as passadas, da mais recente para a mais antiga.

        Futura = início do slot depois de agora (a mesma definição de "passado" da grade, do
        cancelamento e da criação: início <= agora).
        """
        futura = or_(
            Reserva.data > hoje, and_(Reserva.data == hoje, Reserva.hora_inicio > hora_agora)
        )
        base = self._detalhada().where(Reserva.unidade_id == unidade_id)
        itens = self._pagina(
            base,
            case((futura, 0), else_=1),
            case((futura, Reserva.data)).asc(),
            case((futura, Reserva.hora_inicio)).asc(),
            # Nas futuras estas duas colunas valem NULL e não mexem na ordem do grupo.
            case((~futura, Reserva.data)).desc(),
            case((~futura, Reserva.hora_inicio)).desc(),
            limite=limite,
            deslocamento=deslocamento,
        )
        return itens, self._contar(self.consulta().where(Reserva.unidade_id == unidade_id))

    def pagina_do_condominio(
        self, filtros: FiltrosAdministracao, *, limite: int, deslocamento: int
    ) -> tuple[list[ReservaDetalhada], int]:
        """Lista da Administração (US-605): data decrescente, depois hora decrescente."""
        condicoes: list[ColumnElement[bool]] = []
        if filtros.area_id is not None:
            condicoes.append(Reserva.area_id == filtros.area_id)
        if filtros.unidade_id is not None:
            condicoes.append(Reserva.unidade_id == filtros.unidade_id)
        if filtros.data_de is not None:
            condicoes.append(Reserva.data >= filtros.data_de)
        if filtros.data_ate is not None:
            condicoes.append(Reserva.data <= filtros.data_ate)
        if filtros.status is not None:
            condicoes.append(Reserva.status == filtros.status)
        itens = self._pagina(
            self._detalhada().where(*condicoes),
            Reserva.data.desc(),
            Reserva.hora_inicio.desc(),
            limite=limite,
            deslocamento=deslocamento,
        )
        return itens, self._contar(self.consulta().where(*condicoes))
