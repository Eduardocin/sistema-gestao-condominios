"""Regras do DER garantidas pelo próprio PostgreSQL (TASK-81, seção 4 de docs/modelo-de-dados.md).

Cada teste tenta gravar um estado inválido direto no banco e confere qual constraint recusou.
O nome importa: os services traduzem a violação em mensagem (convivencia.md, seção 4.2).
"""

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Andar,
    AreaComum,
    Arquivo,
    Bloco,
    ChaveAcesso,
    Condominio,
    Encomenda,
    Funcionario,
    MoradorUnidade,
    RegistroAuditoria,
    RegistroVisita,
    Reserva,
    Unidade,
    Usuario,
    Veiculo,
    Visitante,
)

pytestmark = pytest.mark.postgres

AGORA = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
DIA = date(2026, 11, 10)


@pytest.fixture
def session():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina TEST_DATABASE_URL para executar contra PostgreSQL migrado")
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
    engine.dispose()


@dataclass
class Predio:
    condominio: Condominio
    andar: Andar
    unidade: Unidade
    vizinha: Unidade
    usuario: Usuario
    morador: MoradorUnidade
    funcionario: Funcionario
    arquivo: Arquivo
    area: AreaComum


def criar_predio(session: Session, nome: str = "Aurora") -> Predio:
    usuario = Usuario(nome="Ana", email=f"{uuid.uuid4().hex}@example.test")
    condominio = Condominio(nome=nome, status="ativo")
    session.add_all([usuario, condominio])
    session.flush()
    bloco = Bloco(condominio_id=condominio.id, nome="A")
    session.add(bloco)
    session.flush()
    andar = Andar(condominio_id=condominio.id, bloco_id=bloco.id, nome="1º", ordem=1)
    session.add(andar)
    session.flush()
    unidade = Unidade(condominio_id=condominio.id, andar_id=andar.id, identificacao="101")
    vizinha = Unidade(condominio_id=condominio.id, andar_id=andar.id, identificacao="102")
    arquivo = Arquivo(
        condominio_id=condominio.id,
        chave_storage=f"condominio/{uuid.uuid4().hex}",
        nome_original="nota.jpg",
        tipo_mime="image/jpeg",
        tamanho_bytes=10,
        enviado_por_usuario_id=usuario.id,
    )
    funcionario = Funcionario(condominio_id=condominio.id, nome="Carlos", funcao="porteiro")
    session.add_all([unidade, vizinha, arquivo, funcionario])
    session.flush()
    morador = MoradorUnidade(
        condominio_id=condominio.id, unidade_id=unidade.id, usuario_id=usuario.id, origem="chave"
    )
    area = AreaComum(
        condominio_id=condominio.id,
        nome="Salão",
        foto_arquivo_id=arquivo.id,
        abre_as=time(8),
        fecha_as=time(22),
        capacidade=30,
    )
    session.add_all([morador, area])
    session.flush()
    return Predio(condominio, andar, unidade, vizinha, usuario, morador, funcionario, arquivo, area)


def recusado_por(session: Session, objeto) -> str:
    session.add(objeto)
    with pytest.raises(IntegrityError) as erro:
        session.flush()
    session.rollback()
    assert isinstance(erro.value.orig, psycopg.Error)
    return erro.value.orig.diag.constraint_name or ""


def reserva(p: Predio, unidade: Unidade | None = None, hora: time = time(10), **extra) -> Reserva:
    return Reserva(
        condominio_id=p.condominio.id,
        area_id=p.area.id,
        unidade_id=(unidade or p.unidade).id,
        usuario_id=p.usuario.id,
        data=DIA,
        hora_inicio=hora,
        **extra,
    )


# Reservas (regras 1 a 3)


def test_unidade_so_tem_uma_reserva_ativa_por_area_e_dia(session):
    p = criar_predio(session)
    session.add(reserva(p, hora=time(10)))
    session.flush()
    nome = recusado_por(session, reserva(p, hora=time(15)))
    assert nome == "uq_reservas_unidade_area_dia_ativa"


def test_mesmo_horario_nao_e_reservado_por_duas_unidades(session):
    p = criar_predio(session)
    session.add(reserva(p))
    session.flush()
    nome = recusado_por(session, reserva(p, unidade=p.vizinha))
    assert nome == "uq_reservas_area_horario_ativa"


def test_cancelar_libera_o_horario(session):
    p = criar_predio(session)
    primeira = reserva(p)
    session.add(primeira)
    session.flush()
    primeira.status = "cancelada"
    primeira.cancelada_em = AGORA
    primeira.cancelada_por_usuario_id = p.usuario.id
    session.flush()
    session.add(reserva(p, unidade=p.vizinha))
    session.flush()


def test_reserva_so_em_hora_cheia(session):
    p = criar_predio(session)
    assert recusado_por(session, reserva(p, hora=time(10, 30))) == "ck_reservas_hora_cheia"


def test_cancelamento_pela_administracao_exige_motivo(session):
    p = criar_predio(session)
    reserva_cancelada = reserva(
        p,
        status="cancelada",
        cancelada_em=AGORA,
        cancelada_por_usuario_id=p.usuario.id,
        cancelada_responsavel_id=uuid.uuid4(),
    )
    session.add(reserva_cancelada)
    with pytest.raises(IntegrityError):
        session.flush()


# Chaves de acesso, CNPJ e estrutura (regras 4 a 7 e 18)


def test_chave_de_acesso_e_unica_no_sistema(session):
    p = criar_predio(session)
    outro = criar_predio(session, "Bosque")
    session.add(ChaveAcesso(condominio_id=p.condominio.id, unidade_id=p.unidade.id, codigo="K1"))
    session.flush()
    chave = ChaveAcesso(condominio_id=outro.condominio.id, unidade_id=outro.unidade.id, codigo="K1")
    assert recusado_por(session, chave) == "uq_chaves_acesso_codigo"


def test_unidade_tem_uma_chave_vigente_e_regenerar_revoga_a_anterior(session):
    p = criar_predio(session)
    antiga = ChaveAcesso(condominio_id=p.condominio.id, unidade_id=p.unidade.id, codigo="K1")
    session.add(antiga)
    session.flush()
    segunda = ChaveAcesso(condominio_id=p.condominio.id, unidade_id=p.unidade.id, codigo="K2")
    assert recusado_por(session, segunda) == "uq_chaves_acesso_unidade_vigente"

    p = criar_predio(session)
    antiga = ChaveAcesso(condominio_id=p.condominio.id, unidade_id=p.unidade.id, codigo="K3")
    session.add(antiga)
    session.flush()
    antiga.revogada_em = datetime.now(UTC) + timedelta(minutes=1)
    session.add(ChaveAcesso(condominio_id=p.condominio.id, unidade_id=p.unidade.id, codigo="K4"))
    session.flush()


def test_cnpj_do_condominio_e_unico(session):
    session.add(Condominio(nome="A", cnpj="12345678000199"))
    session.flush()
    assert recusado_por(session, Condominio(nome="B", cnpj="12345678000199")) == (
        "uq_condominios_cnpj"
    )


def test_rejeitar_condominio_exige_motivo(session):
    rejeitado = Condominio(nome="A", status="rejeitado")
    assert recusado_por(session, rejeitado) == "ck_condominios_rejeicao_com_motivo"


def test_identificacao_da_unidade_repete_em_andares_diferentes_mas_nao_no_mesmo(session):
    p = criar_predio(session)
    outro_andar = Andar(
        condominio_id=p.condominio.id, bloco_id=p.andar.bloco_id, nome="2º", ordem=2
    )
    session.add(outro_andar)
    session.flush()
    session.add(
        Unidade(condominio_id=p.condominio.id, andar_id=outro_andar.id, identificacao="101")
    )
    session.flush()
    repetida = Unidade(condominio_id=p.condominio.id, andar_id=p.andar.id, identificacao="101")
    assert recusado_por(session, repetida) == "uq_unidades_andar_identificacao"


# Isolamento entre condomínios (regra 22)


def test_encomenda_nao_aponta_para_unidade_de_outro_condominio(session):
    p = criar_predio(session)
    outro = criar_predio(session, "Bosque")
    encomenda = Encomenda(
        condominio_id=p.condominio.id,
        unidade_id=outro.unidade.id,
        destinatario_morador_unidade_id=p.morador.id,
        descricao="Caixa",
        foto_nota_arquivo_id=p.arquivo.id,
        recebido_por_funcionario_id=p.funcionario.id,
    )
    assert recusado_por(session, encomenda) == "fk_encomendas_unidade"


def test_area_nao_usa_foto_de_outro_condominio(session):
    p = criar_predio(session)
    outro = criar_predio(session, "Bosque")
    area = AreaComum(
        condominio_id=p.condominio.id,
        nome="Piscina",
        foto_arquivo_id=outro.arquivo.id,
        abre_as=time(8),
        fecha_as=time(18),
        capacidade=10,
    )
    assert recusado_por(session, area) == "fk_areas_comuns_foto"


# Portaria (regras 8, 10 a 14)


def encomenda(p: Predio, **extra) -> Encomenda:
    return Encomenda(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade.id,
        destinatario_morador_unidade_id=p.morador.id,
        descricao="Caixa",
        foto_nota_arquivo_id=p.arquivo.id,
        recebido_por_funcionario_id=p.funcionario.id,
        registrada_em=AGORA,
        **extra,
    )


def test_encomenda_entregue_exige_todos_os_dados_da_entrega(session):
    p = criar_predio(session)
    sem_recebedor = encomenda(p, status="entregue_aguardando_confirmacao", entregue_em=AGORA)
    assert recusado_por(session, sem_recebedor) == "ck_encomendas_etapas_completas"


def test_encomenda_percorre_os_tres_estados(session):
    p = criar_predio(session)
    registro = encomenda(p)
    session.add(registro)
    session.flush()
    registro.status = "entregue_aguardando_confirmacao"
    registro.entregue_em = AGORA + timedelta(hours=1)
    registro.recebedor_morador_unidade_id = p.morador.id
    registro.entregue_por_funcionario_id = p.funcionario.id
    session.flush()
    registro.status = "retirada_confirmada"
    registro.confirmada_em = AGORA + timedelta(hours=2)
    registro.confirmado_por_usuario_id = p.usuario.id
    session.flush()


def test_placa_segue_o_formato_brasileiro(session):
    p = criar_predio(session)
    veiculo = Veiculo(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade.id,
        placa="1BC1234",
        marca="Fiat",
        modelo="Uno",
        cor="Branco",
    )
    assert recusado_por(session, veiculo) == "ck_veiculos_placa_formato"


def test_visitante_tem_no_maximo_uma_visita_em_aberto(session):
    p = criar_predio(session)
    visitante = Visitante(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade.id,
        nome="Bruno",
        entrada_prevista=DIA,
        saida_prevista=DIA,
        cadastrado_por_usuario_id=p.usuario.id,
    )
    session.add(visitante)
    session.flush()

    def visita() -> RegistroVisita:
        return RegistroVisita(
            condominio_id=p.condominio.id,
            visitante_id=visitante.id,
            entrada_por_funcionario_id=p.funcionario.id,
        )

    session.add(visita())
    session.flush()
    assert recusado_por(session, visita()) == "uq_registros_visita_em_aberto"


# Vínculos (regra 19)


def test_morador_nao_se_vincula_duas_vezes_a_mesma_unidade(session):
    p = criar_predio(session)
    repetido = MoradorUnidade(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade.id,
        usuario_id=p.usuario.id,
        origem="convite",
    )
    assert recusado_por(session, repetido) == "uq_moradores_unidade_ativo"


# Auditoria só de inserção (regra 21)


@pytest.mark.parametrize(
    "comando",
    [
        "UPDATE registros_auditoria SET acao = 'outra'",
        "DELETE FROM registros_auditoria",
        "TRUNCATE registros_auditoria",
    ],
)
def test_auditoria_recusa_edicao_e_exclusao(session, comando):
    session.add(RegistroAuditoria(acao="condominio.aprovar"))
    session.flush()
    with pytest.raises(DBAPIError, match="apenas INSERT"):
        session.execute(text(comando))


# Cobertura da portaria migrada do rascunho para o esquema oficial.


def dados_encomenda(p: Predio, status: str = "aguardando_retirada", mask: int = 0):
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "condominio_id": p.condominio.id,
        "unidade_id": p.unidade.id,
        "destinatario_morador_unidade_id": p.morador.id,
        "descricao": "Caixa de exemplo",
        "foto_nota_arquivo_id": p.arquivo.id,
        "recebido_por_funcionario_id": p.funcionario.id,
        "status": status,
        "registrada_em": AGORA,
    }
    eventos = (
        ("entregue_em", AGORA + timedelta(minutes=10)),
        ("recebedor_morador_unidade_id", p.morador.id),
        ("entregue_por_funcionario_id", p.funcionario.id),
        ("confirmada_em", AGORA + timedelta(minutes=20)),
        ("confirmado_por_usuario_id", p.usuario.id),
    )
    row.update(
        {name: value if mask & (1 << bit) else None for bit, (name, value) in enumerate(eventos)}
    )
    return row


def test_encomenda_aceita_somente_tres_das_96_combinacoes_de_estado_e_eventos(session):
    p = criar_predio(session)
    permitidas = {
        ("aguardando_retirada", 0),
        ("entregue_aguardando_confirmacao", 7),
        ("retirada_confirmada", 31),
    }
    aceitas = set()
    for status in sorted({status for status, _ in permitidas}):
        for mask in range(32):
            with session.begin_nested() as savepoint:
                comando = Encomenda.__table__.insert().values(dados_encomenda(p, status, mask))
                if (status, mask) in permitidas:
                    session.execute(comando)
                    aceitas.add((status, mask))
                else:
                    with pytest.raises(IntegrityError) as erro:
                        session.execute(comando)
                    assert erro.value.orig.diag.constraint_name == "ck_encomendas_etapas_completas"
                savepoint.rollback()
    assert aceitas == permitidas


@pytest.mark.parametrize("campo", ["entregue_em", "confirmada_em"])
def test_datas_da_encomenda_respeitam_ordem_dos_eventos(session, campo):
    row = dados_encomenda(criar_predio(session), "retirada_confirmada", 31)
    row[campo] = AGORA - timedelta(seconds=1)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(Encomenda.__table__.insert().values(row))


@pytest.mark.parametrize(
    ("campo", "referencia"),
    [
        ("unidade_id", "unidade"),
        ("destinatario_morador_unidade_id", "morador"),
        ("recebedor_morador_unidade_id", "morador"),
        ("recebido_por_funcionario_id", "funcionario"),
        ("entregue_por_funcionario_id", "funcionario"),
        ("foto_nota_arquivo_id", "arquivo"),
    ],
)
def test_referencias_de_encomenda_nao_atravessam_condominios(session, campo, referencia):
    row = dados_encomenda(criar_predio(session), "retirada_confirmada", 31)
    outro = criar_predio(session, "Bosque")
    row[campo] = getattr(outro, referencia).id
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(Encomenda.__table__.insert().values(row))


@pytest.mark.parametrize(
    "campo",
    [
        "condominio_id",
        "unidade_id",
        "destinatario_morador_unidade_id",
        "descricao",
        "foto_nota_arquivo_id",
        "recebido_por_funcionario_id",
        "status",
        "registrada_em",
    ],
)
def test_campos_obrigatorios_de_encomenda_nao_aceitam_nulo(session, campo):
    row = dados_encomenda(criar_predio(session))
    row[campo] = None
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(Encomenda.__table__.insert().values(row))


def test_encomenda_nao_aceita_estado_desconhecido(session):
    row = dados_encomenda(criar_predio(session), "desconhecido")
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(Encomenda.__table__.insert().values(row))
