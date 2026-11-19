"""Dois pedidos reais disputam o CNPJ; só um cadastro e sua auditoria são confirmados."""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios import repository
from app.modules.condominios.models import Condominio, CondominioAnalise, VinculoCondominio
from app.modules.unidades.models import Andar, Bloco, Unidade
from app.modules.usuarios.models import Usuario
from tests.isolamento.cenario import cabecalho, token_de
from tests.test_condominios_cadastro import corpo

pytestmark = pytest.mark.postgres


def test_cnpj_concorrente_confirma_somente_um_cadastro(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para PostgreSQL exclusivo migrado")
    engine = create_engine(url, pool_size=4)
    assert engine.dialect.name == "postgresql"
    assert engine.url.database and engine.url.database.endswith("_test")
    usuarios = [uuid.uuid4(), uuid.uuid4()]
    try:
        with Session(engine) as session:
            for id_ in usuarios:
                session.add(
                    Usuario(
                        id=id_,
                        nome="Administração concorrente",
                        tipo_cadastro="administracao",
                        email=f"{id_.hex}@exemplo.test",
                    )
                )
            session.commit()
            headers = [cabecalho(token_de(session.get(Usuario, id_), None)) for id_ in usuarios]

        def sessao_da_requisicao():
            with Session(engine) as session:
                try:
                    yield session
                except Exception:
                    session.rollback()
                    raise

        barreira = threading.Barrier(2)
        criar = repository.criar_condominio

        def criar_juntos(*args, **kwargs):
            barreira.wait(timeout=10)
            return criar(*args, **kwargs)

        monkeypatch.setattr(repository, "criar_condominio", criar_juntos)
        app = create_app()
        app.dependency_overrides[get_session] = sessao_da_requisicao

        def enviar(header):
            with TestClient(app) as client:
                return client.post("/api/v1/condominios", headers=header, json=corpo())

        with ThreadPoolExecutor(max_workers=2) as executor:
            respostas = list(executor.map(enviar, headers))
        assert sorted(r.status_code for r in respostas) == [201, 409]
        erro = next(r for r in respostas if r.status_code == 409)
        assert erro.json()["error"]["reason"] == "cnpj_ja_cadastrado"
        sucesso = next(r for r in respostas if r.status_code == 201).json()
        id_ = uuid.UUID(sucesso["id"])
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(Condominio)
                    .where(Condominio.criado_por_usuario_id.in_(usuarios))
                )
                == 1
            )
            for modelo, quantidade in [
                (Bloco, 2),
                (Andar, 3),
                (Unidade, 6),
                (VinculoCondominio, 1),
                (CondominioAnalise, 1),
                (RegistroAuditoria, 1),
            ]:
                assert (
                    session.scalar(
                        select(func.count()).select_from(modelo).where(modelo.condominio_id == id_)
                    )
                    == quantidade
                )
    finally:
        # Mesmo padrão da fixture de auditoria: só UUIDs próprios e banco exclusivo de teste.
        # O trigger de produção permanece inalterado; não há DDL, TRUNCATE ou limpeza global.
        with engine.begin() as connection:
            ids = list(
                connection.scalars(
                    select(Condominio.id).where(Condominio.criado_por_usuario_id.in_(usuarios))
                )
            )
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                text("DELETE FROM registros_auditoria WHERE usuario_id = ANY(:u)"), {"u": usuarios}
            )
            for tabela in (
                "unidades",
                "andares",
                "blocos",
                "vinculos_condominio",
                "condominio_analises",
            ):
                connection.execute(
                    text(f"DELETE FROM {tabela} WHERE condominio_id = ANY(:c)"), {"c": ids}
                )
            connection.execute(text("DELETE FROM condominios WHERE id = ANY(:c)"), {"c": ids})
            connection.execute(text("DELETE FROM usuarios WHERE id = ANY(:u)"), {"u": usuarios})
        engine.dispose()
