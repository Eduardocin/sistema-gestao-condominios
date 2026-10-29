from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

Module = Literal["encomendas", "ocorrencias", "suporte", "fotos"]
Action = Literal["upload", "download", "remove"]
MODULES = frozenset(("encomendas", "ocorrencias", "suporte", "fotos"))


class StorageError(Exception):
    """Erro de infraestrutura, sem detalhes internos na mensagem pública."""


class StorageNotFound(StorageError):
    """Referência inexistente ou fora do escopo autorizado (futuro HTTP 404)."""


class StorageValidationError(StorageError):
    """Arquivo inválido (futuro HTTP 422)."""


@dataclass(frozen=True)
class StorageContext:
    condominio_id: UUID
    usuario_id: UUID


@dataclass(frozen=True)
class FileMetadata:
    id: UUID
    condominio_id: UUID
    modulo: Module
    chave_storage: str
    nome_original: str
    tipo_mime: str
    tamanho_bytes: int
    enviado_por_usuario_id: UUID
    criado_em: datetime


class StorageAdapter(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def sign(self, key: str, seconds: int) -> str: ...
    def remove(self, key: str) -> None: ...


class AuthorizationPolicy(Protocol):
    def __call__(
        self, ctx: StorageContext, module: Module, action: Action, file: FileMetadata | None
    ) -> None:
        """Negar por exceção. A política deve validar o recurso e a ação do chamador."""
        ...
