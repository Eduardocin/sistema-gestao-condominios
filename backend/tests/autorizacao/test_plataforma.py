"""Rotas `/plataforma/...`: só o ADM da plataforma, e só o que a coluna ADM da matriz permite."""

import pytest

from app.core import permissoes
from app.core.permissoes import Perfil
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de


def test_adm_acessa_a_auditoria(client, predio):
    resposta = client.get(
        "/api/v1/plataforma-teste/auditoria/ver", headers=predio.cabecalho_de(Perfil.PLATAFORMA)
    )
    assert resposta.status_code == 200


def test_adm_obedece_a_matriz_em_todas_as_rotas(client, predio):
    cab = predio.cabecalho_de(Perfil.PLATAFORMA)
    for recurso in sorted(permissoes.RECURSOS):
        for acao in sorted(permissoes.NOMES_DAS_ACOES):
            resposta = client.get(f"/api/v1/plataforma-teste/{recurso}/{acao}", headers=cab)
            esperado = 200 if permissoes.pode(Perfil.PLATAFORMA, recurso, acao) else 403
            assert resposta.status_code == esperado, f"ADM em {recurso}:{acao}"


def test_adm_nao_edita_auditoria(client, predio):
    # Auditoria é "só inserção": o ADM só pode ver.
    cab = predio.cabecalho_de(Perfil.PLATAFORMA)
    assert client.get("/api/v1/plataforma-teste/auditoria/editar", headers=cab).status_code == 403


@pytest.mark.parametrize("perfil", [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO])
def test_perfis_de_condominio_nao_entram_na_plataforma(client, predio, perfil):
    resposta = client.get(
        "/api/v1/plataforma-teste/auditoria/ver", headers=predio.cabecalho_de(perfil)
    )
    assert resposta.status_code == 403


def test_token_dizendo_plataforma_nao_basta(client, session):
    """Quem não é `administrador_plataforma` no banco não entra, por mais que o token diga."""
    comum = criar_usuario(session)  # não é ADM
    token = token_de(comum, None, perfil="plataforma")
    resposta = client.get("/api/v1/plataforma-teste/auditoria/ver", headers=cabecalho(token))
    assert resposta.status_code == 403


def test_sem_token_e_401(client):
    assert client.get("/api/v1/plataforma-teste/auditoria/ver").status_code == 401
