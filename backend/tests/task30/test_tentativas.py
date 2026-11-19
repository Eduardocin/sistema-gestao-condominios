from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auditoria import service as auditoria
from app.modules.usuarios.models import TentativaChaveAcesso
from app.modules.vinculos import repository
from tests.isolamento.cenario import cabecalho, token_de
from tests.task30.conftest import morador, vincular

pytestmark = pytest.mark.postgres


def erros(client, caso, quantidade):
    for _ in range(quantidade):
        assert vincular(client, caso, chave_="Z" * 10).status_code == 404


def test_cinco_erros_bloqueiam_inclusive_chave_valida_sem_consulta(
    client, session, caso, monkeypatch
):
    erros(client, caso, 5)

    def nao_consultar(*args, **kwargs):
        pytest.fail("Chave consultada durante bloqueio")

    monkeypatch.setattr(repository, "localizar_chave", nao_consultar)
    resposta = vincular(client, caso)
    assert resposta.status_code == 429 and 0 < int(resposta.headers["Retry-After"]) <= 900
    session.rollback()
    tentativas = list(
        session.scalars(
            select(TentativaChaveAcesso).where(TentativaChaveAcesso.usuario_id == caso.usuario.id)
        )
    )
    assert len(tentativas) == 6 and not any(t.sucesso for t in tentativas)


def test_bloqueio_expira_e_429_nao_estende_prazo(client, session, caso):
    erros(client, caso, 5)
    quinta = session.scalars(
        select(TentativaChaveAcesso)
        .where(TentativaChaveAcesso.usuario_id == caso.usuario.id)
        .order_by(TentativaChaveAcesso.criado_em.desc())
    ).first()
    for minutos in (3, 3, 3):
        caso.relogio.avancar(minutes=minutos)
        assert vincular(client, caso).status_code == 429
    caso.relogio.momento = quinta.criado_em + timedelta(minutes=15)
    assert vincular(client, caso).status_code == 201


def test_sucesso_reinicia_a_sequencia_e_duplicado_nao_conta_como_erro(client, session, caso):
    erros(client, caso, 4)
    assert vincular(client, caso).status_code == 201
    assert vincular(client, caso).status_code == 409
    erros(client, caso, 4)
    assert vincular(client, caso, chave_=caso.chaves[1].codigo).status_code == 201


def test_erros_fora_da_janela_nao_somam(client, caso):
    erros(client, caso, 4)
    caso.relogio.avancar(minutes=16)
    erros(client, caso, 4)
    assert vincular(client, caso).status_code == 201


def test_limite_e_por_conta_nao_por_condominio(client, session, caso):
    erros(client, caso, 5)
    assert vincular(client, caso, chave_=caso.chaves[2].codigo).status_code == 429
    outro = morador(session)
    session.commit()
    assert vincular(client, caso, headers=cabecalho(token_de(outro, None))).status_code == 201


def test_relogio_igual_nao_perde_ordem_do_reset(client, session, caso):
    momento = caso.relogio.momento
    from app.core.tempo import get_relogio

    client.app.dependency_overrides[get_relogio] = lambda: lambda: momento
    erros(client, caso, 4)
    assert vincular(client, caso).status_code == 201
    erros(client, caso, 4)
    assert vincular(client, caso, chave_=caso.chaves[1].codigo).status_code == 201


def test_falha_no_vinculo_nao_apaga_falhas_nem_reinicia_contador(client, caso, monkeypatch):
    erros(client, caso, 4)

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha simulada de auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar)
    assert vincular(client, caso).status_code == 500
    erros(client, caso, 1)
    assert vincular(client, caso).status_code == 429
