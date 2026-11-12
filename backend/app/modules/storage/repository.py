"""Consultas de metadados com escopo explícito antes da política de recurso."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio
from app.core.errors import RecursoNaoEncontrado
from app.db.repositorio import RepositorioDoCondominio
from app.modules.condominios.models import CondominioDocumento
from app.modules.storage.models import Arquivo
from app.modules.suporte.models import ChamadoAnexo


class RepositorioArquivos(RepositorioDoCondominio[Arquivo]):
    modelo = Arquivo


def obter_para_download(
    session: Session, arquivo_id: UUID, contexto: ContextoCondominio | None
) -> Arquivo:
    if contexto is not None:
        return RepositorioArquivos(session, contexto).obter(arquivo_id)
    # Exceção estreita do ADM: apenas documentos e anexos de suporte vinculados.
    documento = (
        select(CondominioDocumento.arquivo_id)
        .where(
            CondominioDocumento.arquivo_id == Arquivo.id,
            CondominioDocumento.condominio_id == Arquivo.condominio_id,
        )
        .exists()
    )
    suporte = (
        select(ChamadoAnexo.arquivo_id)
        .where(
            ChamadoAnexo.arquivo_id == Arquivo.id,
            ChamadoAnexo.condominio_id == Arquivo.condominio_id,
        )
        .exists()
    )
    arquivo = session.scalar(
        select(Arquivo).where(Arquivo.id == arquivo_id, or_(documento, suporte))
    )
    if arquivo is None:
        raise RecursoNaoEncontrado
    return arquivo
