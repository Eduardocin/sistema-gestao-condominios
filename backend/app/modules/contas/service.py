from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.auth.security import hash_senha
from app.modules.auth.service import SessaoEmitida, emitir_sessao_do_usuario
from app.modules.contas import repository
from app.modules.contas.schemas import CadastroAdministracao, CadastroConta, ContaSaida, EdicaoConta
from app.modules.usuarios.models import Usuario


def _conflito(campo: str) -> ApiError:
    return ApiError(
        409, "conflict", "Já existe uma conta com este dado.", reason=f"{campo}_ja_cadastrado"
    )


def cadastrar(
    session: Session,
    dados: CadastroConta,
    tipo: Literal["morador", "administracao"],
    settings: Settings,
    *,
    ip: str | None = None,
) -> SessaoEmitida:
    documento = dados.documento if isinstance(dados, CadastroAdministracao) else None
    valores = {"email": dados.email, "telefone": dados.telefone, "documento": documento}
    for campo, valor in valores.items():
        if valor is not None and repository.campo_em_uso(session, campo, valor):
            raise _conflito(campo)
    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        telefone=dados.telefone,
        documento=documento,
        tipo_cadastro=tipo,
        senha_hash=hash_senha(dados.senha),
    )
    try:
        session.add(usuario)
        session.flush()
        auditoria.registrar_acao(
            session,
            ctx=ContextoAuditoria(usuario_id=usuario.id, ip=ip),
            acao="conta.criar",
            recurso_tipo="usuario",
            recurso_id=usuario.id,
            antes={},
            # Whitelist de saída: nunca inclui senha, hash ou a sessão emitida abaixo.
            depois=ContaSaida.model_validate(usuario).model_dump(exclude={"id"}),
        )
        sessao = emitir_sessao_do_usuario(session, usuario=usuario, settings=settings)
        session.commit()
    except IntegrityError as erro:
        # As constraints também protegem dois cadastros concorrentes do mesmo dado.
        session.rollback()
        for campo, valor in valores.items():
            if valor is not None and repository.campo_em_uso(session, campo, valor):
                raise _conflito(campo) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return sessao


def editar_propria_conta(
    session: Session, usuario: Usuario, dados: EdicaoConta, *, ip: str | None
) -> ContaSaida:
    usuario = repository.bloquear_conta(session, usuario.id)
    # Este recorte trata cadastros globais. Contas compartilhadas não podem trocar seu
    # acesso por esta rota e contornar o responsável e a revogação de sessões da US-210.
    if (
        usuario.tipo_cadastro not in {"morador", "administracao"}
        or usuario.administrador_plataforma
    ):
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")
    if usuario.tipo_cadastro == "morador" and len(dados.nome.split()) < 2:
        raise ApiError(422, "validation_error", "Informe o nome completo.")
    usuario_id = usuario.id
    valores = dados.model_dump()
    for campo in ("email", "telefone"):
        if repository.campo_em_uso(session, campo, valores[campo], exceto_usuario_id=usuario_id):
            raise _conflito(campo)
    antes = {
        campo: getattr(usuario, campo)
        for campo in valores
        if getattr(usuario, campo) != valores[campo]
    }
    depois = {campo: valores[campo] for campo in antes}
    try:
        repository.atualizar_conta(session, usuario, **valores)
        auditoria.registrar_acao(
            session,
            # Operação global de conta própria, mesmo quando o JWT contém um cid.
            # Tipo de cadastro não é perfil de condomínio; não inventamos vínculo/responsável.
            ctx=ContextoAuditoria(usuario_id=usuario_id, ip=ip),
            acao="conta.editar",
            recurso_tipo="usuario",
            recurso_id=usuario_id,
            antes=antes,
            depois=depois,
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        for campo in ("email", "telefone"):
            if repository.campo_em_uso(
                session, campo, valores[campo], exceto_usuario_id=usuario_id
            ):
                raise _conflito(campo) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return ContaSaida.model_validate(usuario)
