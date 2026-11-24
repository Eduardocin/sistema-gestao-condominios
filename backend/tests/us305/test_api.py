import uuid

import pytest
from sqlalchemy import select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.unidades.models import MoradorUnidade, PermissaoAba
from tests.us305.conftest import ACAO, SENHA, desfazer, headers_morador, morador, rota

pytestmark = pytest.mark.postgres


def eventos(session, caso):
    return list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
                RegistroAuditoria.acao == ACAO,
            )
        )
    )


@pytest.mark.parametrize("perfil", ["administracao", "morador"])
def test_desvincula_audita_revoga_e_preserva_historico(client, session, caso, perfil, caplog):
    codigo = caso.chave.codigo
    permissoes = list(
        session.scalars(
            select(PermissaoAba).where(PermissaoAba.morador_unidade_id == caso.alvo.associacao.id)
        )
    )
    abas = {p.aba: p.com_acesso for p in permissoes}
    sv = caso.alvo.usuario.sessao_versao
    resposta = desfazer(client, caso, perfil=perfil)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {
        "id": str(caso.alvo.associacao.id),
        "status": "desvinculado",
        "desvinculado_em": caso.momento.isoformat().replace("+00:00", "Z"),
        "chave_revogada": True,
    }
    session.expire_all()
    alvo = session.get(MoradorUnidade, caso.alvo.associacao.id)
    assert alvo.status == "desvinculado" and alvo.desvinculado_em == caso.momento
    executor = caso.a.administracao if perfil == "administracao" else caso.a.morador
    assert alvo.desvinculado_por_usuario_id == executor.id
    assert caso.alvo.usuario.ativo and caso.alvo.usuario.sessao_versao == sv
    assert not caso.alvo.vinculo.ativo and caso.chave.revogada_em == caso.momento
    assert {
        p.aba: p.com_acesso
        for p in session.scalars(
            select(PermissaoAba).where(PermissaoAba.morador_unidade_id == alvo.id)
        )
    } == abas
    evs = eventos(session, caso)
    assert len(evs) == 1
    e = evs[0]
    assert e.usuario_id == executor.id and e.perfil == perfil and e.recurso_id == alvo.id
    assert e.responsavel_nome == (caso.responsavel.nome if perfil == "administracao" else None)
    assert e.depois["unidade_id"] == str(caso.a.unidade_101.id)
    assert e.depois["vinculo_condominio_desativado"] and e.depois["chave_revogada"]
    assert e.depois["chave_id"] == str(caso.chave.id)
    assert codigo not in resposta.text + str(e.antes) + str(e.depois) + caplog.text
    assert not list(
        session.scalars(
            select(RegistroAuditoria).where(
                RegistroAuditoria.acao == "chave.revogar",
                RegistroAuditoria.condominio_id == caso.a.condominio.id,
            )
        )
    )
    assert (
        client.get(
            f"/api/v1/minhas-unidades/{caso.a.unidade_101.id}",
            headers=caso.a.cabecalho_de("morador"),
        ).status_code
        == 200
    )


def test_repeticao_no_escopo_e_409_sem_duplicar_evento(client, session, caso):
    assert desfazer(client, caso).status_code == 200
    repetido = desfazer(client, caso)
    assert repetido.status_code == 409 and repetido.json()["error"]["reason"] == "ja_desvinculado"
    assert len(eventos(session, caso)) == 1


def tokens_do_alvo(client, caso):
    sessao = client.post(
        "/api/v1/auth/login", json={"identificador": caso.alvo.usuario.email, "senha": SENHA}
    ).json()
    return client.post(
        "/api/v1/auth/selecionar-condominio",
        headers={"Authorization": "Bearer " + sessao["access_token"]},
        json={"condominio_id": str(caso.a.condominio.id)},
    ).json()


@pytest.mark.parametrize("outra_unidade", [False, True])
def test_mesmo_jwt_e_refresh_respeitam_revogacao_e_outros_condominios(
    client, session, caso, outra_unidade
):
    externo = morador(session, caso.b, usuario=caso.alvo.usuario, gestor=True)
    if outra_unidade:
        morador(session, caso.a, unidade=caso.a.unidade_102, usuario=caso.alvo.usuario, gestor=True)
    session.commit()
    tokens = tokens_do_alvo(client, caso)
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert desfazer(client, caso).status_code == 200
    session.expire_all()
    assert externo.vinculo.ativo and caso.alvo.usuario.ativo
    assert caso.alvo.vinculo.ativo is outra_unidade
    assert caso.alvo.usuario.sessao_versao == 1
    assert client.get(
        f"/api/v1/minhas-unidades/{caso.a.unidade_101.id}", headers=headers
    ).status_code == (404 if outra_unidade else 403)
    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == (200 if outra_unidade else 401)
    selecionar = client.post(
        "/api/v1/auth/selecionar-condominio",
        headers=headers,
        json={"condominio_id": str(caso.a.condominio.id)},
    )
    assert selecionar.status_code == (200 if outra_unidade else 404)
    assert (
        client.post(
            "/api/v1/auth/selecionar-condominio",
            headers=headers,
            json={"condominio_id": str(caso.b.condominio.id)},
        ).status_code
        == 200
    )
    if outra_unidade:
        items = client.get("/api/v1/minhas-unidades", headers=headers).json()["items"]
        assert [i["id"] for i in items] == [str(caso.a.unidade_102.id)]


@pytest.mark.parametrize("perfil", ["funcionario", "plataforma", None])
def test_perfis_negados(client, caso, perfil):
    headers = caso.a.cabecalho_de(perfil) if perfil else {}
    resposta = client.post(
        rota(caso.a.unidade_101.id, caso.alvo.associacao.id),
        headers=headers,
        json={"responsavel_id": str(caso.responsavel.id)},
    )
    assert resposta.status_code == (403 if perfil else 401)


@pytest.mark.parametrize("status", ["pendente", "rejeitado", "desativado"])
def test_condominio_nao_ativo(client, session, caso, status):
    caso.a.condominio.status = status
    caso.a.condominio.motivo_rejeicao = "Documento" if status == "rejeitado" else None
    session.commit()
    assert desfazer(client, caso).status_code == 403


@pytest.mark.parametrize("tipo", ["ausente", "invalido", "inexistente", "inativo", "alheio"])
def test_responsavel_administrativo(client, session, caso, tipo):
    corpo = {"responsavel_id": str(caso.responsavel.id)}
    esperado = 404
    if tipo == "ausente":
        corpo = {}
        esperado = 422
    elif tipo == "invalido":
        corpo["responsavel_id"] = "invalido"
        esperado = 422
    elif tipo == "inexistente":
        corpo["responsavel_id"] = str(uuid.uuid4())
    elif tipo == "inativo":
        caso.responsavel.ativo = False
        session.commit()
    else:
        corpo["responsavel_id"] = str(caso.outro.id)
    assert desfazer(client, caso, corpo=corpo).status_code == esperado
    session.expire_all()
    assert caso.alvo.associacao.status == "ativo" and caso.chave.revogada_em is None


def test_morador_sem_aba_autodesvinculacao_e_simulacao_administrativa(client, session, caso):
    headers = headers_morador(caso.alvo.usuario, caso.a.condominio.id)
    assert (
        desfazer(
            client, caso, perfil="morador", headers=headers, associacao=caso.a.morador_unidade
        ).status_code
        == 403
    )
    assert (
        desfazer(client, caso, perfil="morador", associacao=caso.a.morador_unidade).status_code
        == 403
    )
    for corpo in ({"responsavel_id": str(caso.responsavel.id)}, {"responsavel_id": None}):
        assert desfazer(client, caso, perfil="morador", corpo=corpo).status_code == 422


@pytest.mark.parametrize("campo", ["condominio_id", "usuario_id", "status", "desvinculado_em"])
def test_campos_extras(client, caso, campo):
    assert (
        desfazer(
            client, caso, corpo={"responsavel_id": str(caso.responsavel.id), campo: "invalido"}
        ).status_code
        == 422
    )


def test_escopos_cruzados_e_unidade_inativa(client, session, caso):
    assert desfazer(client, caso, unidade=caso.b.unidade_101.id).status_code == 404
    vizinho = morador(session, caso.a, unidade=caso.a.unidade_102, gestor=True)
    session.commit()
    assert (
        desfazer(client, caso, associacao=vizinho.associacao, perfil="morador").status_code == 404
    )
    assert (
        desfazer(client, caso, unidade=caso.a.unidade_102.id, perfil="morador").status_code == 404
    )
    caso.a.unidade_101.ativo = False  # Estado legado: não é produzido pela gestão da estrutura.
    session.commit()
    assert desfazer(client, caso).status_code == 409


@pytest.mark.parametrize("outro_gestor", [False, True])
def test_ultimo_gestor_de_unidade_ocupada(client, session, caso, outro_gestor):
    if outro_gestor:
        morador(session, caso.a, gestor=True)
        session.commit()
    resposta = desfazer(client, caso, associacao=caso.a.morador_unidade)
    assert resposta.status_code == (200 if outro_gestor else 409)
    if not outro_gestor:
        assert resposta.json()["error"]["reason"] == "ultimo_usuarios"


@pytest.mark.parametrize("inativo", ["conta", "vinculo", "plataforma"])
def test_gestor_inefetivo_nao_conta_na_us304_e_us305(client, session, caso, inativo):
    ghost = morador(session, caso.a, gestor=True)
    if inativo == "conta":
        ghost.usuario.ativo = False
    elif inativo == "vinculo":
        ghost.vinculo.ativo = False
    else:
        ghost.usuario.administrador_plataforma = True
    session.commit()
    resposta = desfazer(client, caso, associacao=caso.a.morador_unidade)
    assert resposta.status_code == 409
    permissao = client.put(
        f"/api/v1/unidades/{caso.a.unidade_101.id}/moradores/{caso.a.morador_unidade.id}/permissoes",
        headers=caso.a.cabecalho_de("morador"),
        json={"abas": {"usuarios": False}},
    )
    assert permissao.status_code == 409 and permissao.json()["error"]["reason"] == "ultimo_usuarios"


def test_transferencia_previa_permite_desvincular_gestor(client, caso):
    resposta = client.put(
        f"/api/v1/unidades/{caso.a.unidade_101.id}/moradores/{caso.alvo.associacao.id}/permissoes",
        headers=caso.a.cabecalho_de("morador"),
        json={"abas": {"usuarios": True}},
    )
    assert resposta.status_code == 200
    assert desfazer(client, caso, associacao=caso.a.morador_unidade).status_code == 200


def test_unidade_vazia_nova_chave_e_primeiro_morador(client, session, caso):
    antigo_id = caso.alvo.associacao.id
    codigo = caso.chave.codigo
    assert desfazer(client, caso).status_code == 200
    assert (
        desfazer(client, caso, associacao=caso.a.morador_unidade, perfil="morador").status_code
        == 403
    )
    assert desfazer(client, caso, associacao=caso.a.morador_unidade).status_code == 200
    assert session.get(MoradorUnidade, antigo_id).status == "desvinculado"
    headers = headers_morador(caso.alvo.usuario, caso.a.condominio.id)
    assert (
        client.post("/api/v1/vinculos/chave", headers=headers, json={"chave": codigo}).status_code
        == 404
    )
    base = f"/api/v1/unidades/{caso.a.unidade_101.id}/chave"
    corpo = {"responsavel_id": str(caso.responsavel.id)}
    assert (
        client.post(
            base + "/regeneracao", headers=caso.a.cabecalho_de("administracao"), json=corpo
        ).status_code
        == 409
    )
    nova = client.post(base, headers=caso.a.cabecalho_de("administracao"), json=corpo)
    assert nova.status_code == 201
    assert (
        client.post(
            "/api/v1/vinculos/chave", headers=headers, json={"chave": nova.json()["codigo"]}
        ).status_code
        == 201
    )
    session.expire_all()
    atual = session.scalar(
        select(MoradorUnidade).where(
            MoradorUnidade.usuario_id == caso.alvo.usuario.id,
            MoradorUnidade.unidade_id == caso.a.unidade_101.id,
            MoradorUnidade.status == "ativo",
        )
    )
    assert atual.id != antigo_id and caso.alvo.vinculo.ativo
    assert all(
        session.scalars(
            select(PermissaoAba.com_acesso).where(PermissaoAba.morador_unidade_id == atual.id)
        )
    )


def test_sem_chave_nao_impede_desvinculacao(client, session, caso):
    caso.chave.revogada_em = caso.momento
    session.commit()
    resposta = desfazer(client, caso)
    assert resposta.status_code == 200 and not resposta.json()["chave_revogada"]


def test_legado_ocupado_sem_gestor_nao_ganha_contorno_administrativo(client, session, caso):
    aba = session.get(PermissaoAba, (caso.a.morador_unidade.id, "usuarios"))
    aba.com_acesso = False
    session.commit()
    resposta = desfazer(client, caso)
    assert resposta.status_code == 409 and resposta.json()["error"]["reason"] == "ultimo_usuarios"


@pytest.mark.parametrize("falha", ["auditoria", "commit"])
def test_rollback_integral(client, session, caso, monkeypatch, falha):
    def falhar(*args, **kwargs):
        raise RuntimeError("Falha simulada US305")

    with monkeypatch.context() as m:
        if falha == "auditoria":
            m.setattr(auditoria, "registrar_acao", falhar)
        else:
            m.setattr(session, "commit", falhar)
        resposta = desfazer(client, caso)
    assert resposta.status_code == 500
    session.expire_all()
    assert caso.alvo.associacao.status == "ativo"
    assert caso.alvo.associacao.desvinculado_em is None
    assert caso.alvo.associacao.desvinculado_por_usuario_id is None
    assert caso.alvo.vinculo.ativo and caso.chave.revogada_em is None
    assert eventos(session, caso) == []
