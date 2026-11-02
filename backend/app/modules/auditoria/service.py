import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.auditoria import repository
from app.modules.auditoria.models import (
    PERFIS_CONTAS_COMPARTILHADAS,
    EventoAuditoria,
    TipoEventoAuditoria,
)


def log(
    session: Session,
    *,
    tipo_evento: TipoEventoAuditoria,
    recurso: str,
    usuario_id: uuid.UUID | None = None,
    ator: str | None = None,
    perfil: str | None = None,
    condominio_id: uuid.UUID | None = None,
    recurso_id: str | None = None,
    ip: str | None = None,
    dados_antes: dict[str, Any] | list[Any] | None = None,
    dados_depois: dict[str, Any] | list[Any] | None = None,
    conta_compartilhada: bool = False,
    nome_responsavel: str | None = None,
) -> EventoAuditoria:
    conta_compartilhada = conta_compartilhada or perfil in PERFIS_CONTAS_COMPARTILHADAS
    if conta_compartilhada and not (nome_responsavel and nome_responsavel.strip()):
        raise ValueError("nome_responsavel é obrigatório para conta compartilhada")

    evento = EventoAuditoria(
        usuario_id=usuario_id,
        ator=ator,
        perfil=perfil,
        condominio_id=condominio_id,
        tipo_evento=tipo_evento.value,
        recurso=recurso,
        recurso_id=recurso_id,
        ip=ip,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
        conta_compartilhada=conta_compartilhada,
        nome_responsavel=nome_responsavel.strip() if nome_responsavel else None,
    )
    return repository.criar(session, evento)
