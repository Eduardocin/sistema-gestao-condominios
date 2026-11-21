"""Contas são globais; a edição recebe exclusivamente o ID da identidade autenticada."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.modules.usuarios.models import TokenRecuperacaoSenha, Usuario


def campo_em_uso(
    session: Session, campo: str, valor: str, *, exceto_usuario_id: uuid.UUID | None = None
) -> bool:
    coluna = {"email": Usuario.email, "telefone": Usuario.telefone, "documento": Usuario.documento}[
        campo
    ]
    consulta = select(Usuario.id).where(coluna == valor)
    if exceto_usuario_id is not None:
        consulta = consulta.where(Usuario.id != exceto_usuario_id)
    return session.scalar(consulta.limit(1)) is not None


def bloquear_conta(session: Session, usuario_id: uuid.UUID) -> Usuario:
    usuario = session.scalar(
        select(Usuario)
        .where(Usuario.id == usuario_id, Usuario.ativo.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None:
        raise ApiError(
            401,
            "not_authenticated",
            "Sessão inválida ou expirada. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def atualizar_conta(
    session: Session, usuario: Usuario, *, nome: str, email: str, telefone: str
) -> None:
    usuario.nome = nome
    usuario.email = email
    usuario.telefone = telefone
    session.flush()


def gravar_senha(session: Session, usuario: Usuario, senha_hash: str) -> None:
    """Troca o hash e soma 1 em `sessao_versao`: todos os tokens emitidos antes caem (claim sv).

    Quem chama já travou a linha (`bloquear_conta` ou `obter_conta_travada`).
    """
    usuario.senha_hash = senha_hash
    usuario.sessao_versao += 1
    session.flush()


def obter_conta_travada(session: Session, usuario_id: uuid.UUID) -> Usuario | None:
    """A conta, ativa ou não, com a linha travada. Quem decide se ela serve é o service."""
    return session.scalar(
        select(Usuario)
        .where(Usuario.id == usuario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def consumir_token_recuperacao(session: Session, token_hash: str) -> uuid.UUID | None:
    """Marca o token como usado e devolve o dono, num único UPDATE condicional.

    Dois pedidos simultâneos com o mesmo token não passam juntos: o segundo espera o primeiro e,
    depois do commit dele, já não encontra `usado_em IS NULL`. Se a transação for desfeita, o
    token volta a valer.
    """
    return session.scalar(
        update(TokenRecuperacaoSenha)
        .where(
            TokenRecuperacaoSenha.token_hash == token_hash,
            TokenRecuperacaoSenha.usado_em.is_(None),
            TokenRecuperacaoSenha.expira_em > func.now(),
        )
        .values(usado_em=func.now())
        .returning(TokenRecuperacaoSenha.usuario_id)
    )


def inutilizar_tokens_pendentes(session: Session, usuario_id: uuid.UUID) -> None:
    """Outros links de recuperação ainda abertos da conta deixam de valer."""
    session.execute(
        update(TokenRecuperacaoSenha)
        .where(
            TokenRecuperacaoSenha.usuario_id == usuario_id,
            TokenRecuperacaoSenha.usado_em.is_(None),
        )
        .values(usado_em=func.now())
    )
