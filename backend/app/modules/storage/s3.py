import io
from datetime import timedelta
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings


class S3Adapter:
    def __init__(self, settings: Settings):
        self.bucket = settings.storage_bucket
        self.client = self._client(settings.storage_endpoint, settings)
        self.signer = self._client(settings.storage_public_endpoint, settings)

    @staticmethod
    def _client(endpoint: str, settings: Settings) -> Minio:
        parsed = urlsplit(endpoint)
        return Minio(
            parsed.netloc,
            access_key=settings.storage_access_key.get_secret_value(),
            secret_key=settings.storage_secret_key.get_secret_value(),
            secure=parsed.scheme == "https",
            region=settings.storage_region,
        )

    def ensure_private_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        # O bucket da aplicação não usa política anônima, mesmo em reinicializações.
        try:
            self.client.delete_bucket_policy(self.bucket)
        except S3Error as error:
            if error.code != "NoSuchBucketPolicy":
                raise

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            self.bucket, key, io.BytesIO(data), len(data), content_type=content_type
        )

    def sign(self, key: str, seconds: int) -> str:
        return self.signer.get_presigned_url(
            "GET",
            self.bucket,
            key,
            expires=timedelta(seconds=seconds),
            response_headers={"response-content-disposition": "attachment"},
        )

    def remove(self, key: str) -> None:
        self.client.remove_object(self.bucket, key)
