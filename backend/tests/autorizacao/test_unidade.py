"""Passo 4 da ordem de checagem (R10): a unidade que veio na requisição é do usuário?"""

import uuid

from app.core.permissoes import Perfil
from tests.autorizacao.cenario import criar_unidade, montar_predio


def ver(client, predio, perfil, unidade_id):
    return client.get(f"/api/v1/unidades-teste/{unidade_id}", headers=predio.cabecalho_de(perfil))


def test_morador_acessa_a_propria_unidade(client, predio):
    assert ver(client, predio, Perfil.MORADOR, predio.unidade_101.id).status_code == 200


def test_morador_nao_acessa_outra_unidade_do_mesmo_condominio(client, predio):
    resposta = ver(client, predio, Perfil.MORADOR, predio.unidade_102.id)
    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "not_found"


def test_morador_nao_acessa_unidade_de_outro_condominio(client, predio, session):
    outro = montar_predio(session, "Residencial Outro")
    assert ver(client, predio, Perfil.MORADOR, outro.unidade_101.id).status_code == 404


def test_o_404_de_unidade_alheia_e_igual_ao_de_unidade_inexistente(client, predio):
    alheia = ver(client, predio, Perfil.MORADOR, predio.unidade_102.id)
    inexistente = ver(client, predio, Perfil.MORADOR, uuid.uuid4())
    assert alheia.status_code == inexistente.status_code == 404
    assert alheia.content == inexistente.content  # nada denuncia que a 102 existe


def test_funcionario_e_administracao_acessam_qualquer_unidade_do_condominio(client, predio):
    for perfil in (Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO):
        for unidade in (predio.unidade_101, predio.unidade_102):
            assert ver(client, predio, perfil, unidade.id).status_code == 200


def test_funcionario_e_administracao_nao_acessam_unidade_de_outro_condominio(
    client, predio, session
):
    outro = montar_predio(session, "Residencial Outro")
    for perfil in (Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO):
        assert ver(client, predio, perfil, outro.unidade_101.id).status_code == 404


def test_morador_sem_unidade_nao_acessa_nenhuma(client, predio, session):
    predio.vinculo_morador.unidade_id = None
    session.flush()
    assert ver(client, predio, Perfil.MORADOR, predio.unidade_101.id).status_code == 404


def test_morador_desvinculado_perde_o_acesso_na_hora(client, predio, session):
    predio.vinculo_morador.ativo = False
    session.flush()
    # Vínculo inativo é barrado antes, no passo 2 (403), e a unidade nem chega a ser olhada.
    assert ver(client, predio, Perfil.MORADOR, predio.unidade_101.id).status_code == 403


def test_unidade_nova_do_condominio_aparece_para_a_administracao(client, predio, session):
    nova = criar_unidade(session, predio.condominio, "Bloco B / 201")
    assert ver(client, predio, Perfil.ADMINISTRACAO, nova.id).status_code == 200
