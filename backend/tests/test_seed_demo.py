import os
from collections.abc import Iterator
from datetime import date, timedelta
from importlib import import_module
from typing import cast

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    AreaComum,
    Arquivo,
    Aviso,
    Chamado,
    ChaveAcesso,
    Comunicado,
    Condominio,
    Encomenda,
    Ocorrencia,
    RegistroVisita,
    Reserva,
    Unidade,
    Usuario,
    Veiculo,
    VinculoCondominio,
    Visitante,
)
from app.modules.auth.security import verificar_senha
from app.modules.storage.s3 import S3Adapter
from app.modules.storage.service import StorageService
from app.modules.storage.types import FileMetadata, Module, StorageContext


@pytest.fixture
def banco() -> Iterator[Session]:
    url = os.getenv("TEST_DATABASE_URL")
    if url is None:
        pytest.skip("Defina TEST_DATABASE_URL para PostgreSQL exclusivo e migrado")
    engine = create_engine(url)
    # O rollback externo mantém o banco compartilhado com a suíte intacto.
    with engine.connect() as connection, connection.begin() as transaction:
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@pytest.mark.parametrize(
    "config",
    [
        {"APP_ENV": "production"},
        {"APP_ENV": "test"},
        {"POSTGRES_HOST": "externo.invalid"},
        {"POSTGRES_DB": "condominios_test"},
        {"POSTGRES_PORT": "5433"},
        {"DATABASE_URL": "postgresql+psycopg://db/condominios"},
        {"DEMO_SEED_ALLOWED": "false"},
        {"COMPOSE_DEMO_APP_ENV": "production"},
        {"COMPOSE_DEMO_DATABASE_URL": "postgresql+psycopg://externo.invalid/demo"},
        {"STORAGE_ENDPOINT": "https://externo.invalid"},
    ],
)
def test_reset_recusa_alvo_nao_local(
    monkeypatch: pytest.MonkeyPatch, config: dict[str, str], banco: Session
) -> None:
    banco.add(Usuario(nome="Controle", email="controle@example.test"))
    banco.commit()
    seed = import_module("app.seed_demo")
    for key, value in {
        "APP_ENV": "development",
        "CORS_ORIGINS": '["https://localhost"]',
        "JWT_SECRET_KEY": "seed-guard-ficticio-distinto-do-padrao-12345",
        "POSTGRES_PASSWORD": "demo-guard-ficticio",
        "STORAGE_ACCESS_KEY": "demo-guard-storage",
        "STORAGE_SECRET_KEY": "demo-guard-storage-ficticio",
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "condominios",
        "DEMO_SEED_ALLOWED": "true",
        "DATABASE_URL": "",
        "STORAGE_ENDPOINT": "http://storage:9000",
        "COMPOSE_DEMO_APP_ENV": "development",
        "COMPOSE_DEMO_DATABASE_URL": "",
        **config,
    }.items():
        monkeypatch.setenv(key, value)
    # Qualquer tentativa de abrir a sessão real deve abortar o teste imediatamente.
    monkeypatch.setattr(seed, "get_session_factory", lambda: pytest.fail("Abriu o banco"))
    seed.get_settings.cache_clear()
    try:
        assert seed.run() != 0
    finally:
        seed.get_settings.cache_clear()
    assert banco.scalar(select(Usuario).where(Usuario.email == "controle@example.test"))


def test_seed_demo_rollback_em_falha(monkeypatch: pytest.MonkeyPatch, banco: Session) -> None:
    banco.add(Usuario(nome="Controle", email="controle@example.test"))
    banco.commit()
    seed = import_module("app.seed_demo")

    def falhar(_: str) -> str:
        assert banco.scalar(select(Usuario.id)) is None
        raise RuntimeError("falha após o reset")

    monkeypatch.setattr(seed, "hash_senha", falhar)
    with pytest.raises(RuntimeError, match="falha após o reset"):
        seed.seed_demo(banco, hoje=date(2026, 11, 26))
    assert banco.scalar(select(Usuario.email)) == "controle@example.test"


def test_seed_demo_reset_repetivel(banco: Session) -> None:
    seed = import_module("app.seed_demo")
    hoje = date(2026, 11, 26)
    versao = banco.scalar(text("SELECT version_num FROM alembic_version"))
    banco.commit()

    primeira = seed.seed_demo(banco, hoje=hoje)
    emails = banco.scalars(select(Usuario.email).order_by(Usuario.email)).all()
    banco.add(Usuario(nome="Descartar", email="descartar@example.test"))
    banco.commit()

    segunda = seed.seed_demo(banco, hoje=hoje)
    assert segunda == primeira
    assert segunda.condominios == 3
    assert segunda.contas == len(emails) == 12
    assert banco.scalars(select(Usuario.email).order_by(Usuario.email)).all() == emails
    assert banco.scalar(text("SELECT version_num FROM alembic_version")) == versao
    assert (
        banco.scalar(
            text(
                "SELECT tgenabled FROM pg_trigger "
                "WHERE tgname = 'registros_auditoria_somente_insercao'"
            )
        )
        == "O"
    )


def test_seed_demo_preserva_isolamento_entre_condominios(banco: Session) -> None:
    seed = import_module("app.seed_demo")
    seed.seed_demo(banco, hoje=date(2026, 11, 26))
    assert (
        banco.scalar(
            select(func.count()).select_from(Condominio).where(Condominio.status == "ativo")
        )
        == 2
    )
    assert sorted(
        banco.execute(
            select(VinculoCondominio.perfil, func.count()).group_by(VinculoCondominio.perfil)
        ).all()
    ) == [("administracao", 3), ("funcionario", 2), ("morador", 7)]
    assert (
        len(
            set(
                banco.scalars(
                    select(VinculoCondominio.usuario_id).where(
                        VinculoCondominio.perfil == "administracao"
                    )
                )
            )
        )
        == 2
    )
    assert (
        banco.scalar(select(Condominio.nome).where(Condominio.status == "pendente"))
        == "Residencial Vista Verde"
    )
    assert set(banco.scalars(select(Encomenda.status))) == {
        "aguardando_retirada",
        "entregue_aguardando_confirmacao",
        "retirada_confirmada",
    }
    assert set(banco.scalars(select(Ocorrencia.status))) == {"em_aberto", "resolvida"}
    for reserva, unidade, area in banco.execute(
        select(Reserva, Unidade, AreaComum)
        .join(Unidade, Reserva.unidade_id == Unidade.id)
        .join(AreaComum, Reserva.area_id == AreaComum.id)
    ):
        assert reserva.condominio_id == unidade.condominio_id == area.condominio_id
    for usuario in banco.scalars(select(Usuario)):
        assert usuario.senha_hash is not None
        assert verificar_senha("Teste123", usuario.senha_hash)
    assert banco.scalar(select(func.count()).select_from(RegistroVisita)) == 3
    assert banco.scalar(select(func.count()).select_from(Veiculo)) == 6
    assert banco.scalar(select(func.count()).select_from(Aviso)) == 8
    assert set(banco.scalars(select(Chamado.status))) == {"aberto", "em_atendimento", "encerrado"}
    assert banco.scalar(select(func.count()).select_from(Comunicado)) == 2
    assert banco.scalar(select(ChaveAcesso.codigo).where(ChaveAcesso.codigo == "AURRAB2Z22"))
    # Toda chave usa o alfabeto das chaves reais, sem 0/O/1/I/L.
    for codigo in banco.scalars(select(ChaveAcesso.codigo)):
        assert len(codigo) == 10
        assert set(codigo) <= set("23456789ABCDEFGHJKMNPQRSTUVWXYZ")


def test_seed_demo_datas_sao_relativas(banco: Session) -> None:
    seed = import_module("app.seed_demo")
    hoje = date(2030, 5, 10)
    seed.seed_demo(banco, hoje=hoje)
    datas = set(banco.scalars(select(Reserva.data).where(Reserva.status == "ativa")))
    assert hoje + timedelta(days=2) in datas
    assert all(hoje - timedelta(days=3) <= data <= hoje + timedelta(days=5) for data in datas)
    visitantes = banco.scalars(select(Visitante).where(Visitante.nome == "Visitante Demo")).all()
    assert len(visitantes) == 2
    assert all(v.entrada_prevista <= hoje < v.saida_prevista for v in visitantes)
    vigentes = banco.scalars(select(Aviso).where(Aviso.titulo == "Coleta seletiva")).all()
    assert vigentes
    assert all(a.inicio_em.date() <= hoje <= a.fim_em.date() for a in vigentes)


def test_seed_demo_fotos_respeitam_chave_do_storage(banco: Session) -> None:
    seed = import_module("app.seed_demo")
    seed.seed_demo(banco, hoje=date(2026, 11, 26))
    storage = StorageService(S3Adapter(Settings()), authorize=lambda *_: None)
    for modelo, propriedade, modulo in (
        (AreaComum, AreaComum.foto_arquivo_id, "fotos"),
        (Encomenda, Encomenda.foto_nota_arquivo_id, "encomendas"),
    ):
        arquivos = banco.scalars(select(Arquivo).join(modelo, propriedade == Arquivo.id)).all()
        assert arquivos
        for arquivo in arquivos:
            assert arquivo.condominio_id is not None
            ctx = StorageContext(arquivo.condominio_id, arquivo.enviado_por_usuario_id)
            dados = FileMetadata(
                arquivo.id,
                arquivo.condominio_id,
                cast(Module, modulo),
                arquivo.chave_storage,
                arquivo.nome_original,
                arquivo.tipo_mime,
                arquivo.tamanho_bytes,
                arquivo.enviado_por_usuario_id,
                arquivo.criado_em,
            )
            assert "/" + arquivo.chave_storage + "?" in storage.download_url(ctx, dados)
