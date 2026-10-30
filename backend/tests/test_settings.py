import pytest
from pydantic import ValidationError

from app.core.config import Settings


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


def test_segredo_proprio_vale_em_producao():
    settings = Settings(_env_file=None, app_env="production", jwt_secret_key="x" * 40)
    assert settings.app_env == "production"
