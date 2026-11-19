"""US-903: volume real em PostgreSQL, sem índices novos ou alterações de dados persistidos."""

import json
import math
import platform
import statistics
import uuid
from time import perf_counter

import pytest
from sqlalchemy import event, func, select, text

from app.modules.auditoria.models import RegistroAuditoria
from app.modules.auditoria.service import _codificar_cursor
from tests.auditoria.conftest import ROTA

pytestmark = pytest.mark.postgres


def _nos(plano):
    resultado = [plano["Node Type"] + (":" + plano["Index Name"] if "Index Name" in plano else "")]
    for filho in plano.get("Plans", []):
        resultado.extend(_nos(filho))
    return resultado


def test_consulta_com_100_mil_eventos_e_indices_existentes(consulta):
    session = consulta.session
    tipo = f"benchmark_{uuid.uuid4().hex}"
    session.execute(
        text("""
        INSERT INTO registros_auditoria
            (usuario_id, condominio_id, perfil, acao, recurso_tipo, recurso_id,
             responsavel_nome, antes, depois, criado_em)
        SELECT CASE n % 3 WHEN 1 THEN CAST(:ua AS uuid) WHEN 2 THEN CAST(:ub AS uuid) END,
               CASE n % 3 WHEN 1 THEN CAST(:ca AS uuid) WHEN 2 THEN CAST(:cb AS uuid) END,
               CASE WHEN n % 3 <> 0 THEN 'administracao' END,
               CASE WHEN n % 1000 = 0 THEN 'reserva.rara'
                    WHEN n % 2 = 0 THEN 'reserva.criar' ELSE 'reserva.cancelar' END,
               :tipo, CAST(:recurso AS uuid),
               CASE WHEN n % 3 <> 0 THEN 'Responsável sintético' END,
               '{"status":"anterior"}'::jsonb,
               jsonb_build_object('status', 'posterior', 'indice', n),
               TIMESTAMPTZ '2030-01-01 00:00:00+00' + (n / 5) * INTERVAL '1 second'
        FROM generate_series(1, 100000) AS n
    """),
        {
            "ua": consulta.cenario.a.administracao.id,
            "ub": consulta.cenario.b.administracao.id,
            "ca": consulta.cenario.a.condominio.id,
            "cb": consulta.cenario.b.condominio.id,
            "tipo": tipo,
            "recurso": uuid.uuid4(),
        },
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(RegistroAuditoria)
            .where(RegistroAuditoria.recurso_tipo == tipo)
        )
        == 100000
    )
    session.execute(text("ANALYZE registros_auditoria"))
    antigo = session.execute(
        select(RegistroAuditoria.criado_em, RegistroAuditoria.id)
        .where(RegistroAuditoria.recurso_tipo == tipo)
        .order_by(RegistroAuditoria.criado_em.desc(), RegistroAuditoria.id.desc())
        .offset(90000)
        .limit(1)
    ).one()
    cursor_profundo = _codificar_cursor(antigo.criado_em, antigo.id)
    casos = {
        "sem_filtros": {},
        "condominio": {"condominio_id": str(consulta.cenario.a.condominio.id)},
        "usuario": {"usuario_id": str(consulta.cenario.b.administracao.id)},
        "acao_rara": {"acao": "reserva.rara"},
        "combinados": {
            "condominio_id": str(consulta.cenario.a.condominio.id),
            "usuario_id": str(consulta.cenario.a.administracao.id),
            "acao": "reserva.cancelar",
            "de": "2029-12-31",
            "ate": "2030-01-01",
        },
        "cursor_apos_90_mil": {"cursor": cursor_profundo},
    }
    consultas = []
    connection = session.connection()

    def capturar(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT registros_auditoria.") and "LEFT OUTER JOIN" in statement:
            consultas.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", capturar)
    resultados = {}
    try:
        for nome, filtros in casos.items():
            params = {"page_size": 100, **filtros}
            # Uma execução para aquecer conexão, plano e cache; depois 20 amostras HTTP/ASGI.
            resposta = consulta.client.get(ROTA, headers=consulta.headers, params=params)
            assert resposta.status_code == 200, resposta.text
            tempos = []
            for _ in range(20):
                inicio = perf_counter()
                resposta = consulta.client.get(ROTA, headers=consulta.headers, params=params)
                tempos.append((perf_counter() - inicio) * 1000)
                assert resposta.status_code == 200
                assert len(resposta.json()["items"]) == 100
            sql, parametros = consultas[-1]
            plano = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, parametros
            ).scalar_one()[0]
            p95 = sorted(tempos)[math.ceil(0.95 * len(tempos)) - 1]
            resultados[nome] = {
                "p50_ms": round(statistics.median(tempos), 3),
                "p95_ms": round(p95, 3),
                "sql_ms": plano["Execution Time"],
                "plano": _nos(plano["Plan"]),
            }
            # Orçamento local documentado: p95 abaixo de 1 s para uma página de 100 eventos.
            assert p95 < 1000, resultados[nome]
        versao = session.scalar(text("SHOW server_version"))
        total = session.scalar(select(func.count()).select_from(RegistroAuditoria))
        print(
            "\nBENCHMARK_AUDITORIA="
            + json.dumps(
                {
                    "eventos_sinteticos": 100000,
                    "total_no_banco": total,
                    "postgresql": versao,
                    "python": platform.python_version(),
                    "sistema": platform.system(),
                    "amostras_por_caso": 20,
                    "page_size": 100,
                    "cache": "aquecido",
                    "resultados": resultados,
                },
                ensure_ascii=False,
            )
        )
    finally:
        event.remove(connection, "before_cursor_execute", capturar)
    # A fixture reverte os 100 mil INSERTs; nenhuma linha existente é apagada.
