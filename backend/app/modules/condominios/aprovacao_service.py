import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.auditoria import service as audit
from app.modules.auditoria.models import TipoEventoAuditoria
from app.modules.condominios import aprovacao_repository
from app.modules.condominios.models import ChaveAcesso, Condominio
from app.modules.usuarios.models import Usuario

VALIDADE_CHAVE = timedelta(days=7)


def _hash_seguro(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _exigir_administrador_plataforma(usuario: Usuario) -> None:
    if not usuario.administrador_plataforma:
        raise ApiError(403, "forbidden", "Apenas o administrador da plataforma pode decidir.")


def listar_pendentes(session: Session, *, administrador: Usuario) -> list[dict[str, Any]]:
    _exigir_administrador_plataforma(administrador)
    return [
        {
            "id": condominio.id,
            "nome": condominio.nome,
            "cidade": condominio.cidade,
            "estado": condominio.estado,
            "criado_em": condominio.criado_em,
            "solicitante_nome": solicitante.nome if solicitante else None,
            "solicitante_email": solicitante.email if solicitante else None,
        }
        for condominio, solicitante in aprovacao_repository.listar_pendentes(session)
    ]


def _gerar_chave(
    session: Session,
    *,
    condominio: Condominio,
    administrador: Usuario,
    agora: datetime,
) -> tuple[str, ChaveAcesso]:
    _revogar_chave_disponivel(session, condominio.id, agora)
    codigo = secrets.token_urlsafe(32)
    chave = ChaveAcesso(
        id=uuid.uuid4(),
        condominio_id=condominio.id,
        codigo_hash=_hash_seguro(codigo),
        criada_por_usuario_id=administrador.id,
        expira_em=agora + VALIDADE_CHAVE,
    )
    session.add(chave)
    return codigo, chave


def _revogar_chave_disponivel(session: Session, condominio_id: uuid.UUID, agora: datetime) -> None:
    chave_disponivel = aprovacao_repository.obter_chave_disponivel(
        session, condominio_id, lock=True
    )
    if chave_disponivel is not None:
        chave_disponivel.revogada_em = agora
        session.flush()


def aprovar(
    session: Session,
    *,
    condominio_id: uuid.UUID,
    administrador: Usuario,
    ip: str | None,
) -> dict[str, Any]:
    _exigir_administrador_plataforma(administrador)
    condominio = aprovacao_repository.obter_condominio(session, condominio_id, lock=True)
    if condominio is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")
    if condominio.status != "pendente":
        raise ApiError(409, "conflict", "O condomínio não está pendente de aprovação.")
    conta_admin = aprovacao_repository.obter_administracao(session, condominio.id, lock=True)
    if conta_admin is None:
        raise ApiError(409, "approval_incomplete", "Não há conta de Administração solicitante.")
    usuario_solicitante, vinculo = conta_admin
    agora = datetime.now(UTC)
    codigo, chave = _gerar_chave(
        session, condominio=condominio, administrador=administrador, agora=agora
    )
    condominio.status = "ativo"
    condominio.ativo = True
    condominio.motivo_rejeicao = None
    usuario_solicitante.status_conta = "ativo"
    usuario_solicitante.ativo = True
    vinculo.ativo = True
    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.APROVACAO,
            recurso="condominio",
            recurso_id=str(condominio.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="plataforma",
            condominio_id=condominio.id,
            ip=ip,
            dados_antes={"status": "pendente"},
            dados_depois={"status": "ativo"},
        )
        _registrar_notificacao(
            session,
            condominio=condominio,
            destinatario_id=condominio.solicitante_id or usuario_solicitante.id,
            administrador=administrador,
            ip=ip,
            status="aprovado",
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(409, "conflict", "Não foi possível aprovar o condomínio.") from erro
    except Exception:
        session.rollback()
        raise
    return {
        "condominio_id": condominio.id,
        "status": condominio.status,
        "chave_acesso": codigo,
        "expira_em": chave.expira_em,
    }


def _registrar_notificacao(
    session: Session,
    *,
    condominio: Condominio,
    destinatario_id: uuid.UUID,
    administrador: Usuario,
    ip: str | None,
    status: str,
) -> None:
    audit.log(
        session,
        tipo_evento=TipoEventoAuditoria.NOTIFICACAO_CONDOMINIO,
        recurso="notificacao",
        recurso_id=str(condominio.id),
        usuario_id=destinatario_id,
        ator=administrador.nome,
        perfil="plataforma",
        condominio_id=condominio.id,
        ip=ip,
        dados_depois={"tipo": "decisao_condominio", "status": status},
    )


def rejeitar(
    session: Session,
    *,
    condominio_id: uuid.UUID,
    administrador: Usuario,
    motivo: str,
    ip: str | None,
) -> dict[str, Any]:
    _exigir_administrador_plataforma(administrador)
    condominio = aprovacao_repository.obter_condominio(session, condominio_id, lock=True)
    if condominio is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")
    if condominio.status != "pendente":
        raise ApiError(409, "conflict", "O condomínio não está pendente de aprovação.")
    conta_admin = aprovacao_repository.obter_administracao(session, condominio.id, lock=True)
    condominio.status = "rejeitado"
    condominio.ativo = False
    condominio.motivo_rejeicao = motivo
    if conta_admin is not None:
        usuario_solicitante, vinculo = conta_admin
        usuario_solicitante.status_conta = "rejeitado"
        usuario_solicitante.ativo = False
        vinculo.ativo = False
        destinatario_id = condominio.solicitante_id or usuario_solicitante.id
    elif condominio.solicitante_id:
        destinatario_id = condominio.solicitante_id
    else:
        raise ApiError(409, "approval_incomplete", "Não há solicitante associado ao condomínio.")
    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.REJEICAO,
            recurso="condominio",
            recurso_id=str(condominio.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="plataforma",
            condominio_id=condominio.id,
            ip=ip,
            dados_antes={"status": "pendente"},
            dados_depois={"status": "rejeitado", "motivo": motivo},
        )
        _registrar_notificacao(
            session,
            condominio=condominio,
            destinatario_id=destinatario_id,
            administrador=administrador,
            ip=ip,
            status="rejeitado",
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(409, "conflict", "Não foi possível rejeitar o condomínio.") from erro
    except Exception:
        session.rollback()
        raise
    return {
        "condominio_id": condominio.id,
        "status": condominio.status,
        "motivo_rejeicao": condominio.motivo_rejeicao,
        "notificacao_registrada": True,
    }


def regenerar_chave(
    session: Session,
    *,
    condominio_id: uuid.UUID,
    administrador: Usuario,
    ip: str | None,
) -> dict[str, Any]:
    _exigir_administrador_plataforma(administrador)
    condominio = aprovacao_repository.obter_condominio(session, condominio_id, lock=True)
    if condominio is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")
    if condominio.status != "ativo":
        raise ApiError(409, "conflict", "Só é possível gerar chave para condomínio aprovado.")
    agora = datetime.now(UTC)
    try:
        codigo, chave = _gerar_chave(
            session, condominio=condominio, administrador=administrador, agora=agora
        )
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
            recurso="chave_acesso_condominio",
            recurso_id=str(condominio.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="plataforma",
            condominio_id=condominio.id,
            ip=ip,
            dados_depois={"acao": "regeneracao", "expira_em": chave.expira_em.isoformat()},
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(409, "conflict", "Não foi possível regenerar a chave.") from erro
    except Exception:
        session.rollback()
        raise
    return {
        "condominio_id": condominio.id,
        "status": condominio.status,
        "chave_acesso": codigo,
        "expira_em": chave.expira_em,
    }


def revogar_chave(
    session: Session,
    *,
    condominio_id: uuid.UUID,
    administrador: Usuario,
    ip: str | None,
) -> dict[str, Any]:
    _exigir_administrador_plataforma(administrador)
    condominio = aprovacao_repository.obter_condominio(session, condominio_id, lock=True)
    if condominio is None:
        raise ApiError(404, "not_found", "Condomínio não encontrado.")
    chave = aprovacao_repository.obter_chave_disponivel(session, condominio.id, lock=True)
    if chave is None:
        raise ApiError(409, "conflict", "Não há chave disponível para revogar.")
    chave.revogada_em = datetime.now(UTC)
    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
            recurso="chave_acesso_condominio",
            recurso_id=str(condominio.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="plataforma",
            condominio_id=condominio.id,
            ip=ip,
            dados_depois={"acao": "revogacao"},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"condominio_id": condominio.id, "revogada": True}


def _chave_valida(chave: ChaveAcesso, condominio: Condominio, *, agora: datetime) -> bool:
    return (
        condominio.status == "ativo"
        and condominio.ativo
        and chave.usada_em is None
        and chave.revogada_em is None
        and chave.expira_em > agora
    )


def validar_chave(session: Session, *, codigo: str) -> dict[str, Any]:
    resultado = aprovacao_repository.obter_chave_por_hash(session, _hash_seguro(codigo))
    if resultado is None:
        return {"valida": False, "condominio_id": None, "condominio_nome": None, "expira_em": None}
    chave, condominio = resultado
    valida = _chave_valida(chave, condominio, agora=datetime.now(UTC))
    return {
        "valida": valida,
        "condominio_id": condominio.id if valida else None,
        "condominio_nome": condominio.nome if valida else None,
        "expira_em": chave.expira_em if valida else None,
    }


def consumir_chave(session: Session, *, codigo: str) -> Condominio:
    resultado = aprovacao_repository.obter_chave_por_hash(session, _hash_seguro(codigo), lock=True)
    if resultado is None:
        raise ApiError(422, "invalid_access_key", "Chave de acesso inválida ou indisponível.")
    chave, condominio = resultado
    if not _chave_valida(chave, condominio, agora=datetime.now(UTC)):
        raise ApiError(422, "invalid_access_key", "Chave de acesso inválida ou indisponível.")
    chave.usada_em = datetime.now(UTC)
    return condominio


def status_solicitacao(session: Session, *, condominio_id: uuid.UUID, token: str) -> dict[str, Any]:
    condominio = aprovacao_repository.obter_solicitacao_por_token(
        session, condominio_id, _hash_seguro(token)
    )
    if condominio is None:
        raise ApiError(404, "not_found", "Solicitação não encontrada.")
    return {
        "condominio_id": condominio.id,
        "nome": condominio.nome,
        "status": condominio.status,
        "motivo_rejeicao": condominio.motivo_rejeicao,
        "criado_em": condominio.criado_em,
    }
