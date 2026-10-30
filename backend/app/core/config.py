from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

ROOT = Path(__file__).resolve().parents[3]

# Segredo usado só em desenvolvimento e testes, para o projeto rodar sem configuração extra.
# Em produção ele é proibido (veja a validação em `Settings`).
DEV_JWT_SECRET = "dev-only-jwt-secret-troque-em-producao-0000"
# HS256 pede uma chave com pelo menos 32 bytes; abaixo disso a assinatura fica fraca.
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Gestão de Condomínios"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: SecretStr | None = None
    postgres_user: str = "condominios_dev"
    postgres_password: SecretStr = SecretStr("local_dev_only")
    postgres_db: str = "condominios"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)

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
