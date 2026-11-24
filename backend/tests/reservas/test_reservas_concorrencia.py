"""US-603: dois pedidos simultâneos para o mesmo horário gravam uma só reserva.

Aqui não dá para usar a fixture de rollback: as duas requisições precisam de conexões e
transações DE VERDADE, com commit, para o índice único decidir entre elas. Cada requisição abre
a sua sessão (como o `get_session` de produção), as threads disparam juntas numa barreira, e tudo
o que foi criado é apagado no fim.
"""

import os
import threading
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.contexto import ContextoCondominio
from app.core.tempo import get_relogio
from app.db.session import get_session
from app.main import create_app
from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.reservas.models import AreaComum, Reserva
from app.modules.reservas.repository import RepositorioAreasComuns
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import MoradorUnidade, PermissaoAba, Unidade
from app.modules.usuarios.models import Usuario
from tests.isolamento.cenario import cabecalho, token_de
from tests.reservas.cenario import AGORA, DIA

pytestmark = pytest.mark.postgres

RODADAS = 10


@dataclass
class Predio:
    condominio_id: uuid.UUID
    area_id: uuid.UUID
    unidades: list[uuid.UUID]
    usuarios: list[uuid.UUID]
    cabecalhos: list[dict[str, str]]  # um morador por unidade, com a aba Reservas


@pytest.fixture
def engine() -> Generator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url, pool_size=4)
    yield engine
    engine.dispose()


@pytest.fixture
def predio(engine: Engine) -> Generator[Predio]:
    """Prédio com duas unidades e uma área 00:00 a 23:00, gravado com COMMIT."""
    with Session(engine) as session:
        condominio = Condominio(nome=f"Concorrência {uuid.uuid4().hex[:6]}", status="ativo")
        session.add(condominio)
        session.flush()
        unidades, usuarios = [], []
        for numero in ("101", "102"):
            unidade = Unidade(condominio_id=condominio.id, identificacao=f"Bloco C / {numero}")
            usuario = Usuario(
                nome=f"Morador {numero}",
                email=f"{uuid.uuid4().hex[:12]}@exemplo.test",
                ativo=True,
                administrador_plataforma=False,
                sessao_versao=1,
            )
            session.add_all([unidade, usuario])
            session.flush()
            session.add(
                VinculoCondominio(
                    usuario_id=usuario.id, condominio_id=condominio.id, perfil="morador"
                )
            )
            morador = MoradorUnidade(
                condominio_id=condominio.id,
                unidade_id=unidade.id,
                usuario_id=usuario.id,
                origem="cadastro",
            )
            session.add(morador)
            session.flush()
            session.add(
                PermissaoAba(
                    condominio_id=condominio.id,
                    morador_unidade_id=morador.id,
                    aba="reservas",
                    com_acesso=True,
                )
            )
            unidades.append(unidade)
            usuarios.append(usuario)
        foto = Arquivo(
            condominio_id=condominio.id,
            chave_storage=f"teste/{uuid.uuid4().hex}.jpg",
            nome_original="foto.jpg",
            tipo_mime="image/jpeg",
            tamanho_bytes=1,
            enviado_por_usuario_id=usuarios[0].id,
        )
        session.add(foto)
        session.flush()
        area = AreaComum(
            condominio_id=condominio.id,
            nome="Salão",
            foto_arquivo_id=foto.id,
            abre_as=time(0),
            fecha_as=time(23),
            capacidade=10,
        )
        session.add(area)
        session.commit()
        dados = Predio(
            condominio_id=condominio.id,
            area_id=area.id,
            unidades=[u.id for u in unidades],
            usuarios=[u.id for u in usuarios],
            cabecalhos=[cabecalho(token_de(u, condominio.id, perfil="morador")) for u in usuarios],
        )

    yield dados

    # Limpeza. A trilha de auditoria recusa DELETE por trigger (só inserção, regra 21 do DER);
    # `session_replication_role = replica` desliga os triggers só nesta transação de limpeza.
    with engine.begin() as conexao:
        conexao.execute(text("SET LOCAL session_replication_role = replica"))
        parametros = {"c": dados.condominio_id}
        for tabela in (
            "registros_auditoria",
            "reservas",
            "areas_comuns",
            "arquivos",
            "permissoes_aba",
            "moradores_unidade",
            "vinculos_condominio",
            "unidades",
        ):
            conexao.execute(text(f"DELETE FROM {tabela} WHERE condominio_id = :c"), parametros)
        conexao.execute(text("DELETE FROM condominios WHERE id = :c"), parametros)
        conexao.execute(text("DELETE FROM usuarios WHERE id = ANY(:ids)"), {"ids": dados.usuarios})


@pytest.fixture
def app(engine: Engine):
    app = create_app()
    fabrica = sessionmaker(bind=engine, expire_on_commit=False)

    def sessao_real() -> Generator[Session]:
        # Igual ao get_session de produção, mas no banco de teste: uma conexão por requisição.
        with fabrica() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_session] = sessao_real
    app.dependency_overrides[get_relogio] = lambda: lambda: AGORA
    return app


def disparar_juntos(app, pedidos: list[tuple[dict[str, str], dict[str, Any]]]) -> list[Any]:
    """Cada pedido numa thread com o próprio TestClient; a barreira solta todos ao mesmo tempo."""
    barreira = threading.Barrier(len(pedidos))
    respostas: list[Any] = [None] * len(pedidos)

    def executar(indice: int, cab: dict[str, str], corpo: dict[str, Any]) -> None:
        cliente = TestClient(app)  # sem `with`: cada chamada roda no seu próprio event loop
        barreira.wait()
        respostas[indice] = cliente.post("/api/v1/reservas", headers=cab, json=corpo)

    threads = [
        threading.Thread(target=executar, args=(i, cab, corpo))
        for i, (cab, corpo) in enumerate(pedidos)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(r is not None for r in respostas), "alguma requisição não terminou"
    return respostas


def corpo(predio: Predio, unidade: int, dia, hora: str) -> dict[str, Any]:
    return {
        "unidade_id": str(predio.unidades[unidade]),
        "area_id": str(predio.area_id),
        "data": dia.isoformat(),
        "hora_inicio": hora,
    }


def ativas(engine: Engine, predio: Predio, **filtro: Any) -> int:
    with Session(engine) as session:
        consulta = (
            select(func.count())
            .select_from(Reserva)
            .where(
                Reserva.condominio_id == predio.condominio_id,
                Reserva.status == "ativa",
                *(getattr(Reserva, campo) == valor for campo, valor in filtro.items()),
            )
        )
        return session.scalar(consulta) or 0


def test_duas_unidades_no_mesmo_horario_gravam_uma_reserva(app, engine, predio):
    for rodada in range(RODADAS):
        dia = DIA + timedelta(days=rodada)  # um slot diferente por rodada
        hora = f"{10 + rodada:02d}:00"
        respostas = disparar_juntos(
            app,
            [
                (predio.cabecalhos[0], corpo(predio, 0, dia, hora)),
                (predio.cabecalhos[1], corpo(predio, 1, dia, hora)),
            ],
        )
        status = sorted(r.status_code for r in respostas)
        assert status == [201, 409], (rodada, [r.text for r in respostas])
        conflito = next(r for r in respostas if r.status_code == 409).json()["error"]
        assert conflito["reason"] == "horario_ocupado"
        assert ativas(engine, predio, data=dia, hora_inicio=time(10 + rodada)) == 1


def test_mesma_unidade_em_horarios_diferentes_grava_uma_reserva(app, engine, predio):
    for rodada in range(RODADAS):
        dia = DIA + timedelta(days=100 + rodada)
        respostas = disparar_juntos(
            app,
            [
                (predio.cabecalhos[0], corpo(predio, 0, dia, "10:00")),
                (predio.cabecalhos[0], corpo(predio, 0, dia, "15:00")),
            ],
        )
        status = sorted(r.status_code for r in respostas)
        assert status == [201, 409], (rodada, [r.text for r in respostas])
        conflito = next(r for r in respostas if r.status_code == 409).json()["error"]
        assert conflito["reason"] == "reserva_duplicada_unidade"
        assert ativas(engine, predio, data=dia, unidade_id=predio.unidades[0]) == 1


def test_bloqueio_de_datas_e_reserva_nao_andam_juntos(engine: Engine, predio: Predio) -> None:
    """US-602: o bloqueio trava a área em modo exclusivo e a reserva, em modo compartilhado.

    Uma reserva em andamento faz o bloqueio esperar (e entrar na prévia dele); um bloqueio em
    andamento faz a reserva esperar (e depois enxergar o bloqueio, com 409 `area_bloqueada`). Duas
    reservas entre si não se atrapalham.
    """
    contexto = ContextoCondominio(
        usuario_id=predio.usuarios[0],
        condominio_id=predio.condominio_id,
        perfil="administracao",
        vinculo_id=uuid.uuid4(),
    )

    def travar(session: Session, *, compartilhada: bool) -> None:
        session.execute(text("SET LOCAL lock_timeout = '300ms'"))
        RepositorioAreasComuns(session, contexto).obter_travada(
            predio.area_id, compartilhada=compartilhada
        )

    with Session(engine) as reserva, Session(engine) as outra, Session(engine) as bloqueio:
        travar(reserva, compartilhada=True)
        travar(outra, compartilhada=True)  # reservas simultâneas convivem
        with pytest.raises(OperationalError, match="lock timeout|LockNotAvailable"):
            travar(bloqueio, compartilhada=False)  # o bloqueio espera as reservas
        bloqueio.rollback()
        reserva.rollback()
        outra.rollback()

    with Session(engine) as bloqueio, Session(engine) as reserva:
        travar(bloqueio, compartilhada=False)
        with pytest.raises(OperationalError, match="lock timeout|LockNotAvailable"):
            travar(reserva, compartilhada=True)  # a reserva espera o bloqueio
        reserva.rollback()
        bloqueio.rollback()
