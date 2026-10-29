import io
import struct
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from app.core.config import Settings
from app.modules.storage.s3 import S3Adapter
from app.modules.storage.validation import validate_file


@pytest.mark.parametrize(
    "suffix,mime,format",
    [
        ("jpg", "image/jpeg", "JPEG"),
        ("png", "image/png", "PNG"),
        ("webp", "image/webp", "WEBP"),
    ],
)
def test_supported_images_are_decoded(suffix, mime, format):
    data = io.BytesIO()
    Image.new("RGB", (3, 3)).save(data, format=format)
    content = data.getvalue()
    assert validate_file("fotos", f"foto.{suffix}", mime, io.BytesIO(content)) == content


def test_support_pdf_accepts_signature_and_end_marker():
    content = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    assert validate_file("suporte", "anexo.pdf", "application/pdf", io.BytesIO(content)) == content


def test_video_accepts_container_with_zero_size_final_mdat():
    # Boxes sintéticos testam só o contêiner; não representam um vídeo decodificável.
    content = struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0)
    content += struct.pack(">I4s", 8, b"moov")
    content += struct.pack(">I4s", 0, b"mdat") + b"video-data"
    assert validate_file("ocorrencias", "video.mp4", "video/mp4", io.BytesIO(content)) == content


def test_signing_uses_public_host_region_and_expiry_without_network():
    settings = Settings(
        _env_file=None,
        storage_endpoint="http://internal.invalid:9000",
        storage_public_endpoint="https://public.invalid:9443",
    )
    adapter = S3Adapter(settings)
    url = urlsplit(adapter.sign("condominio/teste/encomendas/arquivo", 120))
    assert url.netloc == "public.invalid:9443"
    query = parse_qs(url.query)
    assert query["X-Amz-Expires"] == ["120"]
    assert "us-east-1" in query["X-Amz-Credential"][0]
    assert query["response-content-disposition"] == ["attachment"]
