from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.tempo import Relogio, agora
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria
from app.modules.condominios import repository
from app.modules.condominios.schemas import (
    CadastroCondominio,
    CadastroCondominioSaida,
    CondominioResumo,
)
from app.modules.usuarios.models import Usuario


def exigir_administracao(usuario: Usuario) -> None:
    # Tipo da conta no banco; não depende do perfil/cid declarado no token.
    if usuario.tipo_cadastro != "administracao" or usuario.administrador_plataforma:
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")


def cadastrar(
    session: Session,
    usuario: Usuario,
    dados: CadastroCondominio,
    *,
    ip: str | None,
    relogio: Relogio = agora,
) -> CadastroCondominioSaida:
    exigir_administracao(usuario)
    if dados.logo_arquivo_id is not None or dados.documentos:
        # Upload atual exige condomínio existente. Não reaproveitar arquivos de outro
        # condomínio nem alterar seu escopo para contornar o bootstrap.
        raise ApiError(
            422,
            "validation_error",
            "Logo e documentos dependem de upload para o cadastro inicial.",
            reason="arquivos_indisponiveis_no_cadastro",
        )
    momento = relogio()
    try:
        condominio = repository.criar_condominio(
            session, dados, usuario_id=usuario.id, momento=momento
        )
        estrutura = repository.criar_estrutura(
            session, condominio_id=condominio.id, dados=dados.blocos
        )
        repository.vincular_criador(session, condominio_id=condominio.id, usuario_id=usuario.id)
        repository.registrar_envio(
            session, condominio_id=condominio.id, usuario_id=usuario.id, momento=momento
        )
        auditoria.registrar_acao(
            session,
            # Cadastro global autenticado, sem um papel local previamente selecionado.
            # A lista de responsáveis desse condomínio ainda não existe.
            ctx=ContextoAuditoria(usuario_id=usuario.id, condominio_id=condominio.id, ip=ip),
            acao="condominio.enviar",
            recurso_tipo="condominio",
            recurso_id=condominio.id,
            antes={},
            depois={"status": "pendente", "estrutura": estrutura.model_dump()},
        )
        saida = CadastroCondominioSaida(
            id=condominio.id,
            nome=condominio.nome,
            cnpj=dados.cnpj,
            status="pendente",
            enviado_em=momento,
            estrutura=estrutura,
        )
        session.commit()
    except IntegrityError as erro:
        session.rollback()
        if (
            getattr(getattr(erro.orig, "diag", None), "constraint_name", None)
            == "uq_condominios_cnpj"
        ):
            raise ApiError(
                409,
                "conflict",
                "Já existe um condomínio com este CNPJ.",
                reason="cnpj_ja_cadastrado",
            ) from erro
        raise
    except Exception:
        session.rollback()
        raise
    return saida


def listar_meus(session: Session, usuario: Usuario) -> list[CondominioResumo]:
    exigir_administracao(usuario)
    return [
        CondominioResumo(id=item.id, nome=item.nome, status=item.status)
        for item in repository.listar_da_administracao(session, usuario.id)
    ]
