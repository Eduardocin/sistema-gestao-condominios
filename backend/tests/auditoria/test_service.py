import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.errors import ApiError, RecursoNaoEncontrado
from app.modules.auditoria import repository, service
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.unidades.models import Unidade

pytestmark = pytest.mark.postgres


def contexto(cenario, perfil="administracao"):
    usuario = cenario.a.administracao if perfil == "administracao" else cenario.a.funcionario
    return ContextoAuditoria(usuario.id, cenario.a.condominio.id, perfil, "203.0.113.5")


def registrar(session, cenario, **campos):
    service.registrar_acao(
        session,
        ctx=contexto(cenario),
        acao="estrutura.editar",
        recurso_tipo="unidade",
        recurso_id=cenario.a.unidade_101.id,
        **campos,
    )


def eventos(session, cenario):
    return list(
        session.scalars(
            select(RegistroAuditoria)
            .where(RegistroAuditoria.condominio_id == cenario.a.condominio.id)
            .order_by(RegistroAuditoria.id)
        )
    )


def test_registro_completo_sanitizado_e_snapshot_do_responsavel(cenario):
    antes = {"ativo": True, "senha_hash": "secreto"}
    depois = {"ativo": False, "pessoa": {"documento": "52998224725", "codigo": "CHAVE"}}
    with cenario.fabrica() as session:
        registrar(
            session,
            cenario,
            responsavel=ResponsavelRef("administracao", cenario.responsavel.id),
            antes=antes,
            depois=depois,
        )
        session.commit()
        [evento] = eventos(session, cenario)
        assert evento.usuario_id == cenario.a.administracao.id
        assert evento.perfil == "administracao"
        assert evento.recurso_tipo == "unidade"
        assert evento.recurso_id == cenario.a.unidade_101.id
        assert str(evento.ip) == "203.0.113.5"
        assert evento.criado_em.tzinfo is not None
        assert abs((datetime.now(UTC) - evento.criado_em).total_seconds()) < 60
        assert evento.responsavel_nome == "Responsável A"
        assert evento.antes == {"ativo": True}
        assert evento.depois == {"ativo": False, "pessoa": {"documento": "***.982.247-**"}}
        responsavel = session.get(ResponsavelAdministracao, cenario.responsavel.id)
        responsavel.nome = "Nome alterado"
        session.commit()
        session.refresh(evento)
        assert evento.responsavel_nome == "Responsável A"
        assert depois["pessoa"]["codigo"] == "CHAVE"


def test_nao_faz_commit_e_rollback_reverte_operacao_e_evento(cenario):
    with cenario.fabrica() as session:
        unidade = session.get(Unidade, cenario.a.unidade_101.id)
        unidade.identificacao = "alterada"
        registrar(
            session, cenario, responsavel=ResponsavelRef("administracao", cenario.responsavel.id)
        )
        assert len(eventos(session, cenario)) == 1
        with cenario.fabrica() as outra:
            assert eventos(outra, cenario) == []
            assert outra.get(Unidade, unidade.id).identificacao != "alterada"
        session.rollback()
    with cenario.fabrica() as outra:
        assert eventos(outra, cenario) == []
        assert outra.get(Unidade, cenario.a.unidade_101.id).identificacao != "alterada"


@pytest.mark.parametrize("tipo", ["ausente", "outro_condominio", "inativo", "tipo_incorreto"])
def test_responsavel_invalido_nao_insere_evento(cenario, tipo):
    ref = ResponsavelRef("administracao", cenario.responsavel.id)
    if tipo == "ausente":
        ref = None
    elif tipo == "outro_condominio":
        ref = ResponsavelRef("administracao", cenario.outro_responsavel.id)
    elif tipo == "tipo_incorreto":
        ref = ResponsavelRef("funcionario", cenario.funcionario.id)
    with cenario.fabrica() as session:
        if tipo == "inativo":
            session.get(ResponsavelAdministracao, cenario.responsavel.id).ativo = False
            session.flush()
        with pytest.raises(ApiError if tipo == "ausente" else RecursoNaoEncontrado):
            registrar(session, cenario, responsavel=ref)
        assert eventos(session, cenario) == []


def test_funcionario_registra_pessoa_identificada(cenario):
    with cenario.fabrica() as session:
        service.registrar_acao(
            session,
            ctx=contexto(cenario, "funcionario"),
            acao="encomenda.entregar",
            recurso_tipo="unidade",
            recurso_id=cenario.a.unidade_101.id,
            responsavel=ResponsavelRef("funcionario", cenario.funcionario.id),
        )
        session.commit()
        [evento] = eventos(session, cenario)
        assert evento.responsavel_nome == "Porteiro A"
        assert evento.usuario_id == cenario.a.funcionario.id


def test_gestao_da_lista_preserva_excecao_e_identidade_da_conta(cenario):
    with cenario.fabrica() as session:
        service.registrar_acao(
            session,
            ctx=contexto(cenario),
            acao="responsaveis.alterar",
            recurso_tipo="responsavel_administracao",
            recurso_id=cenario.responsavel.id,
        )
        session.commit()
        [evento] = eventos(session, cenario)
        assert evento.responsavel_nome is None
        assert evento.usuario_id == cenario.a.administracao.id


def test_falha_de_auditoria_nao_confirma_operacao_principal(cenario, monkeypatch):
    def falhar(*args, **kwargs):
        raise RuntimeError("persistência indisponível")

    monkeypatch.setattr(repository, "inserir", falhar)
    with pytest.raises(RuntimeError), cenario.fabrica() as session:
        session.get(Unidade, cenario.a.unidade_101.id).identificacao = "não pode persistir"
        registrar(
            session, cenario, responsavel=ResponsavelRef("administracao", cenario.responsavel.id)
        )
        session.commit()
    with cenario.fabrica() as session:
        assert eventos(session, cenario) == []
        assert session.get(Unidade, cenario.a.unidade_101.id).identificacao != "não pode persistir"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE registros_auditoria SET acao = 'outra.acao' WHERE id = :id",
        "DELETE FROM registros_auditoria WHERE id = :id",
    ],
)
def test_trigger_preserva_evento_confirmado(cenario, sql):
    with cenario.fabrica() as session:
        registrar(
            session, cenario, responsavel=ResponsavelRef("administracao", cenario.responsavel.id)
        )
        session.commit()
        [evento] = eventos(session, cenario)
        with pytest.raises(DBAPIError, match="apenas INSERT"):
            session.execute(text(sql), {"id": evento.id})
        session.rollback()
        session.refresh(evento)
        assert evento.acao == "estrutura.editar"


@pytest.mark.parametrize("acao", ["sem_grupo", "Grupo.acao", "a." + "b" * 60])
def test_rejeita_nome_de_evento_invalido(cenario, acao):
    with cenario.fabrica() as session, pytest.raises(ValueError):
        service.registrar_acao(
            session,
            ctx=ContextoAuditoria(cenario.a.morador.id),
            acao=acao,
            recurso_tipo="usuario",
            recurso_id=uuid.uuid4(),
        )
