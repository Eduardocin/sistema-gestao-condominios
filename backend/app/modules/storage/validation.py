import io
import struct
import warnings
from pathlib import PurePosixPath
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from app.modules.storage.types import MODULES, Module, StorageValidationError

IMAGE_LIMIT = 5 * 1024 * 1024
VIDEO_LIMIT = 50 * 1024 * 1024
FORMATS = {
    ".jpg": ("image/jpeg", "JPEG"),
    ".jpeg": ("image/jpeg", "JPEG"),
    ".png": ("image/png", "PNG"),
    ".webp": ("image/webp", "WEBP"),
}


def validate_file(module: Module, filename: str, content_type: str, stream: BinaryIO) -> bytes:
    if module not in MODULES:
        raise StorageValidationError("Módulo de arquivo inválido.")
    if (
        not filename
        or len(filename) > 255
        or filename != filename.strip()
        or any(c in filename for c in "/\\:\x00\r\n")
        or filename in {".", ".."}
    ):
        raise StorageValidationError("Nome de arquivo inválido.")
    suffix = PurePosixPath(filename).suffix.lower()
    image = FORMATS.get(suffix)
    pdf = module == "suporte" and suffix == ".pdf" and content_type == "application/pdf"
    video = module == "ocorrencias" and suffix == ".mp4" and content_type == "video/mp4"
    if not ((image and image[0] == content_type) or pdf or video):
        raise StorageValidationError("Tipo de arquivo não permitido neste módulo.")
    limit = VIDEO_LIMIT if video else IMAGE_LIMIT
    data = bytearray()
    while len(data) <= limit:
        chunk = stream.read(min(65536, limit + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > limit:
        raise StorageValidationError("Arquivo excede o tamanho permitido.")
    if not data:
        raise StorageValidationError("Arquivo vazio.")
    content = bytes(data)
    if image:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as decoded:
                    if decoded.format != image[1] or decoded.width * decoded.height > 20_000_000:
                        raise ValueError("Formato ou resolução inválida")
                    decoded.verify()
                with Image.open(io.BytesIO(content)) as decoded:
                    decoded.load()
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise StorageValidationError("Imagem inválida ou corrompida.") from exc
    elif pdf and not (content.startswith(b"%PDF-") and content.rstrip().endswith(b"%%EOF")):
        raise StorageValidationError("Conteúdo PDF inválido.")
    elif video:
        validate_mp4(content)
    return content


def validate_mp4(content: bytes) -> None:
    # Verifica os boxes do contêiner, sem executar ou transcodificar o vídeo.
    offset = 0
    boxes = set()
    while offset + 8 <= len(content):
        size, kind = struct.unpack_from(">I4s", content, offset)
        if size == 0:
            size = len(content) - offset
        if size < 8 or offset + size > len(content):
            raise StorageValidationError("Conteúdo MP4 inválido.")
        if kind == b"ftyp" and (
            size < 16
            or content[offset + 8 : offset + 12]
            not in {b"isom", b"iso2", b"mp41", b"mp42", b"avc1", b"M4V "}
        ):
            raise StorageValidationError("Conteúdo MP4 inválido.")
        boxes.add(kind)
        offset += size
    if offset != len(content) or not {b"ftyp", b"moov", b"mdat"}.issubset(boxes):
        raise StorageValidationError("Conteúdo MP4 inválido.")
