"""Cenários confirmados para testar sessões independentes no PostgreSQL exclusivo de testes.

Como os testes de concorrência existentes, limpamos apenas os UUIDs criados pela fixture.
Nenhum schema/migration é criado aqui; o banco deve estar migrado pelo Alembic.
"""

import os
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db import session as banco
from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.rate_limit import get_login_rate_limiter
from app.modules.auth.security import hash_senha
from app.modules.funcionarios.models import Funcionario, ResponsavelAdministracao
from tests.autorizacao.cenario import Predio, montar_predio

SENHA = "SenhaAuditoria123"


@dataclass
class Cenario:
    fabrica: sessionmaker[Session]
    a: Predio
    b: Predio
    responsavel: ResponsavelAdministracao
    outro_responsavel: ResponsavelAdministracao
    funcionario: Funcionario


@pytest.fixture
def cenario(monkeypatch) -> Generator[Cenario]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para PostgreSQL exclusivo e migrado")
    engine: Engine = create_engine(url)
    assert engine.dialect.name == "postgresql"
    assert engine.url.database and "test" in engine.url.database.lower()
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(banco, "get_session_factory", lambda: fabrica)
    with fabrica() as session:
        a, b = montar_predio(session, "Auditoria A"), montar_predio(session, "Auditoria B")
        a.morador.senha_hash = hash_senha(SENHA)
        responsavel = ResponsavelAdministracao(condominio_id=a.condominio.id, nome="Responsável A")
        outro = ResponsavelAdministracao(condominio_id=b.condominio.id, nome="Responsável B")
        funcionario = Funcionario(
            condominio_id=a.condominio.id, nome="Porteiro A", funcao="porteiro"
        )
        session.add_all([responsavel, outro, funcionario])
        session.commit()
    usuarios = [
        p.id
        for predio in (a, b)
        for p in (predio.morador, predio.funcionario, predio.administracao, predio.adm)
    ]
    condominios = [a.condominio.id, b.condominio.id]
    try:
        yield Cenario(fabrica, a, b, responsavel, outro, funcionario)
    finally:
        # Dados próprios da fixture, em banco cujo nome identifica explicitamente testes.
        # O papel privilegiado é exclusivo do teste; a aplicação não desliga o trigger.
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                text(
                    "DELETE FROM registros_auditoria WHERE condominio_id = ANY(:c) "
                    "OR usuario_id = ANY(:u)"
                ),
                {"c": condominios, "u": usuarios},
            )
            for tabela in (
                "permissoes_aba",
                "moradores_unidade",
                "vinculos_condominio",
                "responsaveis_administracao",
                "funcionarios",
                "unidades",
            ):
                connection.execute(
                    text(f"DELETE FROM {tabela} WHERE condominio_id = ANY(:c)"), {"c": condominios}
                )
            connection.execute(
                text("DELETE FROM condominios WHERE id = ANY(:c)"), {"c": condominios}
            )
            connection.execute(text("DELETE FROM usuarios WHERE id = ANY(:u)"), {"u": usuarios})
        engine.dispose()


@pytest.fixture
def client(cenario) -> Generator[TestClient]:
    get_login_rate_limiter().resetar()
    with TestClient(create_app(), client=("203.0.113.20", 50000)) as client:
        yield client
    get_login_rate_limiter().resetar()


ROTA = "/api/v1/plataforma/auditoria"


@dataclass
class CasoConsulta:
    cenario: Cenario
    session: Session
    client: TestClient
    eventos: list[RegistroAuditoria]
    tipo: str

    @property
    def headers(self):
        return self.cenario.a.cabecalho_de("plataforma")

    def consultar(self, **params):
        return self.client.get(
            ROTA, headers=self.headers, params={"recurso_tipo": self.tipo, **params}
        )


@pytest.fixture
def consulta(cenario) -> Generator[CasoConsulta]:
    tipo = f"consulta_{uuid.uuid4().hex}"
    with cenario.fabrica.kw["bind"].connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                instantes = [
                    datetime(2026, 11, 16, 2, 59, 59, tzinfo=UTC),
                    datetime(2026, 11, 16, 3, tzinfo=UTC),
                    datetime(2026, 11, 17, 2, 59, 59, 999999, tzinfo=UTC),
                    datetime(2026, 11, 17, 3, tzinfo=UTC),
                    datetime(2026, 11, 17, 3, tzinfo=UTC),
                ]
                usuarios = [
                    cenario.a.administracao.id,
                    cenario.a.morador.id,
                    cenario.b.administracao.id,
                    None,
                    cenario.a.adm.id,
                ]
                condominios = [
                    cenario.a.condominio.id,
                    cenario.a.condominio.id,
                    cenario.b.condominio.id,
                    None,
                    None,
                ]
                acoes = [
                    "condominio.aprovar",
                    "condominio.rejeitar",
                    "permissao_aba.alterar",
                    "seguranca.login_falho",
                    "seguranca.login",
                ]
                registros = [
                    RegistroAuditoria(
                        usuario_id=usuarios[i],
                        condominio_id=condominios[i],
                        acao=acoes[i],
                        recurso_tipo=tipo,
                        recurso_id=(
                            cenario.a.unidade_101.id if i < 2 else cenario.b.unidade_101.id
                        ),
                        responsavel_nome="Síndica" if i == 0 else None,
                        perfil="plataforma" if i == 4 else None,
                        criado_em=instantes[i],
                        antes={"status": "pendente"} if i == 0 else None,
                        depois={
                            "status": "ativo",
                            "senha": "SEGREDO_LEGADO",
                            "pessoa": {
                                "documento": "52998224725",
                                "token": "TOKEN_LEGADO",
                            },
                        }
                        if i == 0
                        else None,
                        ip="203.0.113.9" if i == 0 else None,
                    )
                    for i in range(5)
                ]
                session.add_all(registros)
                session.flush()
                app = create_app()
                app.dependency_overrides[get_session] = lambda: session
                with TestClient(app) as client:
                    yield CasoConsulta(cenario, session, client, registros, tipo)
        finally:
            transaction.rollback()
