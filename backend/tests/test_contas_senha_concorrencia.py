"""Dois pedidos simultâneos com o mesmo token de redefinição: só um troca a senha.

Sem a fixture de rollback: cada requisição abre a própria sessão e conexão (como o
`get_session` de produção) e faz commit de verdade, para o UPDATE condicional do token decidir
entre as duas. Threads disparam juntas numa barreira; tudo o que foi criado é apagado no fim.
"""

import os
import secrets
import threading
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session
from app.main import create_app
from app.modules.auth.security import hash_do_token, hash_senha, verificar_senha
from app.modules.contas import repository
from app.modules.usuarios.models import TokenRecuperacaoSenha, Usuario

pytestmark = pytest.mark.postgres

RODADAS = 10
URL = "/api/v1/contas/redefinicao-senha"


@pytest.fixture
def engine() -> Generator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url, pool_size=4)
    yield engine
    engine.dispose()


@pytest.fixture
def usuario_id(engine: Engine) -> Generator[uuid.UUID]:
    with Session(engine) as session:
        usuario = Usuario(
            nome="Pessoa da Concorrência",
            email=f"{uuid.uuid4().hex}@exemplo.test",
            tipo_cadastro="morador",
            senha_hash=hash_senha("SenhaInicial1"),
        )
        session.add(usuario)
        session.commit()
        id_ = usuario.id

    yield id_

    # A trilha de auditoria recusa DELETE por trigger (só inserção); `replica` desliga os
    # triggers só nesta transação de limpeza.
    with engine.begin() as conexao:
        conexao.execute(text("SET LOCAL session_replication_role = replica"))
        parametros = {"u": id_}
        conexao.execute(text("DELETE FROM registros_auditoria WHERE usuario_id = :u"), parametros)
        conexao.execute(
            text("DELETE FROM tokens_recuperacao_senha WHERE usuario_id = :u"), parametros
        )
        conexao.execute(text("DELETE FROM usuarios WHERE id = :u"), parametros)


@pytest.fixture
def app(engine: Engine):
    app = create_app()
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)

    def sessao_real() -> Generator[Session]:
        with fabrica() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_session] = sessao_real
    return app


def emitir_token(engine: Engine, usuario_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    with Session(engine) as session:
        session.add(
            TokenRecuperacaoSenha(
                usuario_id=usuario_id,
                token_hash=hash_do_token(token),
                expira_em=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.commit()
    return token


def disparar_juntos(app, corpos: list[dict[str, Any]]) -> list[Any]:
    barreira = threading.Barrier(len(corpos))
    respostas: list[Any] = [None] * len(corpos)

    def executar(indice: int, corpo: dict[str, Any]) -> None:
        cliente = TestClient(app)  # sem `with`: cada chamada roda no próprio event loop
        barreira.wait()
        respostas[indice] = cliente.post(URL, json=corpo)

    threads = [threading.Thread(target=executar, args=(i, c)) for i, c in enumerate(corpos)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(r is not None for r in respostas), "alguma requisição não terminou"
    return respostas


def test_mesmo_token_em_paralelo_troca_a_senha_uma_vez(app, engine, usuario_id):
    for rodada in range(RODADAS):
        token = emitir_token(engine, usuario_id)
        senhas = [f"Rodada{rodada}A", f"Rodada{rodada}B"]
        with Session(engine) as session:
            versao_antes = session.get(Usuario, usuario_id).sessao_versao

        respostas = disparar_juntos(app, [{"token": token, "senha_nova": s} for s in senhas])

        status = sorted(r.status_code for r in respostas)
        assert status == [204, 422], (rodada, [r.text for r in respostas])
        perdedora = next(r for r in respostas if r.status_code == 422)
        assert perdedora.json()["error"]["reason"] == "token_invalido"
        vencedora = senhas[[r.status_code for r in respostas].index(204)]

        with Session(engine) as session:
            usuario = session.get(Usuario, usuario_id)
            assert usuario.sessao_versao == versao_antes + 1  # uma única troca
            assert verificar_senha(vencedora, usuario.senha_hash)
            pendentes = session.scalar(
                select(func.count())
                .select_from(TokenRecuperacaoSenha)
                .where(
                    TokenRecuperacaoSenha.usuario_id == usuario_id,
                    TokenRecuperacaoSenha.usado_em.is_(None),
                )
            )
            assert pendentes == 0
            eventos = session.scalar(
                text(
                    "SELECT count(*) FROM registros_auditoria "
                    "WHERE usuario_id = :u AND acao = 'conta.senha_redefinir'"
                ),
                {"u": usuario_id},
            )
            assert eventos == rodada + 1  # um evento por troca, nenhum da requisição perdedora


def test_tokens_diferentes_da_mesma_conta_sao_serializados(app, engine, usuario_id, monkeypatch):
    tokens = [emitir_token(engine, usuario_id), emitir_token(engine, usuario_id)]
    senhas = ["NovaSenhaUm1", "NovaSenhaDois2"]
    with Session(engine) as session:
        versao_antes = session.get(Usuario, usuario_id).sessao_versao
    antes_do_lock = threading.Barrier(2)
    obter_conta_travada = repository.obter_conta_travada

    def sincronizar_antes_do_lock(session: Session, usuario_id_: uuid.UUID) -> Usuario | None:
        antes_do_lock.wait(timeout=10)
        return obter_conta_travada(session, usuario_id_)

    # Força ambas as requisições a chegarem juntas ao lock da mesma conta. No fluxo antigo, cada
    # transação já consumia seu token antes de esperar, abrindo a corrida/deadlock.
    monkeypatch.setattr(repository, "obter_conta_travada", sincronizar_antes_do_lock)
    respostas = disparar_juntos(
        app,
        [
            {"token": token, "senha_nova": senha}
            for token, senha in zip(tokens, senhas, strict=True)
        ],
    )

    assert sorted(resposta.status_code for resposta in respostas) == [204, 422]
    perdedora = next(resposta for resposta in respostas if resposta.status_code == 422)
    assert perdedora.json()["error"]["reason"] == "token_invalido"
    vencedora = senhas[[resposta.status_code for resposta in respostas].index(204)]

    with Session(engine) as session:
        usuario = session.get(Usuario, usuario_id)
        assert usuario.sessao_versao == versao_antes + 1
        assert verificar_senha(vencedora, usuario.senha_hash)
        eventos = session.scalar(
            text(
                "SELECT count(*) FROM registros_auditoria "
                "WHERE usuario_id = :u AND acao = 'conta.senha_redefinir'"
            ),
            {"u": usuario_id},
        )
        assert eventos == 1
