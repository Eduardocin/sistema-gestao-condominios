"""Corpo binário limitado; metadados persistidos e leitura por URL assinada curta."""

import io
import logging
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import ApiError, RecursoNaoEncontrado
from app.db.session import get_session
from app.modules.auth.dependencies import (
    ContextoDep,
    UsuarioAutenticado,
    get_current_context,
    get_usuario_autenticado,
)
from app.modules.storage.models import Arquivo
from app.modules.storage.policy import autorizar_download, autorizar_upload
from app.modules.storage.repository import obter_para_download
from app.modules.storage.s3 import S3Adapter
from app.modules.storage.service import StorageService
from app.modules.storage.types import (
    MODULES,
    AuthorizationPolicy,
    FileMetadata,
    Module,
    StorageAdapter,
    StorageContext,
    StorageError,
    StorageNotFound,
    StorageValidationError,
)
from app.modules.storage.validation import IMAGE_LIMIT, VIDEO_LIMIT

router = APIRouter(prefix="/arquivos", tags=["arquivos"])
logger = logging.getLogger(__name__)
SessionDep = Annotated[Session, Depends(get_session)]
UsuarioDep = Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)]


def get_storage_adapter() -> StorageAdapter:
    return S3Adapter(get_settings())


AdapterDep = Annotated[StorageAdapter, Depends(get_storage_adapter)]


class UploadQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str = Field(min_length=1, max_length=255)
    unidade_id: UUID | None = None


class ArquivoOut(BaseModel):
    id: UUID
    nome_original: str
    tipo_mime: str
    tamanho_bytes: int
    criado_em: datetime
    download_url: str


class DownloadOut(BaseModel):
    url: str
    expires_in: int


def _service(adapter: StorageAdapter, policy: AuthorizationPolicy) -> StorageService:
    return StorageService(adapter, authorize=policy, url_seconds=get_settings().storage_url_seconds)


def _erro(error: StorageError) -> ApiError:
    if isinstance(error, StorageNotFound):
        return ApiError(404, "not_found", "Recurso não encontrado.")
    if isinstance(error, StorageValidationError):
        return ApiError(422, "validation_error", str(error))
    return ApiError(503, "storage_unavailable", "Armazenamento temporariamente indisponível.")


@router.post("/{modulo}", status_code=201, response_model=ArquivoOut)
async def upload(
    modulo: Module,
    request: Request,
    response: Response,
    contexto: ContextoDep,
    dados: Annotated[UploadQuery, Query()],
    session: SessionDep,
    adapter: AdapterDep,
) -> ArquivoOut:
    await run_in_threadpool(autorizar_upload, session, contexto, modulo, dados.unidade_id)
    mime = request.headers.get("content-type", "").split(";", 1)[0].strip()
    limite = VIDEO_LIMIT if modulo == "ocorrencias" and mime == "video/mp4" else IMAGE_LIMIT
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limite:
            raise ApiError(422, "validation_error", "Arquivo excede o tamanho permitido.")
        content.extend(chunk)

    def persistir() -> ArquivoOut:
        uploaded_id: UUID | None = None

        def policy(ctx, module, action, file):
            if action == "remove":
                # Só compensamos este objeto recém-criado. A autorização não pode
                # depender de uma nova consulta ao banco que acabou de falhar.
                if file is None or file.id != uploaded_id:
                    raise StorageNotFound("Arquivo indisponível.")
                return
            autorizar_upload(session, contexto, module, dados.unidade_id)
            if file is not None and file.enviado_por_usuario_id != contexto.usuario_id:
                raise RecursoNaoEncontrado

        storage = _service(adapter, policy)
        ctx = StorageContext(contexto.condominio_id, contexto.usuario_id)
        try:
            file = storage.upload(ctx, modulo, dados.nome, mime, io.BytesIO(content))
            uploaded_id = file.id
        except StorageError as error:
            raise _erro(error) from None
        arquivo = Arquivo(
            id=file.id,
            condominio_id=file.condominio_id,
            chave_storage=file.chave_storage,
            nome_original=file.nome_original,
            tipo_mime=file.tipo_mime,
            tamanho_bytes=file.tamanho_bytes,
            enviado_por_usuario_id=file.enviado_por_usuario_id,
            criado_em=file.criado_em,
        )
        try:
            session.add(arquivo)
            session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                logger.error("Falha no rollback do upload: arquivo_id=%s", file.id)
            try:
                storage.remove(ctx, file)
            except Exception:
                logger.error("Falha na compensação de upload: arquivo_id=%s", file.id)
            raise
        location = f"/api/v1/arquivos/{file.id}/download"
        response.headers["Location"] = location
        return ArquivoOut(
            id=file.id,
            nome_original=file.nome_original,
            tipo_mime=file.tipo_mime,
            tamanho_bytes=file.tamanho_bytes,
            criado_em=file.criado_em,
            download_url=location,
        )

    return await run_in_threadpool(persistir)


@router.get("/{arquivo_id}/download", response_model=DownloadOut)
def download(
    arquivo_id: UUID,
    autenticado: UsuarioDep,
    session: SessionDep,
    adapter: AdapterDep,
    response: Response,
) -> DownloadOut:
    ctx = None
    if not autenticado.usuario.administrador_plataforma:
        ctx = get_current_context(autenticado, session)
    arquivo = obter_para_download(session, arquivo_id, ctx)
    autorizar_download(session, ctx, arquivo, autenticado.usuario)
    partes = arquivo.chave_storage.split("/")
    if len(partes) != 4 or partes[2] not in MODULES or arquivo.condominio_id is None:
        raise RecursoNaoEncontrado
    file = FileMetadata(
        arquivo.id,
        arquivo.condominio_id,
        cast(Module, partes[2]),
        arquivo.chave_storage,
        arquivo.nome_original,
        arquivo.tipo_mime,
        arquivo.tamanho_bytes,
        arquivo.enviado_por_usuario_id,
        arquivo.criado_em,
    )
    try:
        url = _service(
            adapter, lambda *_: autorizar_download(session, ctx, arquivo, autenticado.usuario)
        ).download_url(
            StorageContext(arquivo.condominio_id, autenticado.usuario.id),
            file,
        )
    except StorageError as error:
        raise _erro(error) from None
    response.headers["Cache-Control"] = "no-store"
    return DownloadOut(url=url, expires_in=get_settings().storage_url_seconds)
