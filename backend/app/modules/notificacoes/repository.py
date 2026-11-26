"""Consultas da fila `envios_email`. Só aqui se fala com o banco.

A fila é do sistema, não de um condomínio: o worker e o ADM da plataforma enxergam todos. Por isso
o repositório não herda de `RepositorioDoCondominio`. Os dados do corpo do e-mail, porém, são
sempre buscados com o `condominio_id` do próprio envio.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio
from app.modules.encomendas.models import Encomenda
from app.modules.notificacoes.models import EnvioEmail
from app.modules.reservas.models import AreaComum, Reserva
from app.modules.unidades.models import Unidade


@dataclass(frozen=True)
class FiltrosEnvios:
    status: str | None = None
    evento: str | None = None
    condominio_id: uuid.UUID | None = None
    de: date | None = None
    ate: date | None = None


def proximo_pendente(
    session: Session, *, max_tentativas: int, ignorar: set[uuid.UUID]
) -> EnvioEmail | None:
    """O envio pendente mais antigo, com a linha travada até o commit.

    `SKIP LOCKED`: dois workers (ou um worker e um reenvio) nunca pegam o mesmo envio.
    """
    consulta = (
        select(EnvioEmail)
        .where(EnvioEmail.status == "pendente", EnvioEmail.tentativas < max_tentativas)
        .order_by(EnvioEmail.criado_em, EnvioEmail.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if ignorar:
        consulta = consulta.where(EnvioEmail.id.not_in(ignorar))
    return session.scalar(consulta)


def _filtrados(filtros: FiltrosEnvios) -> Select[tuple[EnvioEmail]]:
    consulta = select(EnvioEmail)
    if filtros.status is not None:
        consulta = consulta.where(EnvioEmail.status == filtros.status)
    if filtros.evento is not None:
        consulta = consulta.where(EnvioEmail.evento == filtros.evento)
    if filtros.condominio_id is not None:
        consulta = consulta.where(EnvioEmail.condominio_id == filtros.condominio_id)
    if filtros.de is not None:
        consulta = consulta.where(
            EnvioEmail.criado_em >= datetime.combine(filtros.de, time.min, tzinfo=UTC)
        )
    if filtros.ate is not None:
        fim = datetime.combine(filtros.ate + timedelta(days=1), time.min, tzinfo=UTC)
        consulta = consulta.where(EnvioEmail.criado_em < fim)
    return consulta


def pagina(
    session: Session, filtros: FiltrosEnvios, *, limite: int, deslocamento: int
) -> tuple[list[EnvioEmail], int]:
    base = _filtrados(filtros)
    itens = list(
        session.scalars(
            base.order_by(EnvioEmail.criado_em.desc(), EnvioEmail.id)
            .limit(limite)
            .offset(deslocamento)
        )
    )
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    return itens, total


def obter(session: Session, envio_id: uuid.UUID) -> EnvioEmail | None:
    return session.get(EnvioEmail, envio_id)


def recolocar_na_fila(session: Session, envio_id: uuid.UUID) -> EnvioEmail | None:
    """`falhou` -> `pendente`, zerando as tentativas. Condicional ao status ainda ser `falhou`:
    dois pedidos de reenvio simultâneos não passam juntos (o segundo recebe `None`)."""
    return session.scalar(
        update(EnvioEmail)
        .where(EnvioEmail.id == envio_id, EnvioEmail.status == "falhou")
        .values(status="pendente", tentativas=0, ultimo_erro=None)
        .returning(EnvioEmail)
        .execution_options(populate_existing=True)
    )


# --- dados do corpo do e-mail ---------------------------------------------------------------


def _uma_linha(session: Session, consulta: Select[Any]) -> Any:
    return session.execute(consulta).first()


def condominio_do_envio(session: Session, envio: EnvioEmail) -> str | None:
    if envio.condominio_id is None:
        return None
    return session.scalar(select(Condominio.nome).where(Condominio.id == envio.condominio_id))


def dados_da_encomenda(session: Session, envio: EnvioEmail) -> tuple[str, str] | None:
    """(descrição, identificação da unidade) da encomenda do envio."""
    linha = _uma_linha(
        session,
        select(Encomenda.descricao, Unidade.identificacao)
        .join(
            Unidade,
            (Unidade.id == Encomenda.unidade_id)
            & (Unidade.condominio_id == Encomenda.condominio_id),
        )
        .where(Encomenda.id == envio.recurso_id, Encomenda.condominio_id == envio.condominio_id),
    )
    return None if linha is None else (linha[0], linha[1])


def dados_da_reserva(session: Session, envio: EnvioEmail) -> tuple[Reserva, str] | None:
    """A reserva do envio e o nome da área."""
    linha = _uma_linha(
        session,
        select(Reserva, AreaComum.nome)
        .join(
            AreaComum,
            (AreaComum.id == Reserva.area_id) & (AreaComum.condominio_id == Reserva.condominio_id),
        )
        .where(Reserva.id == envio.recurso_id, Reserva.condominio_id == envio.condominio_id),
    )
    return None if linha is None else (linha[0], linha[1])
