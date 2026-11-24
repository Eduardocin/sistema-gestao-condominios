import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.condominios.models import VinculoCondominio
from tests.isolamento.cenario import criar_usuario, vincular
from tests.us210.conftest import CONTA, dados
from tests.us210.test_conta import conta

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("ativo", [True, False])
@pytest.mark.parametrize("colisao", ["condominio", "usuario"])
def test_unicidade_no_banco_inclui_inativos(client, session, caso, ativo, colisao):
    assert client.put(CONTA, headers=caso.a.headers, json=dados(caso)).status_code == 200
    usuario, existente = conta(session, caso)
    existente.ativo = ativo
    session.flush()
    outro_usuario = criar_usuario(session) if colisao == "condominio" else usuario
    novo = VinculoCondominio(
        usuario_id=outro_usuario.id,
        condominio_id=(caso.a if colisao == "condominio" else caso.b).condominio.id,
        perfil="funcionario",
        ativo=False,
    )
    with pytest.raises(IntegrityError) as erro:
        with session.begin_nested():
            session.add(novo)
            session.flush()
    assert erro.value.orig.diag.constraint_name == f"uq_vinculos_funcionario_{colisao}"


def test_nao_restringe_multiplos_condominios_da_administracao(session, caso):
    vincular(session, caso.a.administracao, caso.b.condominio, perfil="administracao")
    session.flush()
