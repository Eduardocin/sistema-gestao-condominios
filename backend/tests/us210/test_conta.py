import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.tempo import get_relogio
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auth.security import verificar_senha
from app.modules.condominios.models import VinculoCondominio
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de, vincular
from tests.us210.conftest import ACAO, CONTA, RESPONSAVEIS, SENHA, dados, email_novo

pytestmark = pytest.mark.postgres


def conta(session, caso):
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.condominio_id == caso.a.condominio.id,
            VinculoCondominio.perfil == "funcionario",
        )
    )
    return session.get(Usuario, vinculo.usuario_id), vinculo


def eventos(session, caso, acao=ACAO):
    return list(
        session.scalars(
            select(RegistroAuditoria)
            .where(
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
                RegistroAuditoria.acao == acao,
            )
            .order_by(RegistroAuditoria.id)
        )
    )


def login(client, payload):
    return client.post(
        "/api/v1/auth/login", json={"identificador": payload["login"], "senha": payload["senha"]}
    )


def test_cria_consulta_login_e_audita_sem_segredos(client, session, caso, caplog):
    assert client.get(CONTA, headers=caso.a.headers).status_code == 404
    payload = dados(caso)
    resposta = client.put(CONTA, headers=caso.a.headers, json=payload)
    assert resposta.status_code == 200, resposta.text
    assert set(resposta.json()) == {"login", "atualizada_em"}
    assert resposta.json()["atualizada_em"] is not None
    assert client.get(CONTA, headers=caso.a.headers).json() == resposta.json()
    usuario, vinculo = conta(session, caso)
    assert usuario.tipo_cadastro is None and not usuario.administrador_plataforma
    assert usuario.telefone is None and usuario.documento is None
    assert usuario.ativo and vinculo.ativo and vinculo.unidade_id is None
    assert usuario.sessao_versao == 1 and verificar_senha(SENHA, usuario.senha_hash)
    autenticacao = login(client, payload)
    assert autenticacao.status_code == 200
    assert autenticacao.json()["condominio"]["perfil"] == "funcionario"
    evento = eventos(session, caso)[0]
    assert evento.recurso_id == usuario.id and evento.usuario_id == caso.a.administracao.id
    assert evento.responsavel_nome == "Síndica Original"
    for segredo in (SENHA, usuario.senha_hash, autenticacao.json()["access_token"]):
        assert segredo not in str(evento.antes) + str(evento.depois) + resposta.text + caplog.text


@pytest.mark.parametrize("troca", ["login", "senha", "ambos"])
def test_troca_preserva_identidade_e_invalida_tokens(client, session, caso, troca):
    momento = [datetime(2030, 1, 1, tzinfo=UTC)]
    client.app.dependency_overrides[get_relogio] = lambda: lambda: momento[0]
    payload = dados(caso)
    original = client.put(CONTA, headers=caso.a.headers, json=payload)
    usuario, vinculo = conta(session, caso)
    ids = usuario.id, vinculo.id
    tokens = login(client, payload).json()
    novo = dict(payload)
    if troca in {"login", "ambos"}:
        novo["login"] = email_novo()
    if troca in {"senha", "ambos"}:
        novo["senha"] = "NovaSenhaPortaria210"
    momento[0] += timedelta(minutes=1)
    resposta = client.put(CONTA, headers=caso.a.headers, json=novo)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["atualizada_em"] != original.json()["atualizada_em"]
    session.expire_all()
    usuario, vinculo = conta(session, caso)
    assert (usuario.id, vinculo.id) == ids and usuario.sessao_versao == 2
    assert len(eventos(session, caso)) == 2
    assert (
        client.get("/api/v1/auth/me", headers=cabecalho(tokens["access_token"])).status_code == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    assert login(client, payload).status_code == 401
    assert login(client, novo).status_code == 200


def test_idempotencia_normalizada_preserva_hash_data_sessao_e_eventos(client, session, caso):
    payload = dados(caso)
    original = client.put(CONTA, headers=caso.a.headers, json=payload)
    usuario, _ = conta(session, caso)
    hash_original = usuario.senha_hash
    tokens = login(client, payload).json()
    repetido = client.put(
        CONTA,
        headers=caso.a.headers,
        json={**payload, "login": "  " + payload["login"].upper() + "  "},
    )
    assert repetido.json() == original.json()
    session.refresh(usuario)
    assert usuario.sessao_versao == 1 and usuario.senha_hash == hash_original
    assert len(eventos(session, caso)) == 1
    assert (
        client.get("/api/v1/auth/me", headers=cabecalho(tokens["access_token"])).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("senha", ["curta1", "SemNumero", "123456789", "conta210@example.test"])
def test_senha_invalida_nao_persiste(client, session, caso, senha):
    resposta = client.put(
        CONTA, headers=caso.a.headers, json=dados(caso, login="conta210@example.test", senha=senha)
    )
    assert resposta.status_code == 422
    assert eventos(session, caso) == []
    assert client.get(CONTA, headers=caso.a.headers).status_code == 404


@pytest.mark.parametrize("campo", ["condominio_id", "usuario_id", "ativo"])
def test_campos_protegidos_rejeitados(client, caso, campo):
    assert (
        client.put(
            CONTA, headers=caso.a.headers, json=dados(caso, **{campo: str(uuid.uuid4())})
        ).status_code
        == 422
    )


@pytest.mark.parametrize("existente", ["pessoal", "plataforma", "compartilhada"])
def test_email_indisponivel_nao_apropria_conta(client, session, caso, existente):
    if existente == "compartilhada":
        payload = dados(caso, lado="b")
        assert client.put(CONTA, headers=caso.b.headers, json=payload).status_code == 200
        email = payload["login"]
    else:
        alvo = criar_usuario(session, adm=existente == "plataforma")
        alvo.tipo_cadastro = "morador" if existente == "pessoal" else None
        session.commit()
        email = alvo.email
    antes = {
        u.id: (u.email, u.senha_hash, u.sessao_versao) for u in session.scalars(select(Usuario))
    }
    resposta = client.put(CONTA, headers=caso.a.headers, json=dados(caso, login=email))
    assert (
        resposta.status_code == 409 and resposta.json()["error"]["reason"] == "login_indisponivel"
    )
    assert {
        u.id: (u.email, u.senha_hash, u.sessao_versao) for u in session.scalars(select(Usuario))
    } == antes
    assert client.get(CONTA, headers=caso.a.headers).status_code == 404


def test_troca_para_email_ocupado_reverte_tudo(client, session, caso):
    original = client.put(CONTA, headers=caso.a.headers, json=dados(caso)).json()
    usuario, _ = conta(session, caso)
    hash_original = usuario.senha_hash
    resposta = client.put(
        CONTA, headers=caso.a.headers, json=dados(caso, login=caso.b.administracao.email)
    )
    assert resposta.status_code == 409
    assert client.get(CONTA, headers=caso.a.headers).json() == original
    session.refresh(usuario)
    assert usuario.sessao_versao == 1 and usuario.senha_hash == hash_original
    assert len(eventos(session, caso)) == 1


@pytest.mark.parametrize(
    "estado",
    [
        "usuario_inativo",
        "vinculo_inativo",
        "pessoal",
        "plataforma",
        "sem_senha",
        "telefone",
        "documento",
        "outra_associacao",
        "unidade",
    ],
)
def test_legado_incompativel_nao_e_adotado_ou_substituido(client, session, caso, estado):
    assert client.put(CONTA, headers=caso.a.headers, json=dados(caso)).status_code == 200
    usuario, vinculo = conta(session, caso)
    if estado == "usuario_inativo":
        usuario.ativo = False
    elif estado == "vinculo_inativo":
        vinculo.ativo = False
    elif estado == "pessoal":
        usuario.tipo_cadastro = "morador"
    elif estado == "plataforma":
        usuario.administrador_plataforma = True
    elif estado == "sem_senha":
        usuario.senha_hash = None
    elif estado == "telefone":
        usuario.telefone = "11987654321"
    elif estado == "documento":
        usuario.documento = "52998224725"
    elif estado == "outra_associacao":
        vincular(session, usuario, caso.b.condominio, perfil="morador")
    else:
        unidade = Unidade(condominio_id=caso.a.condominio.id, identificacao="101")
        session.add(unidade)
        session.flush()
        vinculo.unidade_id = unidade.id
    session.commit()
    respostas = [
        client.get(CONTA, headers=caso.a.headers),
        client.put(CONTA, headers=caso.a.headers, json=dados(caso, login=email_novo())),
    ]
    for resposta in respostas:
        assert resposta.status_code == 409
        assert resposta.json()["error"]["reason"] == "conta_compartilhada_incompativel"
    assert len(eventos(session, caso)) == 1


def test_legado_compativel_data_nula_ate_troca_efetiva(client, session, caso):
    payload = dados(caso)
    assert client.put(CONTA, headers=caso.a.headers, json=payload).status_code == 200
    _, vinculo = conta(session, caso)
    vinculo.credenciais_atualizadas_em = None
    session.flush()
    assert client.get(CONTA, headers=caso.a.headers).json()["atualizada_em"] is None
    assert client.put(CONTA, headers=caso.a.headers, json=payload).json()["atualizada_em"] is None
    assert (
        client.put(CONTA, headers=caso.a.headers, json=dados(caso, senha="OutraSenha210")).json()[
            "atualizada_em"
        ]
        is not None
    )


@pytest.mark.parametrize("perfil", [None, "morador", "funcionario", "plataforma"])
def test_perfis_negados_em_todas_as_novas_rotas(client, session, caso, perfil):
    headers = {}
    if perfil:
        usuario = criar_usuario(session, adm=perfil == "plataforma")
        if perfil != "plataforma":
            vincular(session, usuario, caso.a.condominio, perfil=perfil)
        headers = cabecalho(
            token_de(
                usuario, None if perfil == "plataforma" else caso.a.condominio.id, perfil=perfil
            )
        )
    esperado = 403 if perfil else 401
    session.commit()
    assert client.get(CONTA, headers=headers).status_code == esperado
    assert client.put(CONTA, headers=headers, json=dados(caso)).status_code == esperado
    rota = f"{RESPONSAVEIS}/{caso.a.responsavel.id}"
    assert client.put(rota, headers=headers, json={"nome": "Outro"}).status_code == esperado
    assert client.post(rota + "/desativacao", headers=headers, json={}).status_code == esperado


@pytest.mark.parametrize("status", ["pendente", "rejeitado", "desativado"])
def test_conta_exige_condominio_ativo(client, session, caso, status):
    caso.a.condominio.status = status
    caso.a.condominio.motivo_rejeicao = "Documentação" if status == "rejeitado" else None
    session.commit()
    assert client.get(CONTA, headers=caso.a.headers).status_code == 403
    assert client.put(CONTA, headers=caso.a.headers, json=dados(caso)).status_code == 403


@pytest.mark.parametrize("tipo", ["ausente", "inexistente", "inativo", "alheio"])
def test_responsavel_validado_antes_da_criacao(client, session, caso, tipo):
    payload = dados(caso)
    esperado = 404
    if tipo == "ausente":
        del payload["responsavel_id"]
        esperado = 422
    elif tipo == "inexistente":
        payload["responsavel_id"] = str(uuid.uuid4())
    elif tipo == "inativo":
        caso.a.responsavel.ativo = False
        session.commit()
    else:
        payload["responsavel_id"] = str(caso.b.responsavel.id)
    assert client.put(CONTA, headers=caso.a.headers, json=payload).status_code == esperado
    assert client.get(CONTA, headers=caso.a.headers).status_code == 404


def test_contas_dos_dois_condominios_sao_independentes(client, caso):
    assert client.put(CONTA, headers=caso.a.headers, json=dados(caso)).status_code == 200
    assert client.get(CONTA, headers=caso.b.headers).status_code == 404
    assert client.put(CONTA, headers=caso.b.headers, json=dados(caso, lado="b")).status_code == 200
    assert client.get(CONTA, headers=caso.a.headers).json()["login"] == dados(caso)["login"]
    assert (
        client.get(CONTA, headers=caso.b.headers).json()["login"] == dados(caso, lado="b")["login"]
    )


@pytest.mark.parametrize("criacao", [True, False])
@pytest.mark.parametrize("falha", ["auditoria", "commit"])
def test_rollback_integral(client, session, caso, monkeypatch, criacao, falha):
    original = None
    if not criacao:
        original = client.put(CONTA, headers=caso.a.headers, json=dados(caso)).json()

    def falhar(*args, **kwargs):
        raise RuntimeError("Falha simulada US-210")

    with monkeypatch.context() as m:
        if falha == "auditoria":
            m.setattr(auditoria, "registrar_acao", falhar)
        else:
            m.setattr(session, "commit", falhar)
        resposta = client.put(
            CONTA, headers=caso.a.headers, json=dados(caso, senha="SenhaAlterada210")
        )
    assert resposta.status_code == 500
    consulta = client.get(CONTA, headers=caso.a.headers)
    assert consulta.status_code == (404 if criacao else 200)
    if original:
        assert consulta.json() == original
        usuario, _ = conta(session, caso)
        assert usuario.sessao_versao == 1 and verificar_senha(SENHA, usuario.senha_hash)
    assert len(eventos(session, caso)) == (0 if criacao else 1)
