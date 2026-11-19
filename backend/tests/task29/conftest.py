import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.condominios.models import CondominioAnalise
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import Andar, Bloco
from tests.autorizacao.cenario import montar_predio
from tests.test_contas_perfil_api import client as cliente_postgres
from tests.test_contas_perfil_api import session as sessao_postgres

client = cliente_postgres
session = sessao_postgres


@pytest.fixture
def caso(session):
    a, b = (
        montar_predio(session, f"TASK29-{uuid.uuid4().hex}"),
        montar_predio(session, "Outro prédio"),
    )
    for predio in (a, b):
        predio.condominio.criado_por_usuario_id = predio.administracao.id
        predio.condominio.enviado_em = datetime(2026, 11, 10, tzinfo=UTC)
        predio.condominio.cidade = "Recife"
        predio.condominio.uf = "PE"
    a.condominio.cnpj = "11222333000181"
    b.condominio.cnpj = "11444777000161"
    bloco = Bloco(condominio_id=a.condominio.id, nome="Bloco A")
    session.add(bloco)
    session.flush()
    andar = Andar(condominio_id=a.condominio.id, bloco_id=bloco.id, nome="Térreo", ordem=0)
    session.add(andar)
    session.flush()
    a.unidade_101.andar_id = andar.id
    a.unidade_102.andar_id = andar.id
    responsavel = ResponsavelAdministracao(condominio_id=a.condominio.id, nome="Síndica A")
    outro = ResponsavelAdministracao(condominio_id=b.condominio.id, nome="Síndica B")
    session.add_all([responsavel, outro])
    session.commit()
    return SimpleNamespace(a=a, b=b, responsavel=responsavel, outro=outro, bloco=bloco, andar=andar)


def pendente(session, caso):
    caso.a.condominio.status = "pendente"
    session.add(
        CondominioAnalise(
            condominio_id=caso.a.condominio.id,
            usuario_id=caso.a.administracao.id,
            evento="enviado",
            criado_em=caso.a.condominio.enviado_em,
        )
    )
    session.commit()


def arquivo(session, predio, *, mime="image/png", autor=None, modulo="fotos"):
    id_ = uuid.uuid4()
    item = Arquivo(
        id=id_,
        condominio_id=predio.condominio.id,
        chave_storage=f"condominio/{predio.condominio.id}/{modulo}/{id_}",
        nome_original="foto.png",
        tipo_mime=mime,
        tamanho_bytes=10,
        enviado_por_usuario_id=autor or predio.administracao.id,
    )
    session.add(item)
    session.commit()
    return item
