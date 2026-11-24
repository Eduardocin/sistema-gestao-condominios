"""Testes sem banco externo para contratos HTTP e regras de escopo por unidade em visitantes."""

import uuid
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.contexto import ContextoCondominio
from app.core.permissoes import Perfil
from app.core.tempo import FUSO_CONDOMINIO, get_relogio
from app.db.session import get_session
from app.main import create_app
from app.modules.auth import autorizacao as auth_autorizacao
from app.modules.auth import repository as auth_repository
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO
from app.modules.auth.dependencies import get_current_context
from app.modules.unidades.models import Unidade
from app.modules.visitantes import service as visitantes_service
from app.modules.visitantes.models import Visitante


def _ctx(perfil: Perfil, usuario_id: uuid.UUID | None = None) -> ContextoCondominio:
    return ContextoCondominio(
        usuario_id=usuario_id or uuid.uuid4(),
        condominio_id=uuid.uuid4(),
        perfil=perfil,
        vinculo_id=uuid.uuid4(),
    )


def test_negacao_de_perfil_registra_evento_e_usa_mensagem_uniforme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    negacoes: list[str] = []
    monkeypatch.setattr(
        "app.modules.visitantes.router.registrar_negacao",
        lambda **kw: negacoes.append(kw["permissao"]),
        raising=False,
    )
    ctx_morador = _ctx(Perfil.MORADOR)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: MagicMock()
    app.dependency_overrides[get_current_context] = lambda: ctx_morador

    with TestClient(app) as client:
        resposta = client.get("/api/v1/visitas")

    assert resposta.status_code == 403
    assert resposta.json()["error"]["message"] == MENSAGEM_SEM_PERMISSAO
    assert len(negacoes) == 1


def test_busca_vazia_ou_espacos_nao_retorna_422_e_normaliza_para_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx_porteiro = _ctx(Perfil.FUNCIONARIO)
    capturadas: list[str | None] = []
    app = create_app()
    app.dependency_overrides[get_session] = lambda: MagicMock()
    app.dependency_overrides[get_current_context] = lambda: ctx_porteiro

    def _pagina_portaria(
        _self: object, _u: object, busca: str | None, _cpf: object, _p: int, _s: int
    ) -> tuple[list[object], int]:
        capturadas.append(busca)
        return [], 0

    def _pagina_visitas(
        _self: object, busca: str | None, _st: object, _p: int, _s: int
    ) -> tuple[list[object], int]:
        capturadas.append(busca)
        return [], 0

    monkeypatch.setattr(
        visitantes_service.RepositorioVisitantes, "pagina_portaria", _pagina_portaria
    )
    monkeypatch.setattr(visitantes_service.RepositorioVisitas, "pagina", _pagina_visitas)

    with TestClient(app) as client:
        r1 = client.get("/api/v1/portaria/visitantes?busca=")
        r2 = client.get("/api/v1/visitas?busca=%20%20")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert capturadas == [None, None]


def test_comorador_da_mesma_unidade_ve_cpf_edita_e_cancela(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    autor_id = uuid.uuid4()
    comorador_id = uuid.uuid4()
    ctx = _ctx(Perfil.MORADOR, usuario_id=comorador_id)
    unidade_id = uuid.uuid4()
    visitante = Visitante(
        id=uuid.uuid4(),
        condominio_id=ctx.condominio_id,
        unidade_id=unidade_id,
        cadastrado_por_usuario_id=autor_id,
        nome="Carlos Souza",
        cpf="52998224725",
        idade=35,
        observacoes="Carro prata",
        entrada_prevista=date(2030, 4, 1),
        saida_prevista=date(2030, 4, 2),
        avulso=False,
    )

    session = MagicMock()
    monkeypatch.setattr(auth_autorizacao, "garantir_aba_da_unidade", lambda *_a, **_kw: None)
    monkeypatch.setattr(visitantes_service, "garantir_aba_da_unidade", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        auth_repository,
        "obter_unidade",
        lambda *_a, **_kw: Unidade(
            id=unidade_id, condominio_id=ctx.condominio_id, identificacao="101", ativo=True
        ),
    )
    monkeypatch.setattr(
        visitantes_service.RepositorioVisitantes, "obter", lambda _s, _id: visitante
    )
    monkeypatch.setattr(
        visitantes_service.RepositorioVisitantes, "bloquear", lambda _s, _id: visitante
    )
    monkeypatch.setattr(
        visitantes_service.RepositorioVisitas, "tem_visita", lambda *_a, **_kw: False
    )
    monkeypatch.setattr(visitantes_service, "registrar_acao", lambda *_a, **_kw: None)

    momento = datetime(2030, 4, 1, 10, tzinfo=FUSO_CONDOMINIO)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_context] = lambda: ctx
    app.dependency_overrides[get_relogio] = lambda: lambda: momento

    with TestClient(app) as client:
        detalhe = client.get(f"/api/v1/visitantes/{visitante.id}")
        assert detalhe.status_code == 200
        assert detalhe.json()["cpf"] == "52998224725"
        assert detalhe.json()["observacoes"] == "Carro prata"

        edicao = client.put(
            f"/api/v1/visitantes/{visitante.id}",
            json={
                "nome": "Carlos Alberto Souza",
                "cpf": "52998224725",
                "idade": 36,
                "observacoes": "Carro azul",
                "entrada_prevista": "2030-04-01",
                "saida_prevista": "2030-04-03",
            },
        )
        assert edicao.status_code == 200
        assert edicao.json()["nome"] == "Carlos Alberto Souza"

        cancelamento = client.post(f"/api/v1/visitantes/{visitante.id}/cancelamento")
        assert cancelamento.status_code == 200
        assert cancelamento.json()["cancelado_em"] is not None
