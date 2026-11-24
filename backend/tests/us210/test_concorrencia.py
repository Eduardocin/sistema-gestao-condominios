import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.main import create_app
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.security import hash_senha, verificar_senha
from app.modules.condominios.models import VinculoCondominio
from app.modules.contas import repository as contas
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.funcionarios.repository import RepositorioResponsaveis
from app.modules.usuarios.models import Usuario
from tests.auditoria.conftest import cenario as cenario
from tests.us210.conftest import ACAO, CONTA, RESPONSAVEIS, SENHA, email_novo

pytestmark = pytest.mark.postgres


@pytest.fixture
def disputa(cenario):
    # O cenário compartilhado tem uma conta fictícia de Funcionários sem senha. Removemos
    # somente essa associação da fixture para exercitar o provisionamento pela API real.
    with cenario.fabrica() as session:
        vinculo = session.scalar(
            select(VinculoCondominio).where(
                VinculoCondominio.usuario_id == cenario.a.funcionario.id,
                VinculoCondominio.condominio_id == cenario.a.condominio.id,
            )
        )
        session.delete(vinculo)
        segundo = ResponsavelAdministracao(condominio_id=cenario.a.condominio.id, nome="Segundo")
        session.add(segundo)
        session.commit()
    usuario_id = None
    caso = SimpleNamespace(
        c=cenario,
        app=create_app(),
        headers=cenario.a.cabecalho_de("administracao"),
        segundo=segundo,
        dados={
            "login": email_novo(),
            "senha": SENHA,
            "responsavel_id": str(cenario.responsavel.id),
        },
    )
    # Prepara os schemas antes de disparar requisições concorrentes à mesma aplicação.
    caso.app.openapi()
    try:
        yield caso
    finally:
        with cenario.fabrica() as session:
            usuario_id = session.scalar(
                select(VinculoCondominio.usuario_id).where(
                    VinculoCondominio.condominio_id == cenario.a.condominio.id,
                    VinculoCondominio.perfil == "funcionario",
                )
            )
            if usuario_id:
                session.execute(text("SET LOCAL session_replication_role = replica"))
                session.execute(
                    text("DELETE FROM registros_auditoria WHERE usuario_id = :u"), {"u": usuario_id}
                )
                session.execute(
                    text("DELETE FROM vinculos_condominio WHERE usuario_id = :u"), {"u": usuario_id}
                )
                session.execute(text("DELETE FROM usuarios WHERE id = :u"), {"u": usuario_id})
            session.commit()


def enviar(d, payload, *, metodo="put", rota=CONTA):
    with TestClient(d.app) as client:
        return getattr(client, metodo)(rota, headers=d.headers, json=payload)


def sincronizar(monkeypatch):
    barreira = threading.Barrier(2)
    original = RepositorioResponsaveis.bloquear_cadastro

    def juntos(self):
        barreira.wait(timeout=10)
        return original(self)

    monkeypatch.setattr(RepositorioResponsaveis, "bloquear_cadastro", juntos)


@pytest.mark.parametrize("mesmas", [True, False])
def test_criacao_concorrente_tem_uma_identidade(disputa, monkeypatch, mesmas):
    d = disputa
    sincronizar(monkeypatch)
    payloads = [
        d.dados,
        d.dados if mesmas else {**d.dados, "login": email_novo(), "senha": "SenhaAlternativa210"},
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda p: enviar(d, p), payloads))
    assert [r.status_code for r in respostas] == [200, 200]
    with d.c.fabrica() as session:
        vinculos = list(
            session.scalars(
                select(VinculoCondominio).where(
                    VinculoCondominio.condominio_id == d.c.a.condominio.id,
                    VinculoCondominio.perfil == "funcionario",
                )
            )
        )
        assert len(vinculos) == 1
        usuario = session.get(Usuario, vinculos[0].usuario_id)
        assert usuario.sessao_versao == (1 if mesmas else 2)
        vencedor = next(p for p in payloads if p["login"] == usuario.email)
        assert verificar_senha(vencedor["senha"], usuario.senha_hash)
        total = session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(
                RegistroAuditoria.condominio_id == d.c.a.condominio.id,
                RegistroAuditoria.acao == ACAO,
            )
        )
        assert total == (1 if mesmas else 2)


def test_trocas_concorrentes_nao_perdem_versoes(disputa, monkeypatch):
    d = disputa
    assert enviar(d, d.dados).status_code == 200
    with d.c.fabrica() as session:
        vinculo = session.scalar(
            select(VinculoCondominio).where(
                VinculoCondominio.condominio_id == d.c.a.condominio.id,
                VinculoCondominio.perfil == "funcionario",
            )
        )
        ids = vinculo.id, vinculo.usuario_id
    sincronizar(monkeypatch)
    payloads = [
        {**d.dados, "login": email_novo(), "senha": f"SenhaConcorrente{i}210"} for i in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda p: enviar(d, p), payloads))
    assert [r.status_code for r in respostas] == [200, 200]
    with d.c.fabrica() as session:
        vinculo = session.get(VinculoCondominio, ids[0])
        usuario = session.get(Usuario, ids[1])
        assert vinculo.usuario_id == usuario.id and usuario.sessao_versao == 3
        vencedor = next(p for p in payloads if p["login"] == usuario.email)
        assert verificar_senha(vencedor["senha"], usuario.senha_hash)


def test_email_global_concorrente_e_recusado_pela_constraint(disputa, monkeypatch):
    d = disputa
    assert enviar(d, d.dados).status_code == 200
    with d.c.fabrica() as session:
        # Torna a identidade fictícia já pertencente ao B um legado compatível.
        usuario_b = session.get(Usuario, d.c.b.funcionario.id)
        usuario_b.senha_hash = hash_senha(SENHA)
        session.commit()
    barreira = threading.Barrier(2)
    original = contas.campo_em_uso

    def consultar_antes_das_duas_gravacoes(*args, **kwargs):
        resultado = original(*args, **kwargs)
        assert resultado is False
        barreira.wait(timeout=10)
        return resultado

    monkeypatch.setattr(contas, "campo_em_uso", consultar_antes_das_duas_gravacoes)
    mesmo_email = email_novo()
    outro = SimpleNamespace(app=d.app, headers=d.c.b.cabecalho_de("administracao"))
    pedidos = [
        (d, {**d.dados, "login": mesmo_email}),
        (
            outro,
            {
                "login": mesmo_email,
                "senha": SENHA,
                "responsavel_id": str(d.c.outro_responsavel.id),
            },
        ),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda p: enviar(*p), pedidos))
    assert sorted(r.status_code for r in respostas) == [200, 409]
    recusado = next(r for r in respostas if r.status_code == 409)
    assert recusado.json()["error"]["reason"] == "login_indisponivel"
    with d.c.fabrica() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Usuario).where(Usuario.email == mesmo_email)
            )
            == 1
        )


def test_desativacoes_concorrentes_preservam_ultimo(disputa, monkeypatch):
    d = disputa
    sincronizar(monkeypatch)

    def desativar(id_):
        return enviar(d, {}, metodo="post", rota=f"{RESPONSAVEIS}/{id_}/desativacao")

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(desativar, [d.c.responsavel.id, d.segundo.id]))
    assert sorted(r.status_code for r in respostas) == [200, 409]
    with d.c.fabrica() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResponsavelAdministracao)
                .where(
                    ResponsavelAdministracao.condominio_id == d.c.a.condominio.id,
                    ResponsavelAdministracao.ativo.is_(True),
                )
            )
            == 1
        )


def test_edicoes_concorrentes_nao_duplicam_nome_ativo(disputa, monkeypatch):
    d = disputa
    sincronizar(monkeypatch)

    def editar(id_):
        return enviar(d, {"nome": "Nome Único"}, rota=f"{RESPONSAVEIS}/{id_}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(editar, [d.c.responsavel.id, d.segundo.id]))
    assert sorted(r.status_code for r in respostas) == [200, 409]


@pytest.mark.parametrize("primeiro", ["conta", "desativacao"])
def test_responsavel_revalidado_com_desativacao_concorrente(disputa, monkeypatch, primeiro):
    d = disputa
    trancou, chegou = threading.Event(), threading.Event()
    papel_atual: ContextVar[str] = ContextVar("papel_us210")
    original = RepositorioResponsaveis.bloquear_cadastro

    def ordenar(self):
        if papel_atual.get() == primeiro:
            resultado = original(self)
            trancou.set()
            assert chegou.wait(timeout=10)
            return resultado
        assert trancou.wait(timeout=10)
        chegou.set()
        return original(self)

    monkeypatch.setattr(RepositorioResponsaveis, "bloquear_cadastro", ordenar)

    def executar(papel):
        papel_atual.set(papel)
        if papel == "conta":
            return enviar(d, d.dados)
        return enviar(d, {}, metodo="post", rota=f"{RESPONSAVEIS}/{d.c.responsavel.id}/desativacao")

    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(
            executor.map(executar, [primeiro, "desativacao" if primeiro == "conta" else "conta"])
        )
    assert [r.status_code for r in respostas] == ([200, 200] if primeiro == "conta" else [200, 404])
