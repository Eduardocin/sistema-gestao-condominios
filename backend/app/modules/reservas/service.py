"""Regras das áreas comuns e das reservas (convivencia.md, seções 2 e 4).

Quem chama já passou por `require_permission` (perfil): ver o router. Aqui ficam o passo 4 quando
a unidade vem da query, do corpo ou da própria reserva (`garantir_aba_da_unidade`), o passo 5
(o recurso existe no condomínio?), o passo 6 (regras de negócio), a auditoria e o commit.
"""

import calendar
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, agora, inicio_do_slot, no_fuso
from app.modules.auth.autorizacao import garantir_aba_da_unidade, garantir_aba_no_condominio
from app.modules.funcionarios.repository import RepositorioResponsaveis
from app.modules.permissoes_aba.repository import RepositorioAuditoria
from app.modules.reservas.models import AreaComum, Reserva
from app.modules.reservas.repository import (
    FiltrosAdministracao,
    RepositorioAreasComuns,
    RepositorioArquivos,
    RepositorioBloqueios,
    RepositorioReservas,
    ReservaDetalhada,
)
from app.modules.reservas.schemas import (
    AgendaSaida,
    AreaComumEntrada,
    CalendarioSaida,
    CancelamentoEntrada,
    CancelamentoSaida,
    DiaDoCalendario,
    PaginaDeReservas,
    Referencia,
    ReservaEntrada,
    ReservaSaida,
    SlotSaida,
    UnidadeRef,
)

# Nomes dos índices/constraints do DER: é por eles que traduzimos a violação no `reason`.
INDICE_NOME_UNICO = "uq_areas_comuns_condominio_nome"
FK_FOTO = "fk_areas_comuns_foto"
INDICE_UNIDADE_AREA_DIA = "uq_reservas_unidade_area_dia_ativa"
INDICE_AREA_HORARIO = "uq_reservas_area_horario_ativa"

MENSAGEM_NOME_DUPLICADO = "Já existe uma área comum com esse nome neste condomínio."
MENSAGEM_FOTO_INVALIDA = "A foto informada não existe neste condomínio."
MENSAGEM_FORA_DO_HORARIO = (
    "Há reservas ativas fora do novo horário de funcionamento. "
    "Cancele essas reservas ou mantenha o horário atual."
)
MENSAGEM_JA_DESATIVADA = "A área comum já está desativada."
MENSAGEM_JA_ATIVA = "A área comum já está ativa."

# Mensagens do contrato (seção 4.2), prontas para o front exibir. A de horário ocupado NUNCA
# cita a outra unidade.
MENSAGEM_DUPLICADA_UNIDADE = "Cada unidade pode reservar no máximo um horário por área por dia."
MENSAGEM_HORARIO_OCUPADO = "Este horário acabou de ser reservado por outra unidade. Escolha outro."
MENSAGEM_HORA_INVALIDA = "Escolha um horário em hora cheia (por exemplo, 18:00)."
MENSAGEM_FORA_DO_FUNCIONAMENTO = "Esse horário está fora do funcionamento da área."
MENSAGEM_HORARIO_PASSADO = "Esse horário já passou."
MENSAGEM_AREA_BLOQUEADA = "A área está bloqueada nessa data."
MENSAGEM_JA_CANCELADA = "A reserva já está cancelada."
MENSAGEM_ENCERRADA = "O horário da reserva já começou; ela não pode mais ser cancelada."
MENSAGEM_UNIDADE_OBRIGATORIA = "Informe a unidade."
MENSAGEM_CANCELAMENTO_ADM = "Informe o motivo e o responsável pelo cancelamento."
MENSAGEM_CANCELAMENTO_MORADOR = "O cancelamento pelo morador não aceita motivo nem responsável."

ABA_RESERVAS = "reservas"
UMA_HORA = timedelta(hours=1)


@dataclass(frozen=True)
class AreasPaginadas:
    items: list[AreaComum]
    page: int
    page_size: int
    total: int


def _nome_da_constraint(erro: IntegrityError) -> str | None:
    """Nome da constraint violada, como o PostgreSQL informa (psycopg: `orig.diag`)."""
    diag = getattr(erro.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _gravar_traduzindo[T](
    session: Session, operacao: Callable[[], T], erros: dict[str, ApiError]
) -> T:
    """Roda o INSERT/UPDATE num savepoint e traduz a violação de constraint pelo NOME.

    Quem garante as regras de unicidade é o banco, não um SELECT prévio: dois pedidos simultâneos
    passariam juntos pela consulta. O savepoint preserva a transação (e a sessão) para o erro ser
    respondido sem derrubar o resto. Constraint desconhecida: o erro segue (vira 500).
    """
    try:
        with session.begin_nested():
            return operacao()
    except IntegrityError as erro:
        traduzido = erros.get(_nome_da_constraint(erro) or "")
        if traduzido is None:
            raise
        raise traduzido from erro


def _hora_fim(hora_inicio: time) -> time:
    return (datetime.combine(date.min, hora_inicio) + UMA_HORA).time()


class AreasComunsService:
    def __init__(
        self, session: Session, contexto: ContextoCondominio, relogio: Relogio = agora
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.relogio = relogio
        self.areas = RepositorioAreasComuns(session, contexto)
        self.arquivos = RepositorioArquivos(session, contexto)
        self.reservas = RepositorioReservas(session, contexto)

    # --- leitura --------------------------------------------------------------------------

    def listar(self, *, page: int, page_size: int, ativa: bool | None) -> AreasPaginadas:
        garantir_aba_no_condominio(self.session, self.contexto, ABA_RESERVAS)
        # Morador só enxerga ativas, mesmo que peça `ativa=false`. O filtro é só da Administração.
        if self.contexto.perfil == Perfil.MORADOR:
            ativa = True
        return AreasPaginadas(
            items=self.areas.listar_pagina(
                ativa=ativa, limite=page_size, deslocamento=(page - 1) * page_size
            ),
            page=page,
            page_size=page_size,
            total=self.areas.contar(ativa=ativa),
        )

    def obter(self, area_id: uuid.UUID) -> AreaComum:
        garantir_aba_no_condominio(self.session, self.contexto, ABA_RESERVAS)
        area = self.areas.obter(area_id)  # 404 se não existir ou for de outro condomínio
        if self.contexto.perfil == Perfil.MORADOR and not area.ativa:
            raise RecursoNaoEncontrado  # área desativada some para o Morador
        return area

    # --- escrita --------------------------------------------------------------------------

    def criar(self, dados: AreaComumEntrada) -> AreaComum:
        valores = dados.model_dump()
        self._conferir_foto(dados)
        area = self._gravar(lambda: self.areas.criar(valores))
        self.session.commit()
        return area

    def editar(self, area_id: uuid.UUID, dados: AreaComumEntrada) -> AreaComum:
        area = self.areas.obter(area_id)
        self._conferir_foto(dados)
        if (dados.abre_as, dados.fecha_as) != (area.abre_as, area.fecha_as) and (
            self.reservas.existe_ativa_fora_do_horario(
                area.id,
                a_partir_de=no_fuso(self.relogio()).date(),
                abre_as=dados.abre_as,
                fecha_as=dados.fecha_as,
            )
        ):
            raise ApiError(
                409, "conflict", MENSAGEM_FORA_DO_HORARIO, reason="reservas_fora_do_horario"
            )
        valores = dados.model_dump()
        atualizada = self._gravar(lambda: self.areas.atualizar(area.id, valores))
        self.session.commit()
        return atualizada

    def desativar(self, area_id: uuid.UUID) -> AreaComum:
        """Não mexe em reservas existentes: a Administração cancela uma a uma, se quiser."""
        area = self.areas.obter(area_id)
        if not area.ativa:
            raise ApiError(409, "conflict", MENSAGEM_JA_DESATIVADA, reason="area_ja_desativada")
        return self._definir_ativa(area.id, False)

    def reativar(self, area_id: uuid.UUID) -> AreaComum:
        area = self.areas.obter(area_id)
        if area.ativa:
            raise ApiError(409, "conflict", MENSAGEM_JA_ATIVA, reason="area_ja_ativa")
        return self._definir_ativa(area.id, True)

    # --- apoio ----------------------------------------------------------------------------

    def _definir_ativa(self, area_id: uuid.UUID, ativa: bool) -> AreaComum:
        area = self.areas.atualizar(area_id, {"ativa": ativa})
        self.session.commit()
        return area

    def _conferir_foto(self, dados: AreaComumEntrada) -> None:
        # A FK composta do banco é a última defesa; aqui damos o 422 com o motivo certo.
        if not self.arquivos.existe(dados.foto_arquivo_id):
            raise ApiError(422, "validation_error", MENSAGEM_FOTO_INVALIDA, reason="foto_invalida")

    def _gravar[T](self, operacao: Callable[[], T]) -> T:
        return _gravar_traduzindo(
            self.session,
            operacao,
            {
                INDICE_NOME_UNICO: ApiError(
                    409, "conflict", MENSAGEM_NOME_DUPLICADO, reason="nome_duplicado"
                ),
                FK_FOTO: ApiError(
                    422, "validation_error", MENSAGEM_FOTO_INVALIDA, reason="foto_invalida"
                ),
            },
        )


class ReservasService:
    def __init__(
        self, session: Session, contexto: ContextoCondominio, relogio: Relogio = agora
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.relogio = relogio
        self.areas = RepositorioAreasComuns(session, contexto)
        self.reservas = RepositorioReservas(session, contexto)
        self.bloqueios = RepositorioBloqueios(session, contexto)
        self.responsaveis = RepositorioResponsaveis(session, contexto)
        # TODO: trocar por registrar_acao (TASK-82)
        self.auditoria = RepositorioAuditoria(session, contexto)

    @property
    def _e_morador(self) -> bool:
        return self.contexto.perfil == Perfil.MORADOR

    @property
    def _e_administracao(self) -> bool:
        return self.contexto.perfil == Perfil.ADMINISTRACAO

    def _ja_comecou(self, dia: date, hora: time) -> bool:
        """ "Passado" = início do slot <= agora, no fuso do condomínio. Vale para a grade, a
        criação, o cancelamento e a ordem da lista do Morador."""
        return inicio_do_slot(dia, hora) <= no_fuso(self.relogio())

    def _unidade(self, unidade_id: uuid.UUID) -> None:
        # Passo 4: 404 se a unidade não é do Morador, depois 403 se a aba estiver Sem Acesso.
        garantir_aba_da_unidade(self.session, self.contexto, unidade_id, ABA_RESERVAS)

    def _area_ativa(self, area_id: uuid.UUID) -> AreaComum:
        area = self.areas.obter(area_id)  # outro condomínio ou inexistente: 404
        if not area.ativa:
            raise RecursoNaoEncontrado  # desativada não aceita reserva nem aparece na agenda
        return area

    # --- agenda e calendário (só Morador) ---------------------------------------------------

    def agenda(self, area_id: uuid.UUID, unidade_id: uuid.UUID, dia: date) -> AgendaSaida:
        self._unidade(unidade_id)
        area = self._area_ativa(area_id)
        ativas = self.reservas.ativas_do_dia(area.id, dia)
        por_hora = {reserva.hora_inicio.hour: reserva for reserva in ativas}
        bloqueado = self.bloqueios.cobre(area.id, dia)

        slots = []
        for hora in range(area.abre_as.hour, area.fecha_as.hour):
            inicio = time(hora)
            reserva = por_hora.get(hora)
            # Precedência: da_minha_unidade > ocupado > bloqueado > passado > livre.
            if reserva is not None and reserva.unidade_id == unidade_id:
                slot = SlotSaida(
                    hora_inicio=inicio,
                    hora_fim=_hora_fim(inicio),
                    estado="da_minha_unidade",
                    reserva_id=reserva.id,
                )
            else:
                if reserva is not None:
                    estado = "ocupado"  # sem dizer qual unidade: nem id, nem reserva_id
                elif bloqueado:
                    estado = "bloqueado"
                elif self._ja_comecou(dia, inicio):
                    estado = "passado"
                else:
                    estado = "livre"
                slot = SlotSaida(hora_inicio=inicio, hora_fim=_hora_fim(inicio), estado=estado)
            slots.append(slot)

        return AgendaSaida(
            area_id=area.id,
            unidade_id=unidade_id,
            data=dia,
            unidade_ja_reservou=any(r.unidade_id == unidade_id for r in ativas),
            slots=slots,
        )

    def calendario(self, area_id: uuid.UUID, unidade_id: uuid.UUID, mes: str) -> CalendarioSaida:
        self._unidade(unidade_id)
        area = self._area_ativa(area_id)
        ano, numero = (int(parte) for parte in mes.split("-"))
        inicio = date(ano, numero, 1)
        fim = date(ano, numero, calendar.monthrange(ano, numero)[1])

        bloqueados: set[date] = set()
        for de, ate in self.bloqueios.intervalos_entre(area.id, inicio, fim):
            dia = max(de, inicio)
            while dia <= min(ate, fim):
                bloqueados.add(dia)
                dia += timedelta(days=1)
        com_reserva = self.reservas.dias_com_reserva_ativa_da_unidade(
            area.id, unidade_id, inicio, fim
        )
        return CalendarioSaida(
            mes=mes,
            dias=[
                DiaDoCalendario(
                    data=dia,
                    bloqueado=dia in bloqueados,
                    tem_reserva_da_minha_unidade=dia in com_reserva,
                )
                for dia in sorted(bloqueados | com_reserva)
            ],
        )

    # --- criar ----------------------------------------------------------------------------

    def criar(self, dados: ReservaEntrada, *, ip: str | None) -> ReservaSaida:
        """Ordem do contrato (seção 4.2); a primeira falha encerra."""
        self._unidade(dados.unidade_id)  # 4
        area = self._area_ativa(dados.area_id)  # 5
        hora = dados.hora_inicio
        if hora.minute or hora.second or hora.microsecond:  # 6
            raise ApiError(422, "validation_error", MENSAGEM_HORA_INVALIDA, reason="hora_invalida")
        if not (area.abre_as <= hora and hora.hour + 1 <= area.fecha_as.hour):  # 7
            raise ApiError(
                422,
                "validation_error",
                MENSAGEM_FORA_DO_FUNCIONAMENTO,
                reason="fora_do_funcionamento",
            )
        if self._ja_comecou(dados.data, hora):  # 8
            raise ApiError(
                422, "validation_error", MENSAGEM_HORARIO_PASSADO, reason="horario_passado"
            )
        if self.bloqueios.cobre(area.id, dados.data):  # 9
            raise ApiError(409, "conflict", MENSAGEM_AREA_BLOQUEADA, reason="area_bloqueada")

        # 10 e 11: sem SELECT prévio. O INSERT tenta e os índices únicos parciais decidem.
        valores: dict[str, Any] = {
            "area_id": area.id,
            "unidade_id": dados.unidade_id,
            "usuario_id": self.contexto.usuario_id,
            "data": dados.data,
            "hora_inicio": hora,
            "status": "ativa",
        }
        reserva: Reserva = _gravar_traduzindo(
            self.session,
            lambda: self.reservas.criar(valores),
            {
                INDICE_UNIDADE_AREA_DIA: ApiError(
                    409,
                    "conflict",
                    MENSAGEM_DUPLICADA_UNIDADE,
                    reason="reserva_duplicada_unidade",
                ),
                INDICE_AREA_HORARIO: ApiError(
                    409, "conflict", MENSAGEM_HORARIO_OCUPADO, reason="horario_ocupado"
                ),
            },
        )
        self.auditoria.registrar(
            acao="reserva.criar",
            recurso_tipo="reserva",
            recurso_id=reserva.id,
            antes={},
            depois={
                "area_id": str(area.id),
                "unidade_id": str(dados.unidade_id),
                "data": dados.data.isoformat(),
                "hora_inicio": hora.strftime("%H:%M"),
            },
            ip=ip,
        )
        self.session.commit()  # reserva e auditoria juntas, ou nenhuma das duas
        return self._saida(reserva.id)

    # --- consultar ------------------------------------------------------------------------

    def listar(
        self,
        *,
        unidade_id: uuid.UUID | None,
        filtros: FiltrosAdministracao,
        page: int,
        page_size: int,
    ) -> PaginaDeReservas:
        deslocamento = (page - 1) * page_size
        if self._e_morador:
            # Para o Morador só vale `unidade_id`; os filtros da Administração são ignorados.
            if unidade_id is None:
                raise ApiError(422, "validation_error", MENSAGEM_UNIDADE_OBRIGATORIA)
            self._unidade(unidade_id)
            momento = no_fuso(self.relogio())
            itens, total = self.reservas.pagina_da_unidade(
                unidade_id,
                hoje=momento.date(),
                hora_agora=momento.time().replace(tzinfo=None),
                limite=page_size,
                deslocamento=deslocamento,
            )
        else:
            # Filtros sempre dentro do condomínio do token: unidade de outro prédio = lista vazia.
            itens, total = self.reservas.pagina_do_condominio(
                replace(filtros, unidade_id=unidade_id),
                limite=page_size,
                deslocamento=deslocamento,
            )
        return PaginaDeReservas(
            items=[self._apresentar(item) for item in itens],
            page=page,
            page_size=page_size,
            total=total,
        )

    def obter(self, reserva_id: uuid.UUID) -> ReservaSaida:
        detalhada = self.reservas.obter_detalhada(reserva_id)
        if detalhada is None:
            raise RecursoNaoEncontrado
        if self._e_morador:
            # Reserva de outra unidade: 404. Da própria unidade com a aba Sem Acesso: 403.
            self._unidade(detalhada.reserva.unidade_id)
        return self._apresentar(detalhada)

    # --- cancelar -------------------------------------------------------------------------

    def cancelar(
        self, reserva_id: uuid.UUID, dados: CancelamentoEntrada, *, ip: str | None
    ) -> ReservaSaida:
        administracao = self._e_administracao
        # Entrada que depende do perfil: o schema não sabe quem chama, o service sabe.
        if administracao and (dados.motivo is None or dados.responsavel_id is None):
            raise ApiError(422, "validation_error", MENSAGEM_CANCELAMENTO_ADM)
        if not administracao and (dados.motivo is not None or dados.responsavel_id is not None):
            raise ApiError(422, "validation_error", MENSAGEM_CANCELAMENTO_MORADOR)

        reserva = self.reservas.bloquear(reserva_id)  # trava a linha até o commit
        if reserva is None:
            raise RecursoNaoEncontrado
        if self._e_morador:
            # Qualquer morador da unidade com a aba Reservas cancela as reservas da unidade
            # (convivencia.md, seção 8, proposta). Outra unidade: 404; aba Sem Acesso: 403.
            self._unidade(reserva.unidade_id)

        responsavel = None
        if administracao:
            assert dados.responsavel_id is not None  # conferido acima
            # Inexistente, inativo ou de outro condomínio: 404 genérico.
            responsavel = self.responsaveis.obter_ativo(dados.responsavel_id)

        if reserva.status != "ativa":
            raise ApiError(409, "conflict", MENSAGEM_JA_CANCELADA, reason="reserva_ja_cancelada")
        if self._ja_comecou(reserva.data, reserva.hora_inicio):
            raise ApiError(409, "conflict", MENSAGEM_ENCERRADA, reason="reserva_encerrada")

        valores: dict[str, Any] = {
            "status": "cancelada",
            "cancelada_em": func.now(),
            "cancelada_por_usuario_id": self.contexto.usuario_id,
        }
        if responsavel is not None:
            valores["cancelada_responsavel_id"] = responsavel.id
            valores["motivo_cancelamento"] = dados.motivo
        # Cancelar tira a reserva dos índices parciais (status = 'ativa'): o horário fica livre
        # na hora, e o registro cancelado continua no histórico.
        self.reservas.atualizar(reserva.id, valores)

        if responsavel is not None:
            # TODO(TASK-48): na mesma transação, antes do commit, entram aqui (1) o aviso para a
            # unidade com o motivo (`publicar_para_unidade`, plataforma.md seção 1) e (2) o
            # e-mail `reserva_cancelada` ao morador que reservou (plataforma.md seção 6).
            # O cancelamento pelo Morador não gera aviso nem e-mail.
            pass

        depois: dict[str, Any] = {
            "status": "cancelada",
            "por": "administracao" if responsavel is not None else "morador",
        }
        if responsavel is not None:
            depois["responsavel_id"] = str(responsavel.id)
            depois["motivo"] = dados.motivo
        self.auditoria.registrar(
            acao="reserva.cancelar",
            recurso_tipo="reserva",
            recurso_id=reserva.id,
            antes={"status": "ativa"},
            depois=depois,
            ip=ip,
            responsavel_nome=responsavel.nome if responsavel is not None else None,
        )
        self.session.commit()
        return self._saida(reserva.id)

    # --- apresentação ---------------------------------------------------------------------

    def _saida(self, reserva_id: uuid.UUID) -> ReservaSaida:
        detalhada = self.reservas.obter_detalhada(reserva_id)
        if detalhada is None:  # acabou de ser gravada neste condomínio: não acontece
            raise RecursoNaoEncontrado
        return self._apresentar(detalhada)

    def _apresentar(self, detalhada: ReservaDetalhada) -> ReservaSaida:
        """Monta o objeto do contrato. Campo não preenchido aqui é omitido na resposta.

        `reservada_por` vai sempre: o Morador só chega até reservas das próprias unidades (o
        passo 4 já barrou as outras), e a Administração vê o condomínio todo. `responsavel`, no
        cancelamento, só vai para a Administração.
        """
        reserva = detalhada.reserva
        cancelamento = None
        if reserva.status == "cancelada" and reserva.cancelada_em is not None:
            pela_administracao = reserva.cancelada_responsavel_id is not None
            campos: dict[str, Any] = {
                "em": reserva.cancelada_em,
                "por": "administracao" if pela_administracao else "morador",
                "motivo": reserva.motivo_cancelamento,
            }
            if self._e_administracao:
                campos["responsavel"] = (
                    Referencia(
                        id=reserva.cancelada_responsavel_id,
                        nome=detalhada.responsavel_nome or "",
                    )
                    if reserva.cancelada_responsavel_id is not None
                    else None
                )
            cancelamento = CancelamentoSaida(**campos)

        return ReservaSaida(
            id=reserva.id,
            area=Referencia(id=reserva.area_id, nome=detalhada.area_nome),
            unidade=UnidadeRef(
                id=reserva.unidade_id, identificacao=detalhada.unidade_identificacao
            ),
            data=reserva.data,
            hora_inicio=reserva.hora_inicio,
            hora_fim=_hora_fim(reserva.hora_inicio),
            status="cancelada" if reserva.status == "cancelada" else "ativa",
            reservada_por=Referencia(id=reserva.usuario_id, nome=detalhada.reservada_por_nome),
            criada_em=reserva.criado_em,
            cancelamento=cancelamento,
        )
