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
