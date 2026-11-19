"""Regressões defensivas da autorização durante a transação de permissões."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.main import create_app
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import VinculoCondominio
from app.modules.permissoes_aba.repository import RepositorioPermissoes, RepositorioUnidades
from app.modules.permissoes_aba.service import PermissoesAbaService
from app.modules.unidades.models import ABAS_MORADOR, MoradorUnidade, PermissaoAba
from tests.auditoria.conftest import Cenario
from tests.auditoria.conftest import cenario as cenario
from tests.isolamento.cenario import cabecalho, token_de

pytestmark = pytest.mark.postgres


@dataclass
class CasoPermissoes:
    cenario: Cenario
    contextos: tuple[ContextoCondominio, ContextoCondominio]
    moradores: tuple[uuid.UUID, uuid.UUID]

    @property
    def unidade_id(self):
        return self.cenario.a.unidade_101.id


@pytest.fixture
def caso(cenario):
    a, b = cenario.a, cenario.b
    with cenario.fabrica() as session:
        vinculo = VinculoCondominio(
            usuario_id=b.morador.id, condominio_id=a.condominio.id, perfil="morador", ativo=True
        )
        morador = MoradorUnidade(
            usuario_id=b.morador.id,
            condominio_id=a.condominio.id,
            unidade_id=a.unidade_101.id,
            origem="cadastro",
        )
        session.add_all([vinculo, morador])
        session.flush()
        contextos = (
            ContextoCondominio(a.morador.id, a.condominio.id, "morador", a.vinculo_morador.id),
            ContextoCondominio(b.morador.id, a.condominio.id, "morador", vinculo.id),
        )
        moradores = (a.morador_unidade.id, morador.id)
        for contexto, id_ in zip(contextos, moradores, strict=True):
            RepositorioPermissoes(session, contexto).definir(
                id_, {aba: True for aba in ABAS_MORADOR}, alterado_por=contexto.usuario_id
            )
        session.commit()
    # A fixture existente remove apenas os dados destes dois condomínios/usuários.
    return CasoPermissoes(cenario, contextos, moradores)


def alterar(caso, ator, alvo, abas):
    usuario = (caso.cenario.a.morador, caso.cenario.b.morador)[ator]
    rota = f"/api/v1/unidades/{caso.unidade_id}/moradores/{caso.moradores[alvo]}/permissoes"
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        return client.put(
            rota,
            headers=cabecalho(token_de(usuario, caso.contextos[ator].condominio_id)),
            json={"abas": abas},
        )


def estado(caso):
    with caso.cenario.fabrica() as session:
        abas = {
            (morador, aba): acesso
            for morador, aba, acesso in session.execute(
                select(
                    PermissaoAba.morador_unidade_id, PermissaoAba.aba, PermissaoAba.com_acesso
                ).where(PermissaoAba.morador_unidade_id.in_(caso.moradores))
            )
        }
        eventos = list(
            session.scalars(
                select(RegistroAuditoria)
                .where(
                    RegistroAuditoria.condominio_id == caso.contextos[0].condominio_id,
                    RegistroAuditoria.acao == "permissao_aba.alterar",
                )
                .order_by(RegistroAuditoria.id)
            )
        )
    return abas, eventos


def test_operacao_autorizada_preserva_contrato_e_auditoria(caso):
    resposta = alterar(caso, 0, 1, {"visitantes": False})
    assert resposta.status_code == 200
    assert set(resposta.json()) == {"id", "nome", "parentesco", "vinculado_em", "eu", "permissoes"}
    assert resposta.json()["permissoes"]["visitantes"] is False
    abas, eventos = estado(caso)
    assert abas[caso.moradores[1], "visitantes"] is False
    assert len(eventos) == 1
    assert eventos[0].usuario_id == caso.contextos[0].usuario_id


@pytest.mark.parametrize("ausente", [False, True])
def test_autorizacao_revogada_ou_ausente_recusa_sem_escrita(caso, ausente):
    with caso.cenario.fabrica() as session:
        permissao = session.get(PermissaoAba, (caso.moradores[0], "usuarios"))
        if ausente:
            session.delete(permissao)
        else:
            permissao.com_acesso = False
        session.commit()
    resposta = alterar(caso, 0, 1, {"visitantes": False})
    assert resposta.status_code == 403
    assert resposta.json() == {
        "error": {
            "code": "forbidden",
            "message": "Você não tem permissão para realizar esta ação.",
        }
    }
    abas, eventos = estado(caso)
    assert abas[caso.moradores[1], "visitantes"] is True
    assert eventos == []


def test_service_revalida_ator_e_reverte_transacao_na_recusa(caso):
    with caso.cenario.fabrica() as session:
        service = PermissoesAbaService(session, caso.contextos[0])
        # Contexto e objeto ORM pré-existentes não substituem a leitura atual do banco.
        antiga = session.get(PermissaoAba, (caso.moradores[0], "usuarios"))
        assert antiga.com_acesso is True
        with caso.cenario.fabrica() as outra:
            RepositorioPermissoes(outra, caso.contextos[1]).definir(
                caso.moradores[0], {"usuarios": False}, alterado_por=caso.contextos[1].usuario_id
            )
            outra.commit()
        with pytest.raises(ApiError) as erro:
            service.alterar_permissoes(
                caso.unidade_id, caso.moradores[1], {"visitantes": False}, ip=None
            )
        assert erro.value.status_code == 403
        assert not session.in_transaction()
    abas, eventos = estado(caso)
    assert abas[caso.moradores[1], "visitantes"] is True
    assert eventos == []


@pytest.mark.parametrize("primeira", ["revogacao", "alteracao"])
def test_alteracao_e_revogacao_respeitam_ordem_da_tranca(caso, monkeypatch, primeira):
    trancou, segundo_entrou = threading.Event(), threading.Event()
    original = RepositorioUnidades.bloquear
    primeiro_ator = 1 if primeira == "revogacao" else 0

    def bloquear(self, unidade_id):
        if self.contexto.usuario_id == caso.contextos[primeiro_ator].usuario_id:
            resultado = original(self, unidade_id)
            trancou.set()
            assert segundo_entrou.wait(timeout=10)
            return resultado
        segundo_entrou.set()
        return original(self, unidade_id)

    monkeypatch.setattr(RepositorioUnidades, "bloquear", bloquear)
    operacoes = (
        (1, 0, {"usuarios": False}),
        (0, 1, {"visitantes": False}),
    )
    if primeira == "alteracao":
        operacoes = operacoes[::-1]
    with ThreadPoolExecutor(max_workers=2) as executor:
        primeiro = executor.submit(alterar, caso, *operacoes[0])
        assert trancou.wait(timeout=10)
        segundo = executor.submit(alterar, caso, *operacoes[1])
        respostas = (primeiro.result(timeout=20), segundo.result(timeout=20))
    assert respostas[0].status_code == 200
    assert respostas[1].status_code == (403 if primeira == "revogacao" else 200)
    abas, eventos = estado(caso)
    assert abas[caso.moradores[0], "usuarios"] is False
    assert abas[caso.moradores[1], "usuarios"] is True
    assert abas[caso.moradores[1], "visitantes"] is (primeira == "revogacao")
    assert len(eventos) == (1 if primeira == "revogacao" else 2)
    if primeira == "revogacao":
        assert all(e.usuario_id == caso.contextos[1].usuario_id for e in eventos)


def test_regra_do_ultimo_morador_recusa_toda_a_alteracao(caso):
    assert alterar(caso, 0, 1, {"usuarios": False}).status_code == 200
    resposta = alterar(caso, 0, 0, {"usuarios": False, "visitantes": False})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "ultimo_usuarios"
    abas, eventos = estado(caso)
    assert abas[caso.moradores[0], "usuarios"] is True
    assert abas[caso.moradores[0], "visitantes"] is True
    assert len(eventos) == 1


def test_resposta_e_consulta_ignoram_permissao_antiga_no_orm(caso):
    with caso.cenario.fabrica() as session:
        antiga = session.get(PermissaoAba, (caso.moradores[1], "visitantes"))
        assert antiga.com_acesso is True
        saida = PermissoesAbaService(session, caso.contextos[0]).alterar_permissoes(
            caso.unidade_id, caso.moradores[1], {"visitantes": False}, ip=None
        )
        assert saida.permissoes["visitantes"] is False
        assert (
            RepositorioPermissoes(session, caso.contextos[0]).do_morador(caso.moradores[1])[
                "visitantes"
            ]
            is False
        )


def test_falha_apos_auditoria_reverte_alteracao_e_evento(caso, monkeypatch):
    original = auditoria.registrar_acao

    def falhar_apos_inserir(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Falha controlada após inserir auditoria")

    monkeypatch.setattr(auditoria, "registrar_acao", falhar_apos_inserir)
    with caso.cenario.fabrica() as session:
        with pytest.raises(RuntimeError):
            PermissoesAbaService(session, caso.contextos[0]).alterar_permissoes(
                caso.unidade_id, caso.moradores[1], {"visitantes": False}, ip=None
            )
        assert not session.in_transaction()
    abas, eventos = estado(caso)
    assert abas[caso.moradores[1], "visitantes"] is True
    assert eventos == []
