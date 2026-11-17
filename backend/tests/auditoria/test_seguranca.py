import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.contexto import ContextoCondominio
from app.core.errors import ApiError
from app.db.session import get_session
from app.main import create_app
from app.modules.auditoria import repository, service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth import service as auth_service
from app.modules.auth.autorizacao import require_permission
from app.modules.auth.security import verificar_senha
from app.modules.unidades.models import Unidade
from tests.auditoria.conftest import SENHA

pytestmark = pytest.mark.postgres


def eventos(cenario, acao, *, usuario_id=None):
    with cenario.fabrica() as session:
        consulta = select(RegistroAuditoria).where(RegistroAuditoria.acao == acao)
        if usuario_id is not None:
            consulta = consulta.where(RegistroAuditoria.usuario_id == usuario_id)
        return list(session.scalars(consulta.order_by(RegistroAuditoria.id)))


def entrar(client, cenario, senha=SENHA):
    return client.post(
        "/api/v1/auth/login",
        json={
            "identificador": cenario.a.morador.email,
            "senha": senha,
        },
    )


def test_login_bem_sucedido_registra_um_evento_sem_tokens(client, cenario):
    resposta = entrar(client, cenario)
    assert resposta.status_code == 200
    [evento] = eventos(cenario, "seguranca.login", usuario_id=cenario.a.morador.id)
    assert evento.condominio_id == cenario.a.condominio.id
    assert evento.perfil == "morador"
    assert str(evento.ip) == "203.0.113.20"
    assert evento.recurso_id == cenario.a.morador.id
    assert evento.antes is None and evento.depois is None
    assert resposta.json()["access_token"] not in str(vars(evento))
    assert resposta.json()["refresh_token"] not in str(vars(evento))


def test_login_falho_persiste_apos_401(client, cenario):
    assert entrar(client, cenario, "senha_errada").status_code == 401
    [evento] = eventos(cenario, "seguranca.login_falho", usuario_id=cenario.a.morador.id)
    assert evento.condominio_id is None
    assert str(evento.ip) == "203.0.113.20"
    assert evento.depois is None


def test_login_inexistente_e_bloqueio_nao_expoem_identificador(client, cenario):
    identificador = f"{uuid.uuid4().hex}@inexistente.test"
    with cenario.fabrica() as session:
        ultimo = session.scalar(select(func.max(RegistroAuditoria.id))) or 0
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={
                    "identificador": identificador,
                    "senha": "errada",
                },
            ).status_code
            == 401
        )
    bloqueio = client.post(
        "/api/v1/auth/login",
        json={
            "identificador": identificador,
            "senha": "errada",
        },
    )
    assert bloqueio.status_code == 429
    assert int(bloqueio.headers["Retry-After"]) > 0
    with cenario.fabrica() as session:
        novos = list(
            session.scalars(
                select(RegistroAuditoria)
                .where(RegistroAuditoria.id > ultimo)
                .order_by(RegistroAuditoria.id)
            )
        )
        assert [e.acao for e in novos] == ["seguranca.login_falho"] * 5 + [
            "seguranca.login_bloqueado"
        ]
        assert all(e.usuario_id is None and e.condominio_id is None for e in novos)
        assert identificador not in str([vars(e) for e in novos])


def test_negacao_registra_um_evento_com_identidade_real(client, cenario):
    headers = {
        **cenario.a.cabecalho_de("morador"),
        "X-Usuario-Id": str(cenario.b.administracao.id),
        "X-Condominio-Id": str(cenario.b.condominio.id),
        "X-Perfil": "plataforma",
        "X-Forwarded-For": "198.51.100.77",
    }
    assert client.post("/api/v1/funcionarios", headers=headers, json={}).status_code == 403
    [evento] = eventos(cenario, "seguranca.acesso_negado", usuario_id=cenario.a.morador.id)
    assert evento.condominio_id == cenario.a.condominio.id
    assert evento.perfil == "morador"
    assert str(evento.ip) == "203.0.113.20"
    assert evento.depois == {
        "status_http": 403,
        "permissao": "funcionarios:criar",
        "rota": "/funcionarios",
        "metodo": "POST",
    }
    assert eventos(cenario, "seguranca.acesso_negado", usuario_id=cenario.b.administracao.id) == []


def test_404_de_unidade_alheia_e_inexistente_sao_iguais_e_auditados(client, cenario):
    headers = cenario.a.cabecalho_de("administracao")
    respostas = [
        client.get(f"/api/v1/unidades/{id_}/moradores", headers=headers)
        for id_ in (cenario.b.unidade_101.id, uuid.uuid4())
    ]
    assert [r.status_code for r in respostas] == [404, 404]
    assert respostas[0].json() == respostas[1].json()
    registros = eventos(
        cenario, "seguranca.acesso_cross_tenant", usuario_id=cenario.a.administracao.id
    )
    assert len(registros) == 2
    assert all(e.condominio_id == cenario.a.condominio.id for e in registros)
    assert all(e.depois["motivo"] == "recurso_fora_do_escopo_ou_inexistente" for e in registros)
    assert (
        eventos(cenario, "seguranca.acesso_cross_tenant", usuario_id=cenario.b.administracao.id)
        == []
    )


def test_rota_desconhecida_nao_e_tratada_como_acesso_cross_tenant(client, cenario):
    assert (
        client.get(
            "/api/v1/rota-inexistente", headers=cenario.a.cabecalho_de("morador")
        ).status_code
        == 404
    )
    assert eventos(cenario, "seguranca.acesso_cross_tenant", usuario_id=cenario.a.morador.id) == []


def test_seguranca_sobrevive_ao_rollback_da_requisicao(cenario):
    app = create_app()

    @app.post("/api/v1/auditoria-teste/negacao")
    def negar(
        contexto: Annotated[ContextoCondominio, Depends(require_permission("estrutura:editar"))],
        session: Annotated[Session, Depends(get_session)],
    ):
        unidade = session.get(Unidade, cenario.a.unidade_101.id)
        assert unidade is not None
        unidade.identificacao = "não deve persistir"
        session.flush()
        raise ApiError(403, "forbidden", "Você não tem permissão para realizar esta ação.")

    with TestClient(app) as client:
        resposta = client.post(
            "/api/v1/auditoria-teste/negacao", headers=cenario.a.cabecalho_de("administracao")
        )
    assert resposta.status_code == 403
    [evento] = eventos(cenario, "seguranca.acesso_negado", usuario_id=cenario.a.administracao.id)
    assert evento.condominio_id == cenario.a.condominio.id
    with cenario.fabrica() as session:
        assert session.get(Unidade, cenario.a.unidade_101.id).identificacao != "não deve persistir"


def test_seguranca_independente_sanitiza_e_nao_confirma_sessao_principal(cenario):
    with cenario.fabrica() as session:
        session.get(Unidade, cenario.a.unidade_101.id).identificacao = "a reverter"
        session.flush()
        service.registrar_evento_seguranca(
            acao="seguranca.chave_invalida",
            usuario_id=cenario.a.morador.id,
            condominio_id=cenario.a.condominio.id,
            perfil="morador",
            ip="203.0.113.7",
            detalhe={"dados": [{"codigo": "NUNCA", "tentativas": 1}]},
        )
        session.rollback()
    [evento] = eventos(cenario, "seguranca.chave_invalida", usuario_id=cenario.a.morador.id)
    assert evento.depois == {"dados": [{"tentativas": 1}]}
    with cenario.fabrica() as session:
        assert session.get(Unidade, cenario.a.unidade_101.id).identificacao != "a reverter"


def test_falha_da_auditoria_de_seguranca_preserva_resposta_e_nao_expoe_erro(
    client, cenario, monkeypatch, caplog
):
    segredo = "segredo-na-excecao-do-driver"

    def falhar(*args, **kwargs):
        raise RuntimeError(segredo)

    monkeypatch.setattr(repository, "inserir", falhar)
    with caplog.at_level(logging.ERROR, logger="app.modules.auditoria.service"):
        assert entrar(client, cenario, "errada").status_code == 401
        assert (
            client.post(
                "/api/v1/funcionarios", headers=cenario.a.cabecalho_de("morador"), json={}
            ).status_code
            == 403
        )
    assert len([r for r in caplog.records if r.name == "app.modules.auditoria.service"]) == 2
    assert segredo not in caplog.text
    assert eventos(cenario, "seguranca.login_falho", usuario_id=cenario.a.morador.id) == []


def test_falha_ao_abrir_sessao_de_seguranca_e_contida(caplog):
    def indisponivel():
        raise RuntimeError("credencial-privada")

    with caplog.at_level(logging.ERROR, logger="app.modules.auditoria.service"):
        service.registrar_evento_seguranca(
            acao="seguranca.login_falho",
            usuario_id=None,
            condominio_id=None,
            ip=None,
            session_factory=indisponivel,
        )
    assert "Falha ao persistir" in caplog.text
    assert "credencial-privada" not in caplog.text


def test_login_nao_confirma_rehash_quando_evento_transacional_falha(client, cenario, monkeypatch):
    def falhar(*args, **kwargs):
        raise RuntimeError("falha de auditoria")

    hash_anterior = cenario.a.morador.senha_hash
    monkeypatch.setattr(auth_service, "precisa_rehash", lambda _: True)
    monkeypatch.setattr(service, "registrar_acao", falhar)
    assert entrar(client, cenario).status_code == 500
    assert eventos(cenario, "seguranca.login", usuario_id=cenario.a.morador.id) == []
    with cenario.fabrica() as session:
        usuario = session.get(type(cenario.a.morador), cenario.a.morador.id)
        assert usuario.senha_hash == hash_anterior
        assert verificar_senha(SENHA, usuario.senha_hash)


def test_contextos_de_requisicoes_concorrentes_nao_se_misturam(client, cenario):
    def negar(predio):
        return client.post(
            "/api/v1/funcionarios", headers=predio.cabecalho_de("morador"), json={}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(negar, [cenario.a, cenario.b])) == [403, 403]
    for predio in (cenario.a, cenario.b):
        [evento] = eventos(cenario, "seguranca.acesso_negado", usuario_id=predio.morador.id)
        assert evento.condominio_id == predio.condominio.id
        assert evento.perfil == "morador"


def test_falha_no_commit_de_seguranca_reverte_evento_e_nao_propaga(cenario, caplog):
    rollbacks = []

    class SessaoComFalha(Session):
        def commit(self) -> None:
            raise RuntimeError("segredo_do_driver")

        def rollback(self) -> None:
            rollbacks.append(True)
            super().rollback()

    fabrica = sessionmaker(bind=cenario.fabrica.kw["bind"], class_=SessaoComFalha)
    with caplog.at_level(logging.ERROR, logger="app.modules.auditoria.service"):
        service.registrar_evento_seguranca(
            acao="seguranca.login_falho",
            usuario_id=cenario.a.morador.id,
            condominio_id=None,
            ip=None,
            session_factory=fabrica,
        )
    assert rollbacks
    assert eventos(cenario, "seguranca.login_falho", usuario_id=cenario.a.morador.id) == []
    assert "segredo_do_driver" not in caplog.text


def test_lock_da_transacao_original_nao_prende_a_auditoria(cenario, caplog):
    # Só o ADM fictício desta fixture, sem vínculos nem eventos prévios.
    with cenario.fabrica() as principal:
        principal.delete(principal.get(type(cenario.a.adm), cenario.a.adm.id))
        principal.flush()
        with caplog.at_level(logging.ERROR, logger="app.modules.auditoria.service"):
            service.registrar_evento_seguranca(
                acao="seguranca.login_falho",
                usuario_id=cenario.a.adm.id,
                condominio_id=None,
                ip=None,
            )
        principal.rollback()
    assert "Falha ao persistir" in caplog.text
    assert eventos(cenario, "seguranca.login_falho", usuario_id=cenario.a.adm.id) == []


def test_rehash_bem_sucedido_e_um_unico_evento_sao_confirmados(client, cenario, monkeypatch):
    hash_anterior = cenario.a.morador.senha_hash
    monkeypatch.setattr(auth_service, "precisa_rehash", lambda _: True)
    assert entrar(client, cenario).status_code == 200
    assert len(eventos(cenario, "seguranca.login", usuario_id=cenario.a.morador.id)) == 1
    with cenario.fabrica() as session:
        usuario = session.get(type(cenario.a.morador), cenario.a.morador.id)
        assert usuario.senha_hash != hash_anterior
        assert verificar_senha(SENHA, usuario.senha_hash)
