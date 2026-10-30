"""Integração real: definir TEST_STORAGE_ENDPOINT em um MinIO dedicado a testes."""

import os
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.storage.s3 import S3Adapter
from app.modules.storage.service import StorageService
from app.modules.storage.types import StorageContext, StorageNotFound
from tests.test_storage import png, upload

pytestmark = pytest.mark.storage


def test_real_minio_private_upload_public_signature_and_delete():
    endpoint = os.getenv("TEST_STORAGE_ENDPOINT")
    if not endpoint:
        pytest.skip("Defina TEST_STORAGE_ENDPOINT para um MinIO dedicado a testes")
    settings = Settings(
        _env_file=None,
        storage_endpoint=endpoint,
        storage_public_endpoint=os.getenv("TEST_STORAGE_PUBLIC_ENDPOINT", endpoint),
        storage_access_key=os.environ["TEST_STORAGE_ACCESS_KEY"],
        storage_secret_key=os.environ["TEST_STORAGE_SECRET_KEY"],
        storage_bucket=f"teste-{uuid4().hex}",
    )
    adapter = S3Adapter(settings)
    adapter.ensure_private_bucket()
    adapter.ensure_private_bucket()
    service = StorageService(adapter, authorize=lambda *args: None)
    ctx = StorageContext(uuid4(), uuid4())
    file = upload(service, ctx)
    try:
        url = service.download_url(ctx, file)
        assert url.startswith(str(settings.storage_public_endpoint).rstrip("/") + "/")
        with urlopen(url, timeout=10) as response:
            assert response.read() == png()
        anonymous = url.split("?")[0]
        with pytest.raises(HTTPError) as denied:
            urlopen(anonymous, timeout=10)
        assert denied.value.code == 403
        with pytest.raises(StorageNotFound):
            service.download_url(StorageContext(uuid4(), uuid4()), file)
        service.remove(ctx, file)
        with pytest.raises(HTTPError) as missing:
            urlopen(url, timeout=10)
        assert missing.value.code == 404
    finally:
        adapter.remove(file.chave_storage)
        adapter.client.remove_bucket(settings.storage_bucket)
