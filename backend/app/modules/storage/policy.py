"""Permissão de arquivo segue o recurso vinculado, nunca apenas o condomínio."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auth import repository
from app.modules.auth.autorizacao import garantir_acesso_a_unidade
from app.modules.condominios.models import CondominioDocumento
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.ocorrencias.models import Ocorrencia, OcorrenciaAnexo
from app.modules.storage.models import Arquivo
from app.modules.storage.types import Module
from app.modules.suporte.models import ChamadoAnexo
from app.modules.usuarios.models import Usuario


def conferir_unidade(session: Session, ctx: ContextoCondominio, unidade_id: UUID, aba: str) -> None:
    garantir_acesso_a_unidade(session, ctx, unidade_id)
    if ctx.perfil == "morador" and not repository.morador_tem_acesso_a_aba(
        session,
        usuario_id=ctx.usuario_id,
        condominio_id=ctx.condominio_id,
        unidade_id=unidade_id,
        aba=aba,
    ):
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")


def autorizar_upload(
    session: Session, ctx: ContextoCondominio, modulo: Module, unidade_id: UUID | None
) -> None:
    perfis = {
        "encomendas": {"funcionario"},
        "ocorrencias": {"morador", "administracao"},
        "suporte": {"administracao"},
        "fotos": {"administracao"},
    }
    if ctx.perfil not in perfis[modulo]:
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")
    if ctx.perfil == "morador" and unidade_id is None:
        raise ApiError(422, "validation_error", "Informe a unidade do anexo.")
    if unidade_id is not None:
        conferir_unidade(session, ctx, unidade_id, "ocorrencias")


def autorizar_download(
    session: Session, ctx: ContextoCondominio | None, arquivo: Arquivo, usuario: Usuario
) -> None:
    id = arquivo.id
    condominio = arquivo.condominio_id
    encomendas = list(
        session.scalars(
            select(Encomenda.unidade_id).where(
                Encomenda.foto_nota_arquivo_id == id,
                Encomenda.condominio_id == condominio,
            )
        )
    )
    ocorrencias = list(
        session.scalars(
            select(Ocorrencia.unidade_id)
            .join(
                OcorrenciaAnexo,
                OcorrenciaAnexo.ocorrencia_id == Ocorrencia.id,
            )
            .where(
                OcorrenciaAnexo.arquivo_id == id,
                Ocorrencia.condominio_id == condominio,
                OcorrenciaAnexo.condominio_id == condominio,
            )
        )
    )
    suporte = (
        session.scalar(
            select(ChamadoAnexo.arquivo_id).where(
                ChamadoAnexo.arquivo_id == id,
                ChamadoAnexo.condominio_id == condominio,
            )
        )
        is not None
    )
    documento = (
        session.scalar(
            select(CondominioDocumento.arquivo_id).where(
                CondominioDocumento.arquivo_id == id,
                CondominioDocumento.condominio_id == condominio,
            )
        )
        is not None
    )
    foto = (
        session.scalar(
            select(Funcionario.id).where(
                Funcionario.foto_arquivo_id == id,
                Funcionario.condominio_id == condominio,
            )
        )
        is not None
    )
    foto_usuario = session.scalar(select(Usuario.id).where(Usuario.foto_arquivo_id == id))
    if usuario.administrador_plataforma:
        if suporte or documento:
            return
        raise RecursoNaoEncontrado
    if ctx is None or condominio != ctx.condominio_id:
        raise RecursoNaoEncontrado
    if ctx.perfil == "administracao" and (
        encomendas or ocorrencias or suporte or documento or foto
    ):
        return
    if ctx.perfil == "funcionario" and encomendas:
        return
    if ctx.perfil == "morador":
        for unidades, aba in ((encomendas, "encomendas"), (ocorrencias, "ocorrencias")):
            for unidade_id in unidades:
                try:
                    conferir_unidade(session, ctx, unidade_id, aba)
                except (ApiError, RecursoNaoEncontrado):
                    continue
                return
    # Um upload ainda sem associação só pode ser lido pelo autor. Após o vínculo,
    # a política do recurso substitui esta permissão provisória, inclusive para o autor.
    vinculado = bool(encomendas or ocorrencias or suporte or documento or foto or foto_usuario)
    if not vinculado and arquivo.enviado_por_usuario_id == usuario.id:
        return
    if foto_usuario == usuario.id:
        return
    raise RecursoNaoEncontrado
