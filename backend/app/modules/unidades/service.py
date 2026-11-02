import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.auditoria import service as audit
from app.modules.auditoria.models import TipoEventoAuditoria
from app.modules.condominios import aprovacao_service
from app.modules.unidades import repository
from app.modules.unidades.models import SolicitacaoVinculoUnidade
from app.modules.unidades.schemas import SolicitarVinculoUnidadeRequest
from app.modules.usuarios.models import Usuario


def _exigir_administracao(
    session: Session, *, administrador: Usuario, condominio_id: uuid.UUID | None
) -> uuid.UUID:
    if (
        condominio_id is None
        or repository.obter_vinculo_administracao(
            session, usuario_id=administrador.id, condominio_id=condominio_id
        )
        is None
    ):
        raise ApiError(
            403,
            "forbidden",
            "Apenas a Administração ativa do condomínio pode decidir solicitações.",
        )
    return condominio_id


def solicitar_vinculo(
    session: Session,
    *,
    morador: Usuario,
    dados: SolicitarVinculoUnidadeRequest,
    ip: str | None,
) -> dict[str, Any]:
    try:
        condominio = aprovacao_service.consumir_chave(session, codigo=dados.chave_acesso)
        unidade = repository.obter_unidade(
            session,
            condominio_id=condominio.id,
            bloco=dados.bloco,
            identificacao=dados.unidade,
        )
        if unidade is None:
            raise ApiError(404, "not_found", "Bloco ou unidade não encontrado neste condomínio.")

        vinculo = repository.obter_vinculo_morador(
            session, usuario_id=morador.id, condominio_id=condominio.id, lock=True
        )
        if vinculo is None:
            raise ApiError(
                403,
                "forbidden",
                "A conta não possui cadastro de morador neste condomínio.",
            )
        if vinculo.ativo or vinculo.unidade_id is not None:
            raise ApiError(409, "conflict", "O morador já possui vínculo ativo com uma unidade.")
        solicitacao = SolicitacaoVinculoUnidade(
            id=uuid.uuid4(),
            usuario_id=morador.id,
            condominio_id=condominio.id,
            unidade_id=unidade.id,
            status="pendente",
            responsavel_principal=dados.responsavel_principal,
        )
        session.add(solicitacao)
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
            recurso="vinculo_morador_unidade",
            recurso_id=str(solicitacao.id),
            usuario_id=morador.id,
            ator=morador.nome,
            perfil="morador",
            condominio_id=condominio.id,
            ip=ip,
            dados_depois={
                "status": "pendente",
                "unidade_id": str(unidade.id),
                "responsavel_principal": dados.responsavel_principal,
            },
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(
            409,
            "conflict",
            "Já existe uma solicitação pendente ou vínculo aprovado para este condomínio.",
        ) from erro
    except Exception:
        session.rollback()
        raise

    return {
        "solicitacao_id": solicitacao.id,
        "status": solicitacao.status,
        "condominio_id": condominio.id,
        "unidade_id": unidade.id,
        "responsavel_principal": solicitacao.responsavel_principal,
    }


def listar_pendentes(
    session: Session, *, administrador: Usuario, condominio_id: uuid.UUID | None
) -> list[dict[str, Any]]:
    id_condominio = _exigir_administracao(
        session, administrador=administrador, condominio_id=condominio_id
    )
    return [
        {
            "id": solicitacao.id,
            "morador_nome": morador.nome,
            "morador_email": morador.email,
            "bloco": bloco.nome,
            "unidade": unidade.identificacao,
            "responsavel_principal": solicitacao.responsavel_principal,
            "solicitado_em": solicitacao.solicitado_em,
        }
        for solicitacao, morador, unidade, bloco in repository.listar_pendentes(
            session, condominio_id=id_condominio
        )
    ]


def aprovar_vinculo(
    session: Session,
    *,
    solicitacao_id: uuid.UUID,
    administrador: Usuario,
    condominio_id: uuid.UUID | None,
    nome_responsavel: str,
    ip: str | None,
) -> dict[str, Any]:
    id_condominio = _exigir_administracao(
        session, administrador=administrador, condominio_id=condominio_id
    )
    solicitacao = repository.obter_solicitacao(session, solicitacao_id, lock=True)
    if solicitacao is None or solicitacao.condominio_id != id_condominio:
        raise ApiError(404, "not_found", "Solicitação de vínculo não encontrada.")
    if solicitacao.status != "pendente":
        raise ApiError(409, "conflict", "A solicitação já foi decidida.")

    vinculo = repository.obter_vinculo_morador(
        session,
        usuario_id=solicitacao.usuario_id,
        condominio_id=solicitacao.condominio_id,
        lock=True,
    )
    if vinculo is None or vinculo.ativo or vinculo.unidade_id is not None:
        raise ApiError(409, "conflict", "O vínculo do morador não está disponível para aprovação.")
    if solicitacao.responsavel_principal and repository.obter_principal_aprovado(
        session, unidade_id=solicitacao.unidade_id, exceto_id=solicitacao.id
    ):
        raise ApiError(409, "conflict", "A unidade já possui um responsável principal.")

    agora = datetime.now(UTC)
    status_antes = solicitacao.status
    solicitacao.status = "aprovado"
    solicitacao.decidido_em = agora
    solicitacao.decidido_por_usuario_id = administrador.id
    vinculo.unidade_id = solicitacao.unidade_id
    vinculo.ativo = True
    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
            recurso="vinculo_morador_unidade",
            recurso_id=str(solicitacao.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="administracao",
            condominio_id=id_condominio,
            ip=ip,
            nome_responsavel=nome_responsavel,
            dados_antes={"status": status_antes},
            dados_depois={
                "status": "aprovado",
                "unidade_id": str(solicitacao.unidade_id),
                "responsavel_principal": solicitacao.responsavel_principal,
            },
        )
        _registrar_notificacao(
            session,
            solicitacao=solicitacao,
            administrador=administrador,
            nome_responsavel=nome_responsavel,
            ip=ip,
            status="aprovado",
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        raise ApiError(409, "conflict", "Não foi possível aprovar o vínculo.") from erro
    except Exception:
        session.rollback()
        raise
    return {
        "solicitacao_id": solicitacao.id,
        "status": solicitacao.status,
        "motivo_rejeicao": None,
        "responsavel_principal": solicitacao.responsavel_principal,
        "notificacao_registrada": True,
    }


def rejeitar_vinculo(
    session: Session,
    *,
    solicitacao_id: uuid.UUID,
    administrador: Usuario,
    condominio_id: uuid.UUID | None,
    motivo: str,
    nome_responsavel: str,
    ip: str | None,
) -> dict[str, Any]:
    id_condominio = _exigir_administracao(
        session, administrador=administrador, condominio_id=condominio_id
    )
    solicitacao = repository.obter_solicitacao(session, solicitacao_id, lock=True)
    if solicitacao is None or solicitacao.condominio_id != id_condominio:
        raise ApiError(404, "not_found", "Solicitação de vínculo não encontrada.")
    if solicitacao.status != "pendente":
        raise ApiError(409, "conflict", "A solicitação já foi decidida.")

    agora = datetime.now(UTC)
    status_antes = solicitacao.status
    solicitacao.status = "rejeitado"
    solicitacao.motivo_rejeicao = motivo
    solicitacao.decidido_em = agora
    solicitacao.decidido_por_usuario_id = administrador.id
    try:
        session.flush()
        audit.log(
            session,
            tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
            recurso="vinculo_morador_unidade",
            recurso_id=str(solicitacao.id),
            usuario_id=administrador.id,
            ator=administrador.nome,
            perfil="administracao",
            condominio_id=id_condominio,
            ip=ip,
            nome_responsavel=nome_responsavel,
            dados_antes={"status": status_antes},
            dados_depois={"status": "rejeitado", "motivo": motivo},
        )
        _registrar_notificacao(
            session,
            solicitacao=solicitacao,
            administrador=administrador,
            nome_responsavel=nome_responsavel,
            ip=ip,
            status="rejeitado",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {
        "solicitacao_id": solicitacao.id,
        "status": solicitacao.status,
        "motivo_rejeicao": solicitacao.motivo_rejeicao,
        "responsavel_principal": solicitacao.responsavel_principal,
        "notificacao_registrada": True,
    }


def _registrar_notificacao(
    session: Session,
    *,
    solicitacao: SolicitacaoVinculoUnidade,
    administrador: Usuario,
    nome_responsavel: str,
    ip: str | None,
    status: str,
) -> None:
    audit.log(
        session,
        tipo_evento=TipoEventoAuditoria.NOTIFICACAO_CONDOMINIO,
        recurso="notificacao_vinculo_unidade",
        recurso_id=str(solicitacao.id),
        usuario_id=administrador.id,
        ator=administrador.nome,
        perfil="administracao",
        condominio_id=solicitacao.condominio_id,
        ip=ip,
        nome_responsavel=nome_responsavel,
        dados_depois={
            "destinatario_usuario_id": str(solicitacao.usuario_id),
            "status": status,
        },
    )
