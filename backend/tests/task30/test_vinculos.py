import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.modules.auditoria import service as auditoria
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.condominios.models import VinculoCondominio
from app.modules.permissoes_aba.repository import RepositorioPermissoes
from app.modules.unidades.models import ABAS_MORADOR, MoradorUnidade, PermissaoAba
from app.modules.usuarios.models import TentativaChaveAcesso
from app.modules.vinculos import repository
from tests.isolamento.cenario import cabecalho, token_de
from tests.task30.conftest import ROTA, morador, vincular

pytestmark = pytest.mark.postgres


def associacoes(session, usuario):
    return list(
        session.scalars(select(MoradorUnidade).where(MoradorUnidade.usuario_id == usuario.id))
    )


def permissoes(session, morador_):
    return {
        p.aba: p.com_acesso
        for p in session.scalars(
            select(PermissaoAba).where(PermissaoAba.morador_unidade_id == morador_.id)
        )
    }


@pytest.mark.parametrize("formato", ["normal", "minusculas", "hifen", "espacos"])
def test_vinculo_imediato_sem_cid_e_sete_permissoes(client, session, caso, formato, caplog):
    codigo = caso.chaves[0].codigo
    entrada = {
        "normal": codigo,
        "minusculas": codigo.lower(),
        "hifen": f"{codigo[:5]}-{codigo[5:]}",
        "espacos": f" {codigo[:5].lower()} - {codigo[5:].lower()} ",
    }[formato]
    resposta = vincular(client, caso, chave_=entrada)
    assert resposta.status_code == 201, resposta.text
    assert resposta.json() == {
        "unidade": {
            "id": str(caso.a.unidade_102.id),
            "identificacao": caso.a.unidade_102.identificacao,
        },
        "condominio": {"id": str(caso.a.condominio.id), "nome": caso.a.condominio.nome},
    }
    assert resposta.headers["Location"] == f"/api/v1/minhas-unidades/{caso.a.unidade_102.id}"
    assert "token" not in resposta.text and codigo not in resposta.text
    (morador_,) = associacoes(session, caso.usuario)
    assert morador_.status == "ativo" and morador_.origem == "chave"
    assert permissoes(session, morador_) == dict.fromkeys(ABAS_MORADOR, True)
    vinculo = session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
    ).one()
    assert vinculo.perfil == "morador" and vinculo.ativo and vinculo.unidade_id is None
    assert caso.chaves[0].revogada_em is None
    tentativa = session.scalars(
        select(TentativaChaveAcesso).where(TentativaChaveAcesso.usuario_id == caso.usuario.id)
    ).one()
    assert tentativa.sucesso
    evento = session.scalars(
        select(RegistroAuditoria).where(RegistroAuditoria.recurso_id == morador_.id)
    ).one()
    assert evento.acao == "vinculo.aprovar" and evento.usuario_id == caso.usuario.id
    assert evento.perfil == "morador" and evento.condominio_id == caso.a.condominio.id
    assert str(evento.ip) == "203.0.113.27" and evento.criado_em
    assert codigo not in json.dumps([evento.antes, evento.depois]) and codigo not in caplog.text
    session.rollback()
    assert associacoes(session, caso.usuario)  # a transação foi confirmada pelo service


def test_duplicado_multiplas_unidades_e_condominios(client, session, caso):
    assert vincular(client, caso).status_code == 201
    resposta = vincular(client, caso)
    assert resposta.status_code == 409 and resposta.json()["error"]["reason"] == "ja_vinculado"
    for chave_ in caso.chaves[1:]:
        assert vincular(client, caso, chave_=chave_.codigo).status_code == 201
    assert len(associacoes(session, caso.usuario)) == 3
    vinculos = list(
        session.scalars(
            select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
        )
    )
    assert len(vinculos) == 2 and all(v.unidade_id is None for v in vinculos)
    assert all(chave_.revogada_em is None for chave_ in caso.chaves)


def test_mesma_chave_reutilizada_por_segundo_morador(client, session, caso):
    assert vincular(client, caso).status_code == 201
    outro = morador(session)
    session.commit()
    assert vincular(client, caso, headers=cabecalho(token_de(outro, None))).status_code == 201
    (vinculo,) = associacoes(session, outro)
    assert permissoes(session, vinculo) == {aba: aba != "usuarios" for aba in ABAS_MORADOR}
    assert caso.chaves[0].revogada_em is None


def test_condominio_da_chave_prevalece_sobre_cid_selecionado(client, session, caso):
    assert vincular(client, caso).status_code == 201
    headers = cabecalho(token_de(caso.usuario, caso.a.condominio.id, perfil="administracao"))
    assert vincular(client, caso, chave_=caso.chaves[2].codigo, headers=headers).status_code == 201
    assert {m.condominio_id for m in associacoes(session, caso.usuario)} == {
        caso.a.condominio.id,
        caso.b.condominio.id,
    }


@pytest.mark.parametrize(
    "motivo",
    [
        "inexistente",
        "revogada",
        "regenerada",
        "pendente",
        "rejeitado",
        "desativado",
        "unidade_inativa",
    ],
)
def test_chaves_invalidas_mesmo_erro_e_falha_persistente(client, session, caso, motivo):
    codigo = caso.chaves[0].codigo
    if motivo == "inexistente":
        codigo = "Z" * 10
    elif motivo == "revogada":
        caso.chaves[0].revogada_em = caso.relogio.momento
    elif motivo == "regenerada":
        resposta = client.post(
            f"/api/v1/unidades/{caso.a.unidade_102.id}/chave/regeneracao",
            headers=caso.a.cabecalho_de("administracao"),
            json={"responsavel_id": str(caso.responsavel.id)},
        )
        assert resposta.status_code == 200
    elif motivo == "unidade_inativa":
        caso.a.unidade_102.ativo = False
    else:
        caso.a.condominio.status = motivo
        caso.a.condominio.motivo_rejeicao = "Motivo" if motivo == "rejeitado" else None
    session.commit()
    resposta = vincular(client, caso, chave_=codigo)
    assert resposta.status_code == 404
    assert resposta.json() == {
        "error": {
            "code": "not_found",
            "message": "Chave de acesso inválida ou já substituída. Peça uma nova à Administração.",
        }
    }
    session.rollback()
    assert not associacoes(session, caso.usuario)
    tentativa = session.scalars(
        select(TentativaChaveAcesso).where(TentativaChaveAcesso.usuario_id == caso.usuario.id)
    ).one()
    assert tentativa.sucesso is False


@pytest.mark.parametrize(
    "entrada",
    [
        "x",
        "",
        "0" * 10,
        "I" * 10,
        "L" * 10,
        "A" * 11,
        "A" * 9,
        "!" * 10,
        " " * 65,
        None,
        123,
        ["A" * 10],
    ],
)
def test_formato_invalido(client, session, caso, entrada):
    resposta = client.post(ROTA, headers=caso.headers, json={"chave": entrada})
    assert resposta.status_code == 422
    assert (
        session.scalar(
            select(func.count())
            .select_from(TentativaChaveAcesso)
            .where(TentativaChaveAcesso.usuario_id == caso.usuario.id)
        )
        == 0
    )


@pytest.mark.parametrize(
    "campo", ["condominio_id", "unidade_id", "usuario_id", "perfil", "permissoes", "status"]
)
def test_campos_protegidos(client, caso, campo):
    assert vincular(client, caso, **{campo: str(uuid.uuid4())}).status_code == 422


@pytest.mark.parametrize("tipo", ["administracao", "funcionario", "plataforma"])
def test_contas_nao_autorizadas(client, session, caso, tipo):
    usuario = {
        "administracao": caso.a.administracao,
        "funcionario": caso.a.funcionario,
        "plataforma": caso.a.adm,
    }[tipo]
    if tipo == "administracao":
        usuario.tipo_cadastro = "administracao"
    session.commit()
    assert vincular(client, caso, headers=cabecalho(token_de(usuario, None))).status_code == 403
    assert not associacoes(session, caso.usuario)


def test_sem_identidade_e_conta_inativa(client, session, caso):
    assert client.post(ROTA, json={"chave": caso.chaves[0].codigo}).status_code == 401
    caso.usuario.ativo = False
    session.commit()
    assert vincular(client, caso).status_code == 401


@pytest.mark.parametrize("perfil", ["administracao", "funcionario"])
@pytest.mark.parametrize("ativo", [True, False])
def test_vinculo_de_outro_perfil_nao_e_sobrescrito(client, session, caso, perfil, ativo):
    if perfil == "funcionario":
        # montar_predio já cria um Funcionário fictício. A US-210 permite apenas um,
        # inclusive inativo: retirar só esse vínculo da preparação evita uma duplicidade
        # inválida antes de testar a proteção original contra conversão de perfil.
        ficticio = session.scalars(
            select(VinculoCondominio).where(
                VinculoCondominio.usuario_id == caso.a.funcionario.id,
                VinculoCondominio.condominio_id == caso.a.condominio.id,
            )
        ).one()
        session.delete(ficticio)
        session.flush()
    session.add(
        VinculoCondominio(
            usuario_id=caso.usuario.id,
            condominio_id=caso.a.condominio.id,
            perfil=perfil,
            ativo=ativo,
        )
    )
    session.commit()
    resposta = vincular(client, caso)
    assert (
        resposta.status_code == 409 and resposta.json()["error"]["reason"] == "perfil_incompativel"
    )
    vinculo = session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
    ).one()
    assert vinculo.perfil == perfil and vinculo.ativo == ativo
    assert not associacoes(session, caso.usuario)


def test_retorno_apos_desvinculacao_preserva_historico(client, session, caso):
    assert vincular(client, caso).status_code == 201
    (anterior,) = associacoes(session, caso.usuario)
    anterior.status = "desvinculado"
    anterior.desvinculado_em = datetime.now(UTC)
    vinculo = session.scalars(
        select(VinculoCondominio).where(VinculoCondominio.usuario_id == caso.usuario.id)
    ).one()
    vinculo.ativo = False
    session.commit()
    assert vincular(client, caso).status_code == 201
    session.refresh(vinculo)
    assert vinculo.ativo and len(associacoes(session, caso.usuario)) == 2
    assert anterior.status == "desvinculado"


@pytest.mark.parametrize("etapa", ["vinculo", "morador", "permissoes", "tentativa", "auditoria"])
def test_rollback_em_falha_de_persistencia(client, session, caso, monkeypatch, etapa):
    alvo, nome = {
        "vinculo": (repository, "criar_vinculo"),
        "morador": (repository.RepositorioMoradores, "criar"),
        "permissoes": (RepositorioPermissoes, "definir"),
        "tentativa": (repository, "registrar_tentativa"),
        "auditoria": (auditoria, "registrar_acao"),
    }[etapa]
    original = getattr(alvo, nome)

    def falhar(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Falha simulada depois da escrita")

    monkeypatch.setattr(alvo, nome, falhar)
    assert vincular(client, caso).status_code == 500
    assert not associacoes(session, caso.usuario)
    for modelo in (VinculoCondominio, TentativaChaveAcesso, RegistroAuditoria):
        assert (
            session.scalar(
                select(func.count()).select_from(modelo).where(modelo.usuario_id == caso.usuario.id)
            )
            == 0
        )
    assert (
        session.scalar(
            select(func.count())
            .select_from(PermissaoAba)
            .where(PermissaoAba.condominio_id == caso.a.condominio.id)
        )
        == 0
    )
    assert caso.chaves[0].revogada_em is None
