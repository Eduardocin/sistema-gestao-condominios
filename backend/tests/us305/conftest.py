import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.tempo import get_relogio
from app.modules.auth.security import hash_senha
from app.modules.condominios.models import VinculoCondominio
from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.unidades.models import ABAS_MORADOR, ChaveAcesso, MoradorUnidade, PermissaoAba
from app.modules.unidades.service import gerar_codigo
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import montar_predio
from tests.isolamento.cenario import cabecalho, token_de
from tests.test_contas_perfil_api import client as client
from tests.test_contas_perfil_api import session as session

SENHA = "SenhaMorador305"
HASH = hash_senha(SENHA)
ACAO = "vinculo.desfazer"


def permissoes(session, associacao, *, gestor):
    session.add_all(
        [
            PermissaoAba(
                condominio_id=associacao.condominio_id,
                morador_unidade_id=associacao.id,
                aba=aba,
                com_acesso=gestor or aba != "usuarios",
            )
            for aba in ABAS_MORADOR
        ]
    )
    session.flush()


def morador(session, predio, *, unidade=None, usuario=None, gestor=False):
    if usuario is None:
        usuario = Usuario(
            nome="Morador US305",
            email=f"{uuid.uuid4().hex}@example.test",
            tipo_cadastro="morador",
            senha_hash=HASH,
        )
        session.add(usuario)
        session.flush()
    vinculo = session.scalar(
        select(VinculoCondominio).where(
            VinculoCondominio.usuario_id == usuario.id,
            VinculoCondominio.condominio_id == predio.condominio.id,
        )
    )
    if vinculo is None:
        vinculo = VinculoCondominio(
            usuario_id=usuario.id, condominio_id=predio.condominio.id, perfil="morador"
        )
        session.add(vinculo)
    associacao = MoradorUnidade(
        usuario_id=usuario.id,
        condominio_id=predio.condominio.id,
        unidade_id=(unidade or predio.unidade_101).id,
        origem="chave",
    )
    session.add(associacao)
    session.flush()
    permissoes(session, associacao, gestor=gestor)
    return SimpleNamespace(usuario=usuario, vinculo=vinculo, associacao=associacao)


def chave(session, predio, unidade=None):
    item = ChaveAcesso(
        condominio_id=predio.condominio.id,
        unidade_id=(unidade or predio.unidade_101).id,
        codigo=gerar_codigo(),
        criada_em=datetime.now(UTC) - timedelta(days=1),
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture
def caso(session, client):
    a, b = montar_predio(session, "US305 A"), montar_predio(session, "US305 B")
    a.morador.tipo_cadastro = "morador"
    a.morador.senha_hash = HASH
    permissoes(session, a.morador_unidade, gestor=True)
    alvo = morador(session, a)
    responsavel = ResponsavelAdministracao(condominio_id=a.condominio.id, nome="Síndica US305")
    outro = ResponsavelAdministracao(condominio_id=b.condominio.id, nome="Síndica B")
    session.add_all([responsavel, outro])
    key = chave(session, a)
    session.commit()
    momento = datetime.now(UTC) + timedelta(minutes=1)
    client.app.dependency_overrides[get_relogio] = lambda: lambda: momento
    return SimpleNamespace(
        a=a, b=b, alvo=alvo, responsavel=responsavel, outro=outro, chave=key, momento=momento
    )


def rota(unidade_id, morador_id):
    return f"/api/v1/unidades/{unidade_id}/moradores/{morador_id}/desvinculacao"


def desfazer(
    client, caso, *, associacao=None, unidade=None, perfil="administracao", corpo=None, headers=None
):
    if corpo is None:
        corpo = {"responsavel_id": str(caso.responsavel.id)} if perfil == "administracao" else {}
    return client.post(
        rota(unidade or caso.a.unidade_101.id, (associacao or caso.alvo.associacao).id),
        headers=headers or caso.a.cabecalho_de(perfil),
        json=corpo,
    )


def headers_morador(usuario, condominio_id):
    return cabecalho(token_de(usuario, condominio_id, perfil="morador"))
