"""Persistência da trilha: inserção e consulta, sem commit ou métodos de alteração/exclusão."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import literal, select, text, tuple_
from sqlalchemy.orm import Session

from app.core.errors import RecursoNaoEncontrado
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auditoria.schemas import ConsultaAuditoria, CursorAuditoria, ResponsavelRef
from app.modules.condominios.models import Condominio
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from app.modules.usuarios.models import Usuario


def inserir(session: Session, dados: dict[str, Any]) -> None:
    session.add(RegistroAuditoria(**dados))
    session.flush()


def nome_do_responsavel(
    session: Session, condominio_id: uuid.UUID, responsavel: ResponsavelRef
) -> str:
    modelo = ResponsavelAdministracao if responsavel.tipo == "administracao" else Funcionario
    pessoa = session.scalar(
        select(modelo)
        .where(
            modelo.id == responsavel.id,
            modelo.condominio_id == condominio_id,
            modelo.ativo.is_(True),
        )
        .with_for_update(read=True)
    )
    if not isinstance(pessoa, (ResponsavelAdministracao, Funcionario)):
        raise RecursoNaoEncontrado
    return pessoa.nome


def referencias_visiveis(
    session: Session, usuario_id: uuid.UUID | None, condominio_id: uuid.UUID | None
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Segurança não espera FKs de uma transação que ainda pode sofrer rollback.

    IDs inexistentes ou ainda não confirmados não viram referências inválidas. Isso também
    permite registrar a tentativa de login de uma conta inexistente.
    """
    usuario = (
        session.scalar(select(Usuario.id).where(Usuario.id == usuario_id)) if usuario_id else None
    )
    condominio = (
        session.scalar(select(Condominio.id).where(Condominio.id == condominio_id))
        if condominio_id
        else None
    )
    return usuario, condominio


def limitar_espera_seguranca(session: Session) -> None:
    """Uma tentativa de auditar não espera indefinidamente por locks da requisição original."""
    session.execute(text("SET LOCAL lock_timeout = '500ms'"))
    session.execute(text("SET LOCAL statement_timeout = '2s'"))


def consultar(
    session: Session,
    filtros: ConsultaAuditoria,
    *,
    inicio: datetime | None,
    fim_exclusivo: datetime | None,
    posicao: CursorAuditoria | None,
) -> list[tuple[RegistroAuditoria, str | None, str | None]]:
    """Consulta global: o router exige ADM antes de aceitar os filtros da plataforma.

    Keyset por data/id, sem OFFSET, COUNT ou consultas adicionais por item. LEFT JOIN preserva
    eventos sem usuário/condomínio. As funções de negócio dos demais módulos não usam esta consulta.
    """
    consulta = (
        select(RegistroAuditoria, Usuario.nome, Condominio.nome)
        .outerjoin(Usuario, Usuario.id == RegistroAuditoria.usuario_id)
        .outerjoin(Condominio, Condominio.id == RegistroAuditoria.condominio_id)
    )
    if filtros.condominio_id is not None:
        consulta = consulta.where(RegistroAuditoria.condominio_id == filtros.condominio_id)
    if filtros.usuario_id is not None:
        consulta = consulta.where(RegistroAuditoria.usuario_id == filtros.usuario_id)
    if inicio is not None:
        consulta = consulta.where(RegistroAuditoria.criado_em >= inicio)
    if fim_exclusivo is not None:
        consulta = consulta.where(RegistroAuditoria.criado_em < fim_exclusivo)
    if filtros.acao is not None:
        consulta = consulta.where(
            RegistroAuditoria.acao.startswith(filtros.acao, autoescape=True)
            if filtros.acao.endswith(".")
            else RegistroAuditoria.acao == filtros.acao
        )
    if filtros.recurso_tipo is not None:
        consulta = consulta.where(RegistroAuditoria.recurso_tipo == filtros.recurso_tipo)
    if filtros.recurso_id is not None:
        consulta = consulta.where(RegistroAuditoria.recurso_id == filtros.recurso_id)
    if posicao is not None:
        consulta = consulta.where(
            tuple_(RegistroAuditoria.criado_em, RegistroAuditoria.id)
            < tuple_(literal(posicao.criado_em), literal(posicao.id))
        )
    consulta = consulta.order_by(RegistroAuditoria.criado_em.desc(), RegistroAuditoria.id.desc())
    consulta = consulta.limit(filtros.page_size + 1)
    return [
        (evento, usuario_nome, condominio_nome)
        for evento, usuario_nome, condominio_nome in session.execute(consulta).tuples()
    ]
