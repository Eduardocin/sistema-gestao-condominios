"""A dependência `require_permission` em ação: perfil × permissão × resposta esperada."""

import logging

import pytest

from app.core import permissoes
from app.core.permissoes import Perfil
from app.modules.auth.autorizacao import MENSAGEM_SEM_PERMISSAO, require_permission

PERFIS_DE_CONDOMINIO = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO]

# A tabela de casos da task: (perfil, permissão, status esperado). Cada linha vem da seção 7
# da matriz e foi escrita à mão, de propósito, para não repetir o código que está sendo testado.
CASOS = [
    # Encomendas: só o Funcionário registra; Morador vê e confirma; Administração só vê.
    (Perfil.FUNCIONARIO, "encomendas:criar", 200),
    (Perfil.MORADOR, "encomendas:criar", 403),
    (Perfil.ADMINISTRACAO, "encomendas:criar", 403),
    (Perfil.MORADOR, "encomendas:ver", 200),
    (Perfil.ADMINISTRACAO, "encomendas:ver", 200),
    (Perfil.MORADOR, "encomendas:editar", 200),  # confirmar recebimento (regra no service)
    (Perfil.ADMINISTRACAO, "encomendas:editar", 403),
    # Ocorrências: o Funcionário não acessa o módulo.
    (Perfil.FUNCIONARIO, "ocorrencias:ver", 403),
    (Perfil.MORADOR, "ocorrencias:criar", 200),
    (Perfil.ADMINISTRACAO, "ocorrencias:editar", 200),
    (Perfil.ADMINISTRACAO, "ocorrencias:criar", 403),
    # Reservas: o Morador cria e cancela; a Administração cancela qualquer uma, mas não cria.
    (Perfil.MORADOR, "reservas:criar", 200),
    (Perfil.MORADOR, "reservas:desativar", 200),
    (Perfil.ADMINISTRACAO, "reservas:desativar", 200),
    (Perfil.ADMINISTRACAO, "reservas:criar", 403),
    (Perfil.FUNCIONARIO, "reservas:ver", 403),
    # Visitantes e veículos.
    (Perfil.MORADOR, "visitantes:criar", 200),
    (Perfil.FUNCIONARIO, "visitantes:editar", 200),  # registrar entrada e saída
    (Perfil.FUNCIONARIO, "visitantes:desativar", 403),
    (Perfil.FUNCIONARIO, "veiculos:criar", 403),
    (Perfil.ADMINISTRACAO, "veiculos:ver", 200),
    # Estrutura do prédio e chaves de acesso: coisas da Administração.
    (Perfil.ADMINISTRACAO, "estrutura:criar", 200),
    (Perfil.MORADOR, "estrutura:criar", 403),
    (Perfil.FUNCIONARIO, "estrutura:ver", 200),
    (Perfil.ADMINISTRACAO, "chaves_acesso:criar", 200),
    (Perfil.MORADOR, "chaves_acesso:ver", 403),
    (Perfil.FUNCIONARIO, "chaves_acesso:ver", 403),
    (Perfil.MORADOR, "proprietarios:ver", 200),
    (Perfil.FUNCIONARIO, "proprietarios:ver", 403),
    # Permissões por aba: só o Morador (com a aba Usuários, que o service confere).
    (Perfil.MORADOR, "permissoes_aba:editar", 200),
    (Perfil.ADMINISTRACAO, "permissoes_aba:editar", 403),
    # Avisos, comunicados, suporte, auditoria.
    (Perfil.MORADOR, "avisos:ver", 200),
    (Perfil.MORADOR, "avisos:criar", 403),
    (Perfil.FUNCIONARIO, "avisos:criar", 403),
    (Perfil.ADMINISTRACAO, "avisos:criar", 200),
    (Perfil.ADMINISTRACAO, "comunicados:ver", 200),
    (Perfil.ADMINISTRACAO, "comunicados:criar", 403),
    (Perfil.MORADOR, "suporte:ver", 403),
    (Perfil.ADMINISTRACAO, "suporte:criar", 200),
    (Perfil.ADMINISTRACAO, "auditoria:ver", 403),
    # Funcionários e contas compartilhadas.
    (Perfil.FUNCIONARIO, "funcionarios:ver", 200),
    (Perfil.FUNCIONARIO, "funcionarios:criar", 403),
    (Perfil.ADMINISTRACAO, "contas_compartilhadas:editar", 200),
    (Perfil.FUNCIONARIO, "contas_compartilhadas:ver", 403),
    # Conta própria: todos veem; o Funcionário não edita.
    (Perfil.FUNCIONARIO, "conta_propria:ver", 200),
    (Perfil.FUNCIONARIO, "conta_propria:editar", 403),
    (Perfil.MORADOR, "conta_propria:editar", 200),
]


@pytest.mark.parametrize(("perfil", "permissao", "esperado"), CASOS)
def test_tabela_de_casos(client, predio, perfil, permissao, esperado):
    recurso, acao = permissao.split(":")
    resposta = client.get(
        f"/api/v1/permissoes-teste/{recurso}/{acao}", headers=predio.cabecalho_de(perfil)
    )
    assert resposta.status_code == esperado


@pytest.mark.parametrize("perfil", PERFIS_DE_CONDOMINIO)
def test_todas_as_rotas_obedecem_a_matriz(client, predio, perfil):
    """80 rotas × cada perfil: o que a matriz libera dá 200, o resto dá 403. Nada fica de fora."""
    cabecalho = predio.cabecalho_de(perfil)
    for recurso in sorted(permissoes.RECURSOS):
        for acao in sorted(permissoes.NOMES_DAS_ACOES):
            resposta = client.get(f"/api/v1/permissoes-teste/{recurso}/{acao}", headers=cabecalho)
            esperado = 200 if permissoes.pode(perfil, recurso, acao) else 403
            assert resposta.status_code == esperado, f"{perfil} em {recurso}:{acao}"


def test_o_403_tem_o_formato_padrao_e_nao_revela_nada(client, predio):
    resposta = client.get(
        "/api/v1/permissoes-teste/ocorrencias/ver", headers=predio.cabecalho_de(Perfil.FUNCIONARIO)
    )
    assert resposta.status_code == 403
    assert resposta.json() == {"error": {"code": "forbidden", "message": MENSAGEM_SEM_PERMISSAO}}


def test_sem_token_e_401_e_nao_403(client):
    resposta = client.get("/api/v1/permissoes-teste/encomendas/ver")
    assert resposta.status_code == 401


def test_adm_da_plataforma_e_negado_nas_rotas_de_condominio(client, predio):
    # R8: mesmo uma permissão que a coluna ADM tem (auditoria:ver) não vale numa rota de condomínio.
    resposta = client.get(
        "/api/v1/permissoes-teste/auditoria/ver", headers=predio.cabecalho_de(Perfil.PLATAFORMA)
    )
    assert resposta.status_code == 403


def test_perfil_forjado_no_token_nao_vale(client, predio):
    """R6: o claim `perfil` é só para a interface. Quem decide é o vínculo no banco."""
    from tests.isolamento.cenario import cabecalho, token_de

    token_forjado = token_de(predio.morador, predio.condominio.id, perfil="administracao")
    resposta = client.get("/api/v1/permissoes-teste/avisos/criar", headers=cabecalho(token_forjado))
    assert resposta.status_code == 403  # o morador de verdade não cria avisos


def test_mudar_o_perfil_no_banco_vale_na_requisicao_seguinte(client, predio, session):
    cabecalho = predio.cabecalho_de(Perfil.MORADOR)
    url = "/api/v1/permissoes-teste/avisos/criar"
    assert client.get(url, headers=cabecalho).status_code == 403

    predio.vinculo_morador.perfil = "administracao"
    session.flush()

    assert client.get(url, headers=cabecalho).status_code == 200


def test_a_negacao_vai_para_o_log_de_seguranca_sem_dados_sensiveis(client, predio, caplog):
    cabecalho = predio.cabecalho_de(Perfil.FUNCIONARIO)
    with caplog.at_level(logging.WARNING, logger="seguranca"):
        client.get("/api/v1/permissoes-teste/ocorrencias/ver", headers=cabecalho)

    registros = [r.getMessage() for r in caplog.records if r.name == "seguranca"]
    assert len(registros) == 1
    assert "seguranca.acesso_negado" in registros[0]
    assert str(predio.funcionario.id) in registros[0]
    assert "ocorrencias:ver" in registros[0]
    assert cabecalho["Authorization"].split()[1] not in registros[0]  # nunca o token


def test_acesso_permitido_nao_gera_log_de_negacao(client, predio, caplog):
    with caplog.at_level(logging.WARNING, logger="seguranca"):
        client.get(
            "/api/v1/permissoes-teste/encomendas/criar",
            headers=predio.cabecalho_de(Perfil.FUNCIONARIO),
        )
    assert not [r for r in caplog.records if r.name == "seguranca"]


def test_permissao_com_nome_errado_estoura_ao_declarar_a_rota():
    with pytest.raises(ValueError):
        require_permission("encomenda:ver")
