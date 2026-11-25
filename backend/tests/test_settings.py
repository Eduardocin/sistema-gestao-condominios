import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch):
    """Os testes montam Settings só com o que passam: variáveis do terminal ou do CI
    (DATABASE_URL, APP_ENV, CORS_ORIGINS...) não podem mudar o resultado."""
    for campo in Settings.model_fields:
        monkeypatch.delenv(campo.upper(), raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)


def test_database_url_uses_configured_port_and_escapes_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None, postgres_port=5544, postgres_password="local@pass:/")
    url = settings.sqlalchemy_url
    assert url.drivername == "postgresql+psycopg"
    assert url.port == 5544
    assert url.password == "local@pass:/"


def test_explicit_database_url_overrides_components():
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://test:test@localhost:5545/test_db"
    )
    assert settings.sqlalchemy_url.database == "test_db"
    assert settings.sqlalchemy_url.port == 5545


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://storage:9000",
        "http://user:pass@storage:9000",
        "http://storage:9000/path",
        "http://storage:9000?key=secret",
    ],
)
def test_storage_endpoint_cannot_contain_paths_or_credentials(endpoint):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, storage_endpoint=endpoint)


def test_storage_signed_url_duration_is_bounded():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, storage_url_seconds=301)


def test_defaults_de_autenticacao():
    settings = Settings(_env_file=None)
    assert settings.access_token_expire_minutes == 15
    assert settings.refresh_token_expire_days == 7
    assert settings.login_max_failures == 5
    assert settings.login_lockout_minutes == 15


def test_segredo_jwt_curto_e_recusado():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret_key="curto")


def test_segredo_padrao_e_proibido_em_producao():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


PRODUCAO_VALIDA = {
    "app_env": "production",
    "jwt_secret_key": "x" * 40,
    "cors_origins": ["https://condominios.exemplo.test"],
    "postgres_password": "senha-de-producao-ficticia",
    "storage_access_key": "chave-de-producao-ficticia",
    "storage_secret_key": "segredo-de-producao-ficticio",
}


def test_segredo_proprio_vale_em_producao():
    settings = Settings(_env_file=None, **PRODUCAO_VALIDA)
    assert settings.app_env == "production"


@pytest.mark.parametrize(
    ("alteracao", "trecho"),
    [
        ({"postgres_password": "local_dev_only"}, "POSTGRES_PASSWORD"),
        ({"storage_access_key": "condominios_storage_dev"}, "STORAGE_ACCESS_KEY"),
        ({"storage_secret_key": "storage_local_dev_only"}, "STORAGE_SECRET_KEY"),
        ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
        ({"cors_origins": ["http://condominios.exemplo.test"]}, "CORS_ORIGINS"),
    ],
)
def test_credenciais_de_desenvolvimento_sao_proibidas_em_producao(alteracao, trecho):
    with pytest.raises(ValidationError, match=trecho):
        Settings(_env_file=None, **(PRODUCAO_VALIDA | alteracao))


def test_senha_padrao_do_banco_vale_em_producao_com_database_url():
    # Com DATABASE_URL própria, os campos POSTGRES_* nem são usados.
    settings = Settings(
        _env_file=None,
        **(
            PRODUCAO_VALIDA
            | {
                "postgres_password": "local_dev_only",
                "database_url": "postgresql+psycopg://app:segredo@db.exemplo.test:5432/prod",
            }
        ),
    )
    assert settings.sqlalchemy_url.host == "db.exemplo.test"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_padroes_de_desenvolvimento_continuam_validos_fora_de_producao(app_env):
    settings = Settings(_env_file=None, app_env=app_env)
    assert settings.postgres_password.get_secret_value() == "local_dev_only"
