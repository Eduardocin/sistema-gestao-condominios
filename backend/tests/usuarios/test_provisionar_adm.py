import pytest
from sqlalchemy import select

from app.modules.auth.security import verificar_senha
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.provisionar_adm import ErroDeProvisionamento, main, provisionar
from tests.autorizacao.conftest import session as session  # noqa: F401

pytestmark = pytest.mark.postgres


def test_cria_adm_da_plataforma_sem_cadastro_nem_vinculo(session):
    usuario = provisionar(
        session, nome="  Ana   Souza ", email=" ADM@Exemplo.COM ", senha="Senha1234"
    )
    salvo = session.scalar(select(Usuario).where(Usuario.id == usuario.id))
    assert salvo is not None
    assert salvo.email == "adm@exemplo.com"
    assert salvo.nome == "Ana Souza"
    assert salvo.administrador_plataforma is True
    assert salvo.ativo is True
    assert salvo.tipo_cadastro is None
    assert salvo.telefone is None and salvo.documento is None
    assert salvo.senha_hash and salvo.senha_hash != "Senha1234"
    assert verificar_senha("Senha1234", salvo.senha_hash)


@pytest.mark.parametrize(
    ("campos", "trecho"),
    [
        ({"email": "sem-arroba"}, "e-mail"),
        ({"senha": "curta1"}, "Senha"),
        ({"senha": "somenteletras"}, "Senha"),
        ({"senha": "12345678"}, "Senha"),
        ({"senha": "adm@exemplo.com"}, "Senha"),
        ({"nome": "Al"}, "nome"),
    ],
)
def test_recusa_entradas_invalidas(session, campos, trecho):
    dados = {"nome": "Ana Souza", "email": "adm@exemplo.com", "senha": "Senha1234", **campos}
    with pytest.raises(ErroDeProvisionamento, match=trecho):
        provisionar(session, **dados)
    assert session.scalar(select(Usuario).where(Usuario.email == "adm@exemplo.com")) is None


def test_nao_promove_conta_existente(session):
    existente = Usuario(
        nome="Morador", email="adm@exemplo.com", senha_hash="x", tipo_cadastro="morador"
    )
    session.add(existente)
    session.flush()
    with pytest.raises(ErroDeProvisionamento, match="Já existe"):
        provisionar(session, nome="Ana Souza", email="ADM@exemplo.com", senha="Senha1234")
    session.refresh(existente)
    assert existente.administrador_plataforma is False


def test_comando_falha_com_codigo_1_e_mensagem_sem_senha(monkeypatch, capsys):
    monkeypatch.setenv("ADM_SENHA", "curta")
    assert main(["--nome", "Ana Souza", "--email", "adm@exemplo.com"]) == 1
    saida = capsys.readouterr()
    assert "Senha inválida" in saida.err
    assert "curta" not in saida.out + saida.err
