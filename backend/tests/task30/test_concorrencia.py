import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import VinculoCondominio
from app.modules.unidades.models import ChaveAcesso, MoradorUnidade, PermissaoAba
from app.modules.unidades.repository import RepositorioUnidades
from app.modules.usuarios.models import TentativaChaveAcesso
from app.modules.vinculos import repository
from tests.auditoria.conftest import cenario as cenario_auditoria
from tests.isolamento.cenario import cabecalho, token_de
from tests.task30.conftest import ROTA, chave, morador

cenario = cenario_auditoria
pytestmark = pytest.mark.postgres


@pytest.fixture
def confirmado(cenario):
    with cenario.fabrica() as session:
        usuarios = [morador(session), morador(session)]
        chaves = [
            chave(session, cenario.a, cenario.a.unidade_102),
            chave(session, cenario.a, cenario.a.unidade_101),
        ]
        session.commit()
    ids = [u.id for u in usuarios]
    try:
        yield SimpleNamespace(
            cenario=cenario,
            usuarios=usuarios,
            chaves=chaves,
            headers=[cabecalho(token_de(u, None)) for u in usuarios],
        )
    finally:
        # Só UUIDs próprios e banco exclusivo já validado pela fixture de auditoria.
        with cenario.fabrica() as session:
            session.execute(text("SET LOCAL session_replication_role = replica"))
            session.execute(
                text("DELETE FROM registros_auditoria WHERE usuario_id = ANY(:u)"), {"u": ids}
            )
            session.execute(
                text(
                    "DELETE FROM permissoes_aba WHERE morador_unidade_id IN "
                    "(SELECT id FROM moradores_unidade WHERE usuario_id = ANY(:u))"
                ),
                {"u": ids},
            )
            for tabela in ("tentativas_chave_acesso", "moradores_unidade", "vinculos_condominio"):
                session.execute(
                    text(f"DELETE FROM {tabela} WHERE usuario_id = ANY(:u)"), {"u": ids}
                )
            session.execute(
                text("DELETE FROM chaves_acesso WHERE condominio_id = :c"),
                {"c": cenario.a.condominio.id},
            )
            session.execute(text("DELETE FROM usuarios WHERE id = ANY(:u)"), {"u": ids})
            session.commit()


def enviar(caso, indice=0, codigo=None):
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        return client.post(
            ROTA, headers=caso.headers[indice], json={"chave": codigo or caso.chaves[0].codigo}
        )


def sincronizar(monkeypatch, nome, quantidade=2):
    barreira = threading.Barrier(quantidade)
    original = getattr(repository, nome)

    def juntos(*args, **kwargs):
        barreira.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, nome, juntos)


@pytest.mark.parametrize("mesma_conta", [False, True])
def test_mesma_chave_e_primeiro_morador_concorrentes(confirmado, monkeypatch, mesma_conta):
    c = confirmado
    sincronizar(monkeypatch, "bloquear_conta" if mesma_conta else "bloquear_destino")
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda i: enviar(c, i), [0, 0 if mesma_conta else 1]))
    assert sorted(r.status_code for r in respostas) == ([201, 409] if mesma_conta else [201, 201])
    with c.cenario.fabrica() as session:
        moradores = list(
            session.scalars(
                select(MoradorUnidade).where(
                    MoradorUnidade.unidade_id == c.cenario.a.unidade_102.id
                )
            )
        )
        assert len(moradores) == (1 if mesma_conta else 2)
        abas = list(
            session.scalars(
                select(PermissaoAba).where(
                    PermissaoAba.morador_unidade_id.in_([m.id for m in moradores])
                )
            )
        )
        assert len(abas) == 7 * len(moradores)
        assert sum(p.aba == "usuarios" and p.com_acesso for p in abas) == 1
        assert sum(not p.com_acesso for p in abas) == (0 if mesma_conta else 1)
        assert session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.usuario_id.in_([u.id for u in c.usuarios]))
        ) == len(moradores)


def test_mesma_conta_varias_unidades_um_vinculo_global(confirmado, monkeypatch):
    c = confirmado
    sincronizar(monkeypatch, "bloquear_conta")
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(
            executor.map(lambda codigo: enviar(c, codigo=codigo), [k.codigo for k in c.chaves])
        )
    assert [r.status_code for r in respostas] == [201, 201]
    with c.cenario.fabrica() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(VinculoCondominio)
                .where(VinculoCondominio.usuario_id == c.usuarios[0].id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(MoradorUnidade)
                .where(MoradorUnidade.usuario_id == c.usuarios[0].id)
            )
            == 2
        )


@pytest.mark.parametrize("primeiro", ["vinculo", "regeneracao"])
def test_regeneracao_e_uso_da_chave_sao_serializados(confirmado, monkeypatch, primeiro):
    c = confirmado
    trancou, concorrente = threading.Event(), threading.Event()
    bloquear_vinculo, bloquear_regeneracao = (
        repository.bloquear_destino,
        RepositorioUnidades.bloquear,
    )

    def vinculo(*args, **kwargs):
        if primeiro == "vinculo":
            resultado = bloquear_vinculo(*args, **kwargs)
            trancou.set()
            assert concorrente.wait(timeout=10)
            return resultado
        concorrente.set()
        return bloquear_vinculo(*args, **kwargs)

    def regeneracao(*args, **kwargs):
        if primeiro == "regeneracao":
            resultado = bloquear_regeneracao(*args, **kwargs)
            trancou.set()
            assert concorrente.wait(timeout=10)
            return resultado
        concorrente.set()
        return bloquear_regeneracao(*args, **kwargs)

    monkeypatch.setattr(repository, "bloquear_destino", vinculo)
    monkeypatch.setattr(RepositorioUnidades, "bloquear", regeneracao)

    def regenerar():
        with TestClient(create_app()) as client:
            return client.post(
                f"/api/v1/unidades/{c.cenario.a.unidade_102.id}/chave/regeneracao",
                headers=c.cenario.a.cabecalho_de("administracao"),
                json={"responsavel_id": str(c.cenario.responsavel.id)},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuro = executor.submit(enviar, c) if primeiro == "vinculo" else executor.submit(regenerar)
        assert trancou.wait(timeout=10)
        outro = executor.submit(regenerar) if primeiro == "vinculo" else executor.submit(enviar, c)
        respostas = [futuro.result(timeout=20), outro.result(timeout=20)]
    assert sorted(r.status_code for r in respostas) == (
        [200, 201] if primeiro == "vinculo" else [200, 404]
    )
    with c.cenario.fabrica() as session:
        assert session.get(ChaveAcesso, c.chaves[0].id).revogada_em is not None
        assert session.scalar(
            select(func.count())
            .select_from(MoradorUnidade)
            .where(MoradorUnidade.usuario_id == c.usuarios[0].id)
        ) == (1 if primeiro == "vinculo" else 0)


def test_erros_simultaneos_nao_burlam_bloqueio(confirmado, monkeypatch):
    c = confirmado
    sincronizar(monkeypatch, "bloquear_conta", 6)
    with ThreadPoolExecutor(max_workers=6) as executor:
        respostas = list(executor.map(lambda _: enviar(c, codigo="Z" * 10), range(6)))
    assert sorted(r.status_code for r in respostas) == [404] * 5 + [429]
    with c.cenario.fabrica() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(TentativaChaveAcesso)
                .where(TentativaChaveAcesso.usuario_id == c.usuarios[0].id)
            )
            == 6
        )


def test_falhas_e_auditoria_persistem_em_sessoes_independentes(confirmado, monkeypatch, caplog):
    c = confirmado
    for _ in range(5):
        assert enviar(c, codigo="Z" * 10).status_code == 404

    def nao_consultar(*args, **kwargs):
        raise AssertionError("Consulta durante bloqueio")

    monkeypatch.setattr(repository, "localizar_chave", nao_consultar)
    resposta = enviar(c)
    assert resposta.status_code == 429 and int(resposta.headers["Retry-After"]) > 0
    with c.cenario.fabrica() as session:
        tentativas = list(
            session.scalars(
                select(TentativaChaveAcesso).where(
                    TentativaChaveAcesso.usuario_id == c.usuarios[0].id
                )
            )
        )
        assert len(tentativas) == 6 and all(not t.sucesso for t in tentativas)
        eventos = list(
            session.scalars(
                select(RegistroAuditoria).where(RegistroAuditoria.usuario_id == c.usuarios[0].id)
            )
        )
        assert len(eventos) == 6 and all(e.acao == "seguranca.chave_invalida" for e in eventos)
        assert sorted(e.depois["status_http"] for e in eventos) == [404] * 5 + [429]
        for e in eventos:
            assert e.condominio_id is None and e.usuario_id == c.usuarios[0].id
            assert c.chaves[0].codigo not in str(e.depois) and "Z" * 10 not in str(e.depois)
    assert c.chaves[0].codigo not in caplog.text and "Z" * 10 not in caplog.text
