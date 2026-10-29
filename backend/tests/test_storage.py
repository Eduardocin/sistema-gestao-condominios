import io
from dataclasses import replace
from uuid import uuid4

import pytest
from PIL import Image

from app.modules.storage.service import StorageService
from app.modules.storage.types import (
    StorageContext,
    StorageError,
    StorageNotFound,
    StorageValidationError,
)


def png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(stream, format="PNG")
    return stream.getvalue()


class MemoryAdapter:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.fail = False

    def put(self, key, data, content_type):
        self.calls.append(("put", key))
        if self.fail:
            raise OSError("secret credential and internal endpoint")
        self.objects[key] = data

    def sign(self, key, seconds):
        self.calls.append(("sign", key))
        return f"http://localhost:9000/private/{key}?expires={seconds}"

    def remove(self, key):
        self.calls.append(("remove", key))
        self.objects.pop(key, None)


@pytest.fixture
def storage():
    adapter = MemoryAdapter()
    context = StorageContext(condominio_id=uuid4(), usuario_id=uuid4())
    decisions = []

    def authorize(ctx, module, action, file):
        decisions.append(action)

    return StorageService(adapter, authorize=authorize), adapter, context, decisions


def upload(service, ctx, data=None, filename="foto.png", mime="image/png", module="encomendas"):
    return service.upload(ctx, module, filename, mime, io.BytesIO(png() if data is None else data))


def test_upload_returns_metadata_and_generated_tenant_key(storage):
    service, adapter, ctx, decisions = storage
    file = upload(service, ctx)
    assert file.condominio_id == ctx.condominio_id
    assert file.enviado_por_usuario_id == ctx.usuario_id
    assert file.chave_storage == f"condominio/{ctx.condominio_id}/encomendas/{file.id}"
    assert file.nome_original == "foto.png"
    assert file.tipo_mime == "image/png"
    assert file.tamanho_bytes == len(png())
    assert adapter.objects[file.chave_storage] == png()
    assert decisions == ["upload"]


@pytest.mark.parametrize("action", ["download", "remove"])
def test_other_condominium_is_denied_before_policy_or_s3(storage, action):
    service, adapter, ctx, decisions = storage
    file = upload(service, ctx)
    adapter.calls.clear()
    decisions.clear()
    other = StorageContext(condominio_id=uuid4(), usuario_id=uuid4())
    operation = service.download_url if action == "download" else service.remove
    with pytest.raises(StorageNotFound, match="Arquivo indisponível"):
        operation(other, file)
    assert adapter.calls == []
    assert decisions == []


@pytest.mark.parametrize("action", ["upload", "download", "remove"])
def test_resource_authorization_is_required_even_in_same_condominium(storage, action):
    service, adapter, ctx, _ = storage
    file = upload(service, ctx)

    def deny(*args):
        raise StorageNotFound("Arquivo indisponível.")

    denied = StorageService(adapter, authorize=deny)
    adapter.calls.clear()
    with pytest.raises(StorageNotFound):
        if action == "upload":
            upload(denied, ctx)
        elif action == "download":
            denied.download_url(ctx, file)
        else:
            denied.remove(ctx, file)
    assert adapter.calls == []


def test_signed_download_and_removal_use_generated_reference(storage):
    service, adapter, ctx, decisions = storage
    file = upload(service, ctx)
    assert service.download_url(ctx, file).endswith("expires=60")
    service.remove(ctx, file)
    assert not adapter.objects
    assert decisions == ["upload", "download", "remove"]


@pytest.mark.parametrize("field,value", [("modulo", "../outro"), ("chave_storage", "outra-chave")])
def test_inconsistent_metadata_never_reaches_s3(storage, field, value):
    service, adapter, ctx, _ = storage
    file = replace(upload(service, ctx), **{field: value})
    adapter.calls.clear()
    with pytest.raises(StorageNotFound):
        service.download_url(ctx, file)
    assert adapter.calls == []


@pytest.mark.parametrize(
    "filename,mime,data,module",
    [
        ("../foto.png", "image/png", b"x", "encomendas"),
        ("C:\\foto.png", "image/png", b"x", "encomendas"),
        ("foto.svg", "image/svg+xml", b"<svg/>", "encomendas"),
        ("foto.png", "image/jpeg", b"x", "encomendas"),
        ("foto.png", "image/png", b"not an image", "encomendas"),
        ("foto.png", "image/png", b"", "encomendas"),
        ("filme.mp4", "video/mp4", b"\x00\x00\x00\x18ftypisom", "encomendas"),
        ("arquivo.pdf", "application/pdf", b"%PDF-1.7\n%%EOF", "encomendas"),
        ("foto.png", "image/png", b"x", "../outro"),
    ],
)
def test_invalid_files_are_rejected_before_upload(storage, filename, mime, data, module):
    service, adapter, ctx, _ = storage
    with pytest.raises(StorageValidationError):
        upload(service, ctx, data, filename, mime, module)
    assert adapter.calls == []


def test_truncated_image_is_rejected(storage):
    service, adapter, ctx, _ = storage
    with pytest.raises(StorageValidationError):
        upload(service, ctx, png()[:40])
    assert not adapter.objects


def test_oversize_upload_reads_only_up_to_limit_plus_one(storage):
    service, adapter, ctx, _ = storage

    class LimitedStream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 5 * 1024 * 1024 + 1
            return super().read(size)

    stream = LimitedStream(b"x" * (5 * 1024 * 1024 + 100))
    with pytest.raises(StorageValidationError, match="tamanho"):
        service.upload(ctx, "encomendas", "foto.png", "image/png", stream)
    assert stream.tell() == 5 * 1024 * 1024 + 1
    assert adapter.calls == []


def test_storage_failure_does_not_expose_internal_exception(storage):
    service, adapter, ctx, _ = storage
    adapter.fail = True
    with pytest.raises(StorageError, match="Armazenamento temporariamente indisponível") as error:
        upload(service, ctx)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("seconds", [0, 301])
def test_signed_url_expiry_has_safe_bounds(storage, seconds):
    _, adapter, _, _ = storage
    with pytest.raises(ValueError):
        StorageService(adapter, authorize=lambda *args: None, url_seconds=seconds)


def test_uncertain_upload_failure_cleans_only_the_new_object(storage):
    service, adapter, ctx, _ = storage
    previous = upload(service, ctx)

    def interrupted_put(key, data, content_type):
        adapter.objects[key] = data
        raise OSError("connection lost after object was stored")

    adapter.put = interrupted_put
    with pytest.raises(StorageError):
        upload(service, ctx)
    assert list(adapter.objects) == [previous.chave_storage]


def test_png_bad_checksum_is_validation_error_before_s3(storage):
    service, adapter, ctx, _ = storage
    corrupted = bytearray(png())
    corrupted[corrupted.index(b"IDAT") + 4] ^= 1
    with pytest.raises(StorageValidationError):
        upload(service, ctx, bytes(corrupted))
    assert adapter.calls == []
