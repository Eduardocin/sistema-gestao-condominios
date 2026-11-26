from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

ROOT = Path(__file__).resolve().parents[3]

# Segredo usado só em desenvolvimento e testes, para o projeto rodar sem configuração extra.
# Em produção ele é proibido (veja a validação em `Settings`).
DEV_JWT_SECRET = "dev-only-jwt-secret-troque-em-producao-0000"
# HS256 pede uma chave com pelo menos 32 bytes; abaixo disso a assinatura fica fraca.
JWT_SECRET_MIN_LENGTH = 32
# Credenciais locais de desenvolvimento (as mesmas do .env.example). Proibidas em produção.
DEV_POSTGRES_PASSWORD = "local_dev_only"
DEV_STORAGE_ACCESS_KEY = "condominios_storage_dev"
DEV_STORAGE_SECRET_KEY = "storage_local_dev_only"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Gestão de Condomínios"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    frontend_base_url: str = "http://localhost:5173"
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    database_url: SecretStr | None = None
    postgres_user: str = "condominios_dev"
    postgres_password: SecretStr = SecretStr(DEV_POSTGRES_PASSWORD)
    postgres_db: str = "condominios"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    storage_endpoint: str = "http://127.0.0.1:9000"
    storage_public_endpoint: str = "http://127.0.0.1:9000"
    storage_access_key: SecretStr = SecretStr(DEV_STORAGE_ACCESS_KEY)
    storage_secret_key: SecretStr = SecretStr(DEV_STORAGE_SECRET_KEY)
    storage_bucket: str = "condominios-arquivos"
    storage_region: str = "us-east-1"
    storage_url_seconds: int = Field(default=60, ge=1, le=300)

    @field_validator("storage_endpoint", "storage_public_endpoint")
    @classmethod
    def validate_storage_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Endpoint S3 deve ser HTTP(S), sem credenciais, caminho ou query.")
        return value.rstrip("/")

    @field_validator("frontend_base_url")
    @classmethod
    def validate_frontend_base_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "FRONTEND_BASE_URL deve ser HTTP(S), sem credenciais, query ou fragmento."
            )
        return value.rstrip("/")

    # Ambiente de execução. Só "production" liga as travas extras de segurança.
    app_env: Literal["development", "test", "production"] = "development"

    # Autenticação (JWT). O access token vive pouco; o refresh token permite renová-lo
    # sem pedir a senha de novo.
    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)

    # Proteção contra força bruta no login: após `login_max_failures` erros seguidos
    # dentro da janela, a tentativa fica bloqueada por `login_lockout_minutes`.
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)

    # E-mail assíncrono (US-803, plataforma.md seção 6). `console` escreve no log em vez de
    # enviar: é o padrão em desenvolvimento e nos testes.
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "nao-responda@example.test"
    smtp_starttls: bool = False
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    # O worker da fila roda no processo da API (uma instância; ADR 0001) quando ligado.
    email_worker_ativo: bool = False
    email_worker_intervalo_seconds: int = Field(default=30, ge=1, le=3600)
    email_max_tentativas: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def _validar_segredo_jwt(self) -> Self:
        segredo = self.jwt_secret_key.get_secret_value()
        if len(segredo) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY precisa ter pelo menos {JWT_SECRET_MIN_LENGTH} caracteres."
            )
        if self.app_env == "production" and segredo == DEV_JWT_SECRET:
            raise ValueError("Defina um JWT_SECRET_KEY próprio: o padrão não vale em produção.")
        return self

    @model_validator(mode="after")
    def _validar_producao(self) -> Self:
        """Em produção, nada de credencial de desenvolvimento nem CORS aberto (TASK-54)."""
        if self.app_env != "production":
            return self
        if urlsplit(self.frontend_base_url).scheme != "https":
            raise ValueError("FRONTEND_BASE_URL deve usar HTTPS em produção.")
        if self.email_backend == "console":
            raise ValueError("EMAIL_BACKEND não pode ser 'console' em produção; configure SMTP.")
        for origem in self.cors_origins:
            if origem.strip() == "*":
                raise ValueError("CORS_ORIGINS não pode conter '*' em produção.")
            if origem.strip().lower().startswith("http://"):
                raise ValueError(
                    f"CORS_ORIGINS só aceita origens https:// em produção (recebido: {origem})."
                )
        url_database = self.database_url.get_secret_value() if self.database_url else ""
        if url_database:
            senha_na_url = make_url(url_database).password
            if senha_na_url == DEV_POSTGRES_PASSWORD:
                raise ValueError(
                    "Defina uma senha própria em DATABASE_URL: a senha padrão do banco "
                    "não vale em produção."
                )
        elif self.postgres_password.get_secret_value() == DEV_POSTGRES_PASSWORD:
            raise ValueError(
                "Defina POSTGRES_PASSWORD próprio: a senha padrão do banco não vale em produção."
            )
        if (
            self.storage_access_key.get_secret_value() == DEV_STORAGE_ACCESS_KEY
            or self.storage_secret_key.get_secret_value() == DEV_STORAGE_SECRET_KEY
        ):
            raise ValueError(
                "Defina STORAGE_ACCESS_KEY e STORAGE_SECRET_KEY próprios: as chaves padrão do "
                "storage não valem em produção."
            )
        return self

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url and self.database_url.get_secret_value():
            return make_url(self.database_url.get_secret_value())
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
