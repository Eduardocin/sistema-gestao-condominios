import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.contexto import ContextoCondominio
from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import VinculoCondominio
from app.modules.encomendas import repository as encomendas
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.funcionarios.repository import RepositorioResponsaveis
from app.modules.permissoes_aba.repository import RepositorioPermissoes
from app.modules.permissoes_aba.repository import RepositorioUnidades as UnidadesPermissoes
from app.modules.unidades.models import ChaveAcesso, MoradorUnidade, Unidade
from app.modules.unidades.repository import RepositorioUnidades
from app.modules.usuarios.models import Usuario
from app.modules.vinculos import repository
from tests.auditoria.conftest import cenario as cenario
from tests.us305.conftest import ACAO, HASH, chave, headers_morador, morador, permissoes, rota

pytestmark = pytest.mark.postgres


@pytest.fixture
def disputa(cenario):
    c = cenario
    with c.fabrica() as session:
        a = session.merge(c.a.morador)
        b = session.merge(c.b.morador)
        a.tipo_cadastro = b.tipo_cadastro = "morador"
        a.senha_hash = b.senha_hash = HASH
        permissoes(session, c.a.morador_unidade, gestor=True)
        alvo = morador(session, c.a, usuario=b)
        novo = Usuario(
            nome="Novo morador US305",
            email=f"{uuid.uuid4().hex}@example.test",
            tipo_cadastro="morador",
            senha_hash=HASH,
        )
        segundo = ResponsavelAdministracao(condominio_id=c.a.condominio.id, nome="Substituto")
        session.add_all([novo, segundo])
        keys = [chave(session, c.a), chave(session, c.a, c.a.unidade_102)]
        session.commit()
    app = create_app()
    app.openapi()  # Schemas preparados antes da concorrência, como numa única API.
    d = SimpleNamespace(c=c, alvo=alvo, novo=novo, segundo=segundo, keys=keys, app=app)
    try:
        yield d
    finally:
        # Limpeza restrita aos UUIDs da fixture, no PostgreSQL exclusivo de teste.
        with c.fabrica() as session:
            session.execute(text("SET LOCAL session_replication_role = replica"))
            session.execute(
                text("DELETE FROM chaves_acesso WHERE condominio_id=:c"), {"c": c.a.condominio.id}
            )
            session.execute(
                text("DELETE FROM tentativas_chave_acesso WHERE usuario_id IN (:a,:b,:n)"),
                {"a": c.a.morador.id, "b": c.b.morador.id, "n": novo.id},
            )
            session.execute(
                text("DELETE FROM registros_auditoria WHERE usuario_id=:u"), {"u": novo.id}
            )
            session.execute(
                text(
                    "DELETE FROM permissoes_aba WHERE morador_unidade_id IN "
                    "(SELECT id FROM moradores_unidade WHERE usuario_id=:u)"
                ),
                {"u": novo.id},
            )
            session.execute(
                text("DELETE FROM moradores_unidade WHERE usuario_id=:u"), {"u": novo.id}
            )
            session.execute(
                text("DELETE FROM vinculos_condominio WHERE usuario_id=:u"), {"u": novo.id}
            )
            session.execute(text("DELETE FROM usuarios WHERE id=:u"), {"u": novo.id})
            session.commit()


def enviar(d, caminho, corpo, *, metodo="post", headers=None):
    with TestClient(d.app, raise_server_exceptions=False) as client:
        return getattr(client, metodo)(
            caminho, json=corpo, headers=headers or d.c.a.cabecalho_de("administracao")
        )


def desfazer(d, associacao=None, unidade=None, *, headers=None, morador_=False):
    return enviar(
        d,
        rota(unidade or d.c.a.unidade_101.id, (associacao or d.alvo.associacao).id),
        {} if morador_ else {"responsavel_id": str(d.c.responsavel.id)},
        headers=headers,
    )


def simultaneos(monkeypatch, objeto, nome):
    barreira = threading.Barrier(2)
    original = getattr(objeto, nome)

    def juntos(*args, **kwargs):
        barreira.wait(timeout=15)
        return original(*args, **kwargs)

    monkeypatch.setattr(objeto, nome, juntos)


def ordenar(monkeypatch, pontos, primeiro):
    papel = ContextVar("papel_us305")
    trancou, chegou = threading.Event(), threading.Event()
    for objeto, nome in pontos:
        original = getattr(objeto, nome)

        def envoltorio(original):
            def bloqueio(*args, **kwargs):
                if papel.get() == primeiro:
                    resultado = original(*args, **kwargs)
                    trancou.set()
                    assert chegou.wait(timeout=15)
                    return resultado
                assert trancou.wait(timeout=15)
                chegou.set()
                return original(*args, **kwargs)

            return bloqueio

        monkeypatch.setattr(objeto, nome, envoltorio(original))

    def executar(item):
        etiqueta, funcao = item
        papel.set(etiqueta)
        return funcao()

    return executar


def estado(d):
    with d.c.fabrica() as session:
        ativos = list(
            session.scalars(
                select(MoradorUnidade).where(
                    MoradorUnidade.condominio_id == d.c.a.condominio.id,
                    MoradorUnidade.status == "ativo",
                )
            )
        )
        evs = list(
            session.scalars(
                select(RegistroAuditoria).where(
                    RegistroAuditoria.condominio_id == d.c.a.condominio.id,
                    RegistroAuditoria.acao == ACAO,
                )
            )
        )
        keys = list(
            session.scalars(
                select(ChaveAcesso).where(
                    ChaveAcesso.unidade_id == d.c.a.unidade_101.id,
                    ChaveAcesso.revogada_em.is_(None),
                )
            )
        )
        return ativos, evs, keys


def test_duas_remocoes_da_mesma_associacao(disputa, monkeypatch):
    d = disputa
    simultaneos(monkeypatch, repository, "bloquear_conta")
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda _: desfazer(d), range(2)))
    assert sorted(r.status_code for r in respostas) == [200, 409]
    ativos, evs, keys = estado(d)
    assert len(evs) == 1 and not keys
    assert {m.id for m in ativos} == {d.c.a.morador_unidade.id}


def test_moradores_diferentes_mesma_unidade_preservam_gestao(disputa, monkeypatch):
    d = disputa
    simultaneos(monkeypatch, repository, "bloquear_conta")
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(
            executor.map(lambda m: desfazer(d, m), [d.alvo.associacao, d.c.a.morador_unidade])
        )
    assert sorted(r.status_code for r in respostas) in ([200, 200], [200, 409])
    ativos, _, _ = estado(d)
    if ativos:
        assert [m.id for m in ativos] == [d.c.a.morador_unidade.id]


def test_mesmo_usuario_em_unidades_distintas_desativa_global_sem_perder_atualizacao(
    disputa, monkeypatch
):
    d = disputa
    with d.c.fabrica() as session:
        segunda = morador(session, d.c.a, usuario=d.c.b.morador, unidade=d.c.a.unidade_102)
        morador(session, d.c.a, usuario=d.c.a.morador, unidade=d.c.a.unidade_102, gestor=True)
        session.commit()
    simultaneos(monkeypatch, repository, "bloquear_conta")
    # Chegam à decisão global segurando unidades distintas, antes de disputar o vínculo.
    simultaneos(monkeypatch, repository, "obter_vinculo")
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(
            executor.map(
                lambda m: desfazer(d, m.associacao, m.associacao.unidade_id), [d.alvo, segunda]
            )
        )
    assert [r.status_code for r in respostas] == [200, 200]
    with d.c.fabrica() as session:
        vinculo = session.get(VinculoCondominio, d.alvo.vinculo.id)
        assert not vinculo.ativo
        assert session.get(VinculoCondominio, d.c.b.vinculo_morador.id).ativo
        assert session.get(Usuario, d.c.b.morador.id).sessao_versao == 1
    assert len(estado(d)[1]) == 2


def test_dois_moradores_tentando_remover_um_ao_outro_revalidam_executor(disputa, monkeypatch):
    d = disputa
    with d.c.fabrica() as session:
        contexto = ContextoCondominio(
            d.c.a.morador.id, d.c.a.condominio.id, "morador", d.c.a.vinculo_morador.id
        )
        RepositorioPermissoes(session, contexto).definir(
            d.alvo.associacao.id, {"usuarios": True}, alterado_por=d.c.a.morador.id
        )
        session.commit()
    simultaneos(monkeypatch, repository, "bloquear_conta")
    pedidos = [
        (d.alvo.associacao, d.c.a.cabecalho_de("morador")),
        (d.c.a.morador_unidade, headers_morador(d.c.b.morador, d.c.a.condominio.id)),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(
            executor.map(lambda p: desfazer(d, p[0], headers=p[1], morador_=True), pedidos)
        )
    assert sorted(r.status_code for r in respostas) == [200, 403]
    ativos, evs, _ = estado(d)
    assert len(ativos) == len(evs) == 1


@pytest.mark.parametrize("primeiro", ["desvinculacao", "vinculo"])
@pytest.mark.parametrize("mesmo_usuario", [False, True])
def test_chave_antiga_concorrente_com_novo_vinculo(disputa, monkeypatch, primeiro, mesmo_usuario):
    d = disputa
    pontos = (
        [(repository, "bloquear_conta")]
        if mesmo_usuario
        else [(RepositorioUnidades, "bloquear"), (repository, "bloquear_destino")]
    )
    executar = ordenar(monkeypatch, pontos, primeiro)
    pedidos = [
        ("desvinculacao", lambda: desfazer(d)),
        (
            "vinculo",
            lambda: enviar(
                d,
                "/api/v1/vinculos/chave",
                {"chave": d.keys[0].codigo},
                headers=headers_morador(d.c.b.morador if mesmo_usuario else d.novo, None),
            ),
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(executar, pedidos))
    esperado = 404 if primeiro == "desvinculacao" else (409 if mesmo_usuario else 201)
    assert [r.status_code for r in respostas] == [200, esperado]
    ativos, evs, keys = estado(d)
    assert len(evs) == 1 and not keys
    assert any(m.usuario_id == d.novo.id for m in ativos) is (
        primeiro == "vinculo" and not mesmo_usuario
    )


@pytest.mark.parametrize("acao", ["gerar", "regenerar"])
@pytest.mark.parametrize("primeiro", ["desvinculacao", "chave"])
def test_geracao_e_regeneracao_serializadas_com_revogacao(disputa, monkeypatch, acao, primeiro):
    d = disputa
    if acao == "gerar":
        with d.c.fabrica() as session:
            session.get(ChaveAcesso, d.keys[0].id).revogada_em = datetime.now(UTC)
            session.commit()
    executar = ordenar(monkeypatch, [(RepositorioUnidades, "bloquear")], primeiro)
    caminho = f"/api/v1/unidades/{d.c.a.unidade_101.id}/chave" + (
        "/regeneracao" if acao == "regenerar" else ""
    )
    pedidos = [
        ("desvinculacao", lambda: desfazer(d)),
        ("chave", lambda: enviar(d, caminho, {"responsavel_id": str(d.c.responsavel.id)})),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(executar, pedidos))
    codigo_chave = (
        409
        if acao == "regenerar" and primeiro == "desvinculacao"
        else (201 if acao == "gerar" else 200)
    )
    assert [r.status_code for r in respostas] == [200, codigo_chave]
    _, evs, keys = estado(d)
    assert len(evs) == 1
    assert len(keys) == (1 if acao == "gerar" and primeiro == "desvinculacao" else 0)


@pytest.mark.parametrize("primeiro", ["desvinculacao", "permissao"])
def test_transferencia_concorrente_reconsulta_gestores_apos_trava(disputa, monkeypatch, primeiro):
    d = disputa
    executar = ordenar(
        monkeypatch, [(RepositorioUnidades, "bloquear"), (UnidadesPermissoes, "bloquear")], primeiro
    )
    caminho = f"/api/v1/unidades/{d.c.a.unidade_101.id}/moradores/{d.alvo.associacao.id}/permissoes"
    pedidos = [
        ("desvinculacao", lambda: desfazer(d, d.c.a.morador_unidade)),
        (
            "permissao",
            lambda: enviar(
                d,
                caminho,
                {"abas": {"usuarios": True}},
                metodo="put",
                headers=d.c.a.cabecalho_de("morador"),
            ),
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(executar, pedidos))
    assert [r.status_code for r in respostas] == [409 if primeiro == "desvinculacao" else 200, 200]
    with d.c.fabrica() as session:
        contexto = ContextoCondominio(
            d.c.a.morador.id, d.c.a.condominio.id, "morador", d.c.a.vinculo_morador.id
        )
        assert (
            RepositorioPermissoes(session, contexto).contar_com_usuarios(
                d.c.a.unidade_101.id, excluindo=uuid.uuid4()
            )
            >= 1
        )


@pytest.mark.parametrize("primeiro", ["desvinculacao", "responsavel"])
def test_desativacao_de_responsavel_nao_inverte_travas(disputa, monkeypatch, primeiro):
    d = disputa
    executar = ordenar(
        monkeypatch,
        [(repository, "bloquear_condominio"), (RepositorioResponsaveis, "bloquear_cadastro")],
        primeiro,
    )
    pedidos = [
        ("desvinculacao", lambda: desfazer(d)),
        (
            "responsavel",
            lambda: enviar(
                d, f"/api/v1/responsaveis-administracao/{d.c.responsavel.id}/desativacao", {}
            ),
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(executar, pedidos))
    assert [r.status_code for r in respostas] == [200 if primeiro == "desvinculacao" else 404, 200]
    assert len(estado(d)[1]) == (1 if primeiro == "desvinculacao" else 0)


@pytest.mark.parametrize("primeiro", ["desvinculacao", "permissao"])
def test_revogacao_concorrente_da_aba_do_executor_e_revalidada(disputa, monkeypatch, primeiro):
    d = disputa
    with d.c.fabrica() as session:
        contexto = ContextoCondominio(
            d.c.a.morador.id, d.c.a.condominio.id, "morador", d.c.a.vinculo_morador.id
        )
        RepositorioPermissoes(session, contexto).definir(
            d.alvo.associacao.id, {"usuarios": True}, alterado_por=d.c.a.morador.id
        )
        session.commit()
    executar = ordenar(
        monkeypatch,
        [(RepositorioUnidades, "bloquear"), (UnidadesPermissoes, "bloquear")],
        primeiro,
    )
    caminho = (
        f"/api/v1/unidades/{d.c.a.unidade_101.id}/moradores/{d.c.a.morador_unidade.id}/permissoes"
    )
    pedidos = [
        (
            "desvinculacao",
            lambda: desfazer(d, headers=d.c.a.cabecalho_de("morador"), morador_=True),
        ),
        (
            "permissao",
            lambda: enviar(
                d,
                caminho,
                {"abas": {"usuarios": False}},
                metodo="put",
                headers=headers_morador(d.c.b.morador, d.c.a.condominio.id),
            ),
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(executar, pedidos))
    assert [r.status_code for r in respostas] == (
        [200, 404] if primeiro == "desvinculacao" else [403, 200]
    )


def test_leitura_de_recebimento_na_portaria_nao_inverte_conta_e_unidade(disputa, monkeypatch):
    d = disputa
    unidade_trancada, conta_trancada = threading.Event(), threading.Event()
    original = repository.bloquear_conta

    def bloquear_conta(*args, **kwargs):
        usuario = original(*args, **kwargs)
        conta_trancada.set()
        assert unidade_trancada.wait(timeout=15)
        return usuario

    monkeypatch.setattr(repository, "bloquear_conta", bloquear_conta)

    def receber():
        with d.c.fabrica() as session:
            # O recebimento real começa pela unidade e depois lê morador/usuário em SHARE.
            session.scalar(
                select(Unidade)
                .where(
                    Unidade.id == d.c.a.unidade_101.id,
                    Unidade.condominio_id == d.c.a.condominio.id,
                )
                .with_for_update(read=True)
            )
            unidade_trancada.set()
            assert conta_trancada.wait(timeout=15)
            referencias = encomendas.obter_referencias_recebimento(
                session,
                d.c.a.condominio.id,
                unidade_id=d.c.a.unidade_101.id,
                destinatario_morador_unidade_id=d.alvo.associacao.id,
                recebido_por_funcionario_id=d.c.funcionario.id,
            )
            assert referencias is not None
            session.commit()
            return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        portaria = executor.submit(receber)
        desvinculacao = executor.submit(desfazer, d)
        assert portaria.result(timeout=20)
        assert desvinculacao.result(timeout=20).status_code == 200
    assert len(estado(d)[1]) == 1
