import logging
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import uuid4

from app.modules.storage.types import (
    MODULES,
    Action,
    AuthorizationPolicy,
    FileMetadata,
    Module,
    StorageAdapter,
    StorageContext,
    StorageError,
    StorageNotFound,
)
from app.modules.storage.validation import validate_file

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(
        self, adapter: StorageAdapter, *, authorize: AuthorizationPolicy, url_seconds: int = 60
    ):
        if not 1 <= url_seconds <= 300:
            raise ValueError("A URL deve durar de 1 a 300 segundos.")
        self.adapter = adapter
        self.authorize = authorize
        self.url_seconds = url_seconds

    def upload(
        self,
        ctx: StorageContext,
        module: Module,
        filename: str,
        content_type: str,
        stream: BinaryIO,
    ) -> FileMetadata:
        self.authorize(ctx, module, "upload", None)
        content = validate_file(module, filename, content_type, stream)
        identifier = uuid4()
        key = f"condominio/{ctx.condominio_id}/{module}/{identifier}"
        file = FileMetadata(
            identifier,
            ctx.condominio_id,
            module,
            key,
            filename,
            content_type,
            len(content),
            ctx.usuario_id,
            datetime.now(UTC),
        )
        try:
            self.adapter.put(key, content, content_type)
        except Exception:
            # O servidor pode ter gravado antes da falha de conexão. Só este UUID
            # recém-gerado é compensado; não há limpeza por prefixo ou chave do cliente.
            try:
                self.adapter.remove(key)
            except Exception:
                logger.error("Falha na limpeza de upload incompleto: arquivo_id=%s", identifier)
            raise StorageError("Armazenamento temporariamente indisponível.") from None
        return file

    def _check(self, ctx: StorageContext, file: FileMetadata, action: Action) -> None:
        expected_key = f"condominio/{ctx.condominio_id}/{file.modulo}/{file.id}"
        if (
            file.condominio_id != ctx.condominio_id
            or file.modulo not in MODULES
            or file.chave_storage != expected_key
        ):
            raise StorageNotFound("Arquivo indisponível.")
        self.authorize(ctx, file.modulo, action, file)

    def download_url(self, ctx: StorageContext, file: FileMetadata) -> str:
        self._check(ctx, file, "download")
        try:
            return self.adapter.sign(file.chave_storage, self.url_seconds)
        except Exception:
            raise StorageError("Armazenamento temporariamente indisponível.") from None

    def remove(self, ctx: StorageContext, file: FileMetadata) -> None:
        self._check(ctx, file, "remove")
        try:
            self.adapter.remove(file.chave_storage)
        except Exception:
            raise StorageError("Armazenamento temporariamente indisponível.") from None
