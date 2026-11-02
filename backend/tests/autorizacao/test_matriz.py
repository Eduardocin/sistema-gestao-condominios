"""A matriz em código, sem banco e sem HTTP."""

import pytest

from app.core import permissoes
from app.core.permissoes import Perfil, interpretar, pode

TODOS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]


def test_a_matriz_tem_os_20_modulos_do_documento():
    assert len(permissoes.RECURSOS) == 20


def test_perfil_ou_recurso_desconhecido_e_negado():
    assert pode("sindico", "encomendas", "ver") is False
    assert pode("morador", "foguetes", "ver") is False
    assert pode(None, "encomendas", "ver") is False


def test_a_acao_apagar_nao_existe_para_ninguem():
    # "Nenhum perfil apaga registro de forma definitiva"
    for perfil in TODOS:
        for recurso in permissoes.RECURSOS:
            assert not pode(perfil, recurso, "apagar")
            assert not pode(perfil, recurso, "excluir")


def test_adm_da_plataforma_nao_toca_no_dia_a_dia_dos_condominios():
    # R8: encomendas, visitantes, veículos, reservas, ocorrências e avisos são negados ao ADM.
    for recurso in ("encomendas", "visitantes", "veiculos", "reservas", "ocorrencias", "avisos"):
        for acao in permissoes.NOMES_DAS_ACOES:
            assert not pode(Perfil.PLATAFORMA, recurso, acao)


def test_so_o_adm_ve_a_auditoria():
    for perfil in TODOS:
        assert pode(perfil, "auditoria", "ver") is (perfil == Perfil.PLATAFORMA)


def test_funcionario_nao_acessa_ocorrencias():
    for acao in permissoes.NOMES_DAS_ACOES:
        assert not pode(Perfil.FUNCIONARIO, "ocorrencias", acao)


@pytest.mark.parametrize("permissao", ["encomendas:ver", "reservas:desativar", "suporte:criar"])
def test_interpretar_aceita_permissoes_validas(permissao):
    recurso, acao = interpretar(permissao)
    assert f"{recurso}:{acao}" == permissao


@pytest.mark.parametrize(
    "permissao",
    ["encomenda:ver", "encomendas:apagar", "encomendas", "", ":ver", "encomendas:", "a:b:c"],
)
def test_interpretar_recusa_permissoes_mal_escritas(permissao):
    with pytest.raises(ValueError):
        interpretar(permissao)
