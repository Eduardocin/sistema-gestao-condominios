import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AreaComum,
    BlocoCondominio,
    Condominio,
    EventoAuditoria,
    RascunhoCondominio,
    Unidade,
    Usuario,
    VinculoCondominio,
)
from app.db.session import get_session
from app.main import create_app
from app.modules.auth.security import hash_senha

pytestmark = pytest.mark.postgres

SENHA_FORTE = "Senha#Forte123"
RESPONSAVEL = {
    "nome": "Responsável Teste",
    "email": "responsavel.wizard@exemplo.test",
    "cpf": "529.982.247-25",
    "senha": SENHA_FORTE,
}


@pytest.fixture
def session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    if engine.dialect.name != "postgresql":
        pytest.fail("Estes testes exigem PostgreSQL real")
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.fixture
def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def iniciar(client: TestClient) -> tuple[str, dict[str, str]]:
    resposta = client.post("/api/v1/condominios/wizard")
    assert resposta.status_code == 201
    corpo = resposta.json()
    return corpo["id"], {"X-Wizard-Token": corpo["token"]}


def preencher_etapas(
    client: TestClient,
    rascunho_id: str,
    headers: dict[str, str],
    *,
    email: str | None = None,
) -> None:
    prefixo = f"/api/v1/condominios/wizard/{rascunho_id}/etapas"
    assert (
        client.put(
            f"{prefixo}/dados-gerais",
            headers=headers,
            json={
                "nome": "Condomínio Teste",
                "cep": "01001-000",
                "logradouro": "Praça da Sé",
                "numero": "100",
                "cidade": "São Paulo",
                "estado": "sp",
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{prefixo}/blocos",
            headers=headers,
            json={"blocos": [{"nome": "A"}, {"nome": "B"}, {"nome": "C"}]},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{prefixo}/unidades",
            headers=headers,
            json={
                "geracoes": [
                    {
                        "bloco": bloco,
                        "andar_inicial": 1,
                        "quantidade_andares": 10,
                        "unidades_por_andar": 4,
                    }
                    for bloco in ("A", "B", "C")
                ]
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{prefixo}/areas-comuns",
            headers=headers,
            json={"areas_comuns": [{"nome": "Salão de festas", "descricao": "Área para eventos"}]},
        ).status_code
        == 200
    )
    dados_responsavel = {**RESPONSAVEL, "email": email or f"{uuid.uuid4().hex}@exemplo.test"}
    assert (
        client.put(
            f"{prefixo}/responsavel",
            headers=headers,
            json=dados_responsavel,
        ).status_code
        == 200
    )


def test_wizard_conclui_cadastro_em_transacao_e_gera_unidades(client, session):
    rascunho_id, headers = iniciar(client)
    preencher_etapas(client, rascunho_id, headers)

    retomar = client.get(f"/api/v1/condominios/wizard/{rascunho_id}", headers=headers)
    assert retomar.status_code == 200
    assert retomar.json()["responsavel_configurado"] is True
    assert "senha_hash" not in retomar.text
    assert SENHA_FORTE not in retomar.text

    resposta = client.post(f"/api/v1/condominios/wizard/{rascunho_id}/finalizar", headers=headers)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["unidades_criadas"] == 120
    assert corpo["condominio_ativo"] is False
    assert corpo["status_conta"] == "pendente"
    condominio = session.get(Condominio, uuid.UUID(corpo["condominio_id"]))
    usuario = session.get(Usuario, uuid.UUID(corpo["usuario_administracao_id"]))
    assert condominio is not None
    assert condominio.cep == "01001000"
    assert condominio.estado == "SP"
    assert condominio.ativo is False
    assert usuario is not None
    assert usuario.ativo is False
    assert usuario.status_conta == "pendente"
    assert usuario.senha_hash is not None and usuario.senha_hash != SENHA_FORTE
    assert (
        session.scalar(
            select(func.count())
            .select_from(BlocoCondominio)
            .where(BlocoCondominio.condominio_id == condominio.id)
        )
        == 3
    )
    assert (
        session.scalar(
            select(func.count()).select_from(Unidade).where(Unidade.condominio_id == condominio.id)
        )
        == 120
    )
    primeira_unidade = session.scalar(
        select(Unidade.identificacao).where(
            Unidade.condominio_id == condominio.id,
            Unidade.identificacao == "A-01-01",
        )
    )
    assert primeira_unidade == "A-01-01"
    unidade_com_bloco = session.scalar(
        select(Unidade).where(
            Unidade.condominio_id == condominio.id,
            Unidade.identificacao == "A-01-01",
        )
    )
    assert unidade_com_bloco is not None
    assert unidade_com_bloco.bloco_id is not None
    assert (
        session.scalar(
            select(func.count())
            .select_from(AreaComum)
            .where(AreaComum.condominio_id == condominio.id)
        )
        == 1
    )
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == usuario.id,
            VinculoCondominio.condominio_id == condominio.id,
        )
    )
    assert vinculo is not None
    assert vinculo.perfil == "administracao"
    assert vinculo.ativo is False
    eventos = session.scalars(
        select(EventoAuditoria).where(
            EventoAuditoria.tipo_evento == "criacao_conta",
            EventoAuditoria.usuario_id == usuario.id,
        )
    ).all()
    assert len(eventos) == 1
    assert eventos[0].condominio_id == condominio.id
    assert eventos[0].nome_responsavel == "Responsável Teste"
    assert session.get(RascunhoCondominio, uuid.UUID(rascunho_id)) is None


def test_wizard_valida_ordem_das_etapas_e_token_de_acesso(client):
    rascunho_id, headers = iniciar(client)

    bloco_sem_dados_gerais = client.put(
        f"/api/v1/condominios/wizard/{rascunho_id}/etapas/blocos",
        headers=headers,
        json={"blocos": [{"nome": "A"}]},
    )
    token_incorreto = client.get(
        f"/api/v1/condominios/wizard/{rascunho_id}",
        headers={"X-Wizard-Token": "x" * 32},
    )

    assert bloco_sem_dados_gerais.status_code == 409
    assert token_incorreto.status_code == 404


def test_wizard_rejeita_configuracao_que_nao_corresponde_aos_blocos(client):
    rascunho_id, headers = iniciar(client)
    prefixo = f"/api/v1/condominios/wizard/{rascunho_id}/etapas"
    assert (
        client.put(
            f"{prefixo}/dados-gerais",
            headers=headers,
            json={"nome": "Condomínio Teste"},
        ).status_code
        == 200
    )
    assert (
        client.put(
            f"{prefixo}/blocos",
            headers=headers,
            json={"blocos": [{"nome": "Torre A"}]},
        ).status_code
        == 200
    )

    resposta = client.put(
        f"{prefixo}/unidades",
        headers=headers,
        json={
            "geracoes": [
                {
                    "bloco": "Torre B",
                    "andar_inicial": 1,
                    "quantidade_andares": 10,
                    "unidades_por_andar": 4,
                }
            ]
        },
    )

    assert resposta.status_code == 422


def test_falha_ao_criar_conta_nao_persiste_condominio_parcial(client, session):
    email_existente = f"{uuid.uuid4().hex}@exemplo.test"
    rascunho_id, headers = iniciar(client)
    preencher_etapas(client, rascunho_id, headers, email=email_existente)
    session.add(
        Usuario(
            id=uuid.uuid4(),
            nome="Conta concorrente",
            email=email_existente,
            cpf="11144477735",
            senha_hash=hash_senha(SENHA_FORTE),
            ativo=False,
            status_conta="pendente",
        )
    )
    session.flush()

    resposta = client.post(f"/api/v1/condominios/wizard/{rascunho_id}/finalizar", headers=headers)

    assert resposta.status_code == 409
    assert session.scalar(select(Condominio).where(Condominio.nome == "Condomínio Teste")) is None
    assert session.get(RascunhoCondominio, uuid.UUID(rascunho_id)) is not None
