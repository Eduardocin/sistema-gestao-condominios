"""Inicializa somente o bucket privado; não executa migrations nem cria dados de negócio."""

from app.core.config import get_settings
from app.modules.storage.s3 import S3Adapter


def main() -> None:
    try:
        S3Adapter(get_settings()).ensure_private_bucket()
    except Exception:
        raise SystemExit("Não foi possível inicializar o bucket privado.") from None
    print("Bucket privado pronto.")


if __name__ == "__main__":
    main()
