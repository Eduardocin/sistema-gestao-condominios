from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.modules.auth.security import hash_senha
from app.modules.auth.service import SessaoEmitida, emitir_sessao_do_usuario
from app.modules.contas import repository
from app.modules.contas.schemas import CadastroAdministracao, CadastroConta
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
