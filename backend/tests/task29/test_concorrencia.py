import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios import repository as condominios
from app.modules.condominios.models import CondominioAnalise
from app.modules.notificacoes.models import EnvioEmail
from app.modules.unidades.models import ChaveAcesso
from app.modules.unidades.repository import RepositorioUnidades
from tests.auditoria.conftest import cenario as cenario_auditoria

cenario = cenario_auditoria
pytestmark = pytest.mark.postgres


@pytest.fixture
def concorrencia(cenario):
    # Reutiliza a fixture confirmada e suas sessões independentes; só dados próprios.
    with cenario.fabrica() as session:
        condominio = session.merge(cenario.a.condominio)
        condominio.criado_por_usuario_id = cenario.a.administracao.id
        session.commit()
    try:
        yield cenario
    finally:
        with cenario.fabrica() as session:
            for tabela in ("chaves_acesso", "envios_email", "condominio_analises"):
                session.execute(
                    text(f"DELETE FROM {tabela} WHERE condominio_id = :c"),
                    {"c": cenario.a.condominio.id},
                )
            session.commit()


def disputar(cenario, rota, corpos):
    def enviar(corpo):
        with TestClient(create_app()) as client:
            return client.post(
                rota,
                headers=cenario.a.cabecalho_de(
                    "plataforma" if "/plataforma/" in rota else "administracao"
                ),
                json=corpo,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(enviar, corpos))


@pytest.mark.parametrize("segunda_decisao", ["aprovacao", "rejeicao"])
def test_decisoes_concorrentes_serializadas(concorrencia, monkeypatch, segunda_decisao):
    c = concorrencia
    with c.fabrica() as session:
        condominio = session.merge(c.a.condominio)
        condominio.status = "pendente"
        session.commit()
    barreira = threading.Barrier(2)
    original = condominios.obter_plataforma

    def bloquear_juntos(*args, **kwargs):
        if kwargs.get("bloquear"):
            barreira.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(condominios, "obter_plataforma", bloquear_juntos)
    base = f"/api/v1/plataforma/condominios/{c.a.condominio.id}"

    def enviar(acao):
        with TestClient(create_app()) as client:
            return client.post(
                f"{base}/{acao}",
                headers=c.a.cabecalho_de("plataforma"),
                json={"motivo": "Documento inválido"} if acao == "rejeicao" else {},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(enviar, ["aprovacao", segunda_decisao]))
    assert sorted(r.status_code for r in respostas) == [200, 409]
    vencedor = next(r for r in respostas if r.status_code == 200).json()["status"]
    with c.fabrica() as session:
        for modelo in (CondominioAnalise, RegistroAuditoria):
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(modelo)
                    .where(modelo.condominio_id == c.a.condominio.id)
                )
                == 1
            )
        chaves = list(
            session.scalars(
                select(ChaveAcesso).where(ChaveAcesso.condominio_id == c.a.condominio.id)
            )
        )
        assert len(chaves) == (2 if vencedor == "ativo" else 0)
        assert len({chave.codigo for chave in chaves}) == len(chaves)
        assert session.scalar(
            select(func.count())
            .select_from(EnvioEmail)
            .where(EnvioEmail.condominio_id == c.a.condominio.id)
        ) == (1 if vencedor == "ativo" else 0)


@pytest.mark.parametrize("regenerar", [False, True])
def test_chaves_concorrentes_uma_vigente(concorrencia, monkeypatch, regenerar):
    c = concorrencia
    base = f"/api/v1/unidades/{c.a.unidade_101.id}/chave"
    dados = {"responsavel_id": str(c.responsavel.id)}
    if regenerar:
        with TestClient(create_app()) as client:
            assert (
                client.post(base, headers=c.a.cabecalho_de("administracao"), json=dados).status_code
                == 201
            )
    barreira = threading.Barrier(2)
    original = RepositorioUnidades.bloquear

    def bloquear_juntos(*args, **kwargs):
        barreira.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(RepositorioUnidades, "bloquear", bloquear_juntos)
    respostas = disputar(c, base + ("/regeneracao" if regenerar else ""), [dados, dados])
    assert sorted(r.status_code for r in respostas) == ([200, 200] if regenerar else [201, 409])
    with c.fabrica() as session:
        chaves = list(
            session.scalars(select(ChaveAcesso).where(ChaveAcesso.unidade_id == c.a.unidade_101.id))
        )
        assert len(chaves) == (3 if regenerar else 1)
        assert len({chave.codigo for chave in chaves}) == len(chaves)
        assert sum(chave.revogada_em is None for chave in chaves) == 1
        eventos = list(
            session.scalars(
                select(RegistroAuditoria).where(
                    RegistroAuditoria.condominio_id == c.a.condominio.id
                )
            )
        )
        assert len(eventos) == (3 if regenerar else 1)
