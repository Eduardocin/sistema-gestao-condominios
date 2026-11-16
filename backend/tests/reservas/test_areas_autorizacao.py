"""Áreas comuns: matriz por perfil, 401/403 e isolamento entre condomínios."""

import uuid
from datetime import UTC, datetime

import pytest

from app.core.permissoes import Perfil
from tests.autorizacao.cenario import montar_predio
from tests.isolamento.cenario import cabecalho, token_de, vincular
from tests.reservas.cenario import corpo, criar_area, criar_arquivo, definir_aba

PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]

# (nome, método, caminho, precisa de corpo, área nasce ativa?, status por perfil na ordem de PERFIS)
# Só a Administração escreve. Na reativação a área nasce desativada; nas demais, ativa.
ROTAS = [
    ("listar", "GET", "/areas-comuns", False, True, [200, 403, 200, 403]),
    ("obter", "GET", "/areas-comuns/{id}", False, True, [200, 403, 200, 403]),
    ("criar", "POST", "/areas-comuns", True, True, [403, 403, 201, 403]),
    ("editar", "PUT", "/areas-comuns/{id}", True, True, [403, 403, 200, 403]),
    ("desativar", "POST", "/areas-comuns/{id}/desativacao", False, True, [403, 403, 200, 403]),
    ("reativar", "POST", "/areas-comuns/{id}/reativacao", False, False, [403, 403, 200, 403]),
]
IDS = [rota[0] for rota in ROTAS]


def test_catalogo_exige_aba_e_revogacao_vale_com_o_mesmo_token(client, session, predio):
    area = criar_area(session, predio)
    headers = predio.cabecalho_de(Perfil.MORADOR)
    urls = ["/api/v1/areas-comuns", f"/api/v1/areas-comuns/{area.id}"]
    for acesso, esperado in [(False, 403), (True, 200), (False, 403)]:
        definir_aba(session, predio.morador_unidade, com_acesso=acesso)
        for url in urls:
            assert client.get(url, headers=headers).status_code == esperado


def test_catalogo_aceita_aba_em_outra_unidade_ativa(client, session, predio):
    from app.modules.unidades.models import MoradorUnidade

    definir_aba(session, predio.morador_unidade, com_acesso=False)
    outro_vinculo = MoradorUnidade(
        condominio_id=predio.condominio.id,
        usuario_id=predio.morador.id,
        unidade_id=predio.unidade_102.id,
        origem="cadastro",
    )
    session.add(outro_vinculo)
    session.flush()
    definir_aba(session, outro_vinculo)
    headers = predio.cabecalho_de(Perfil.MORADOR)
    assert client.get("/api/v1/areas-comuns", headers=headers).status_code == 200
    outro_vinculo.status = "desvinculado"
    outro_vinculo.desvinculado_em = datetime.now(UTC)
    session.flush()
    assert client.get("/api/v1/areas-comuns", headers=headers).status_code == 403


def chamar(client, predio, session, rota, perfil):
    _, metodo, caminho, com_corpo, ativa, _ = rota
    area = criar_area(session, predio, ativa=ativa)
    foto = criar_arquivo(session, predio)
    resposta = client.request(
        metodo,
        f"/api/v1{caminho.format(id=area.id)}",
        headers=predio.cabecalho_de(perfil),
        json=corpo(foto.id, nome="Outro nome") if com_corpo else None,
    )
    return resposta


@pytest.mark.parametrize("rota", ROTAS, ids=IDS)
@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_matriz_por_perfil(client, session, predio, rota, indice):
    resposta = chamar(client, predio, session, rota, PERFIS[indice])
    assert resposta.status_code == rota[5][indice], resposta.text


@pytest.mark.parametrize("rota", ROTAS, ids=IDS)
def test_sem_token_e_401(client, rota):
    _, metodo, caminho, com_corpo, _, _ = rota
    resposta = client.request(
        metodo,
        f"/api/v1{caminho.format(id=uuid.uuid4())}",
        json=corpo(uuid.uuid4()) if com_corpo else None,
    )
    assert resposta.status_code == 401


@pytest.mark.parametrize("rota", ROTAS, ids=IDS)
def test_administracao_de_condominio_desativado_e_403(client, session, rota):
    """403 de condomínio vem antes do de perfil e do 404 do recurso."""
    _, metodo, caminho, com_corpo, _, _ = rota
    predio = montar_predio(session)
    predio.condominio.status = "desativado"
    session.flush()
    resposta = client.request(
        metodo,
        f"/api/v1{caminho.format(id=uuid.uuid4())}",
        headers=predio.cabecalho_de(Perfil.ADMINISTRACAO),
        json=corpo(uuid.uuid4()) if com_corpo else None,
    )
    assert resposta.status_code == 403


@pytest.mark.parametrize("perfil", [Perfil.FUNCIONARIO, Perfil.PLATAFORMA])
def test_o_403_de_perfil_vem_antes_do_422_e_do_404(client, predio, perfil):
    cab = predio.cabecalho_de(perfil)
    # Corpo inválido e área inexistente, mas o perfil não pode: 403, nunca 422 ou 404.
    assert client.post("/api/v1/areas-comuns", headers=cab, json={}).status_code == 403
    assert (
        client.put(f"/api/v1/areas-comuns/{uuid.uuid4()}", headers=cab, json={}).status_code == 403
    )
    assert client.get(f"/api/v1/areas-comuns/{uuid.uuid4()}", headers=cab).status_code == 403


def test_o_403_nao_revela_nada(client, predio):
    resposta = client.get("/api/v1/areas-comuns", headers=predio.cabecalho_de(Perfil.FUNCIONARIO))
    assert resposta.json()["error"]["code"] == "forbidden"


def test_perfil_forjado_no_token_nao_vale(client, predio):
    """R6: o claim `perfil` é só da interface. Morador com token de 'administracao' não escreve."""
    token = token_de(predio.morador, predio.condominio.id, perfil="administracao")
    resposta = client.post("/api/v1/areas-comuns", headers=cabecalho(token), json={})
    assert resposta.status_code == 403


def test_vinculo_inativo_perde_o_acesso_na_hora(client, predio):
    predio.vinculo_morador.ativo = False
    resposta = client.get("/api/v1/areas-comuns", headers=predio.cabecalho_de(Perfil.MORADOR))
    assert resposta.status_code == 403


# --- isolamento entre condomínios --------------------------------------------------------------


def test_administracao_de_outro_condominio_recebe_404(client, session, predio, outro_predio):
    area = criar_area(session, predio)
    foto = criar_arquivo(session, outro_predio)
    intruso = outro_predio.cabecalho_de(Perfil.ADMINISTRACAO)
    url = f"/api/v1/areas-comuns/{area.id}"

    assert client.get(url, headers=intruso).status_code == 404
    assert client.put(url, headers=intruso, json=corpo(foto.id)).status_code == 404
    assert client.post(f"{url}/desativacao", headers=intruso, json={}).status_code == 404
    assert client.post(f"{url}/reativacao", headers=intruso, json={}).status_code == 404

    session.refresh(area)
    assert area.ativa is True and area.nome == "Salão de festas"  # nada mudou


def test_morador_de_outro_condominio_recebe_404(client, session, predio, outro_predio):
    area = criar_area(session, predio)
    resposta = client.get(
        f"/api/v1/areas-comuns/{area.id}", headers=outro_predio.cabecalho_de(Perfil.MORADOR)
    )
    assert resposta.status_code == 404


def test_a_lista_nunca_mistura_condominios(client, session, predio, outro_predio):
    criar_area(session, predio, "Salão A")
    criar_area(session, predio, "Quadra A", ativa=False)
    criar_area(session, outro_predio, "Salão B")

    for alvo, esperados in ((predio, {"Salão A", "Quadra A"}), (outro_predio, {"Salão B"})):
        resposta = client.get("/api/v1/areas-comuns", headers=alvo.cabecalho_de("administracao"))
        corpo_json = resposta.json()
        assert {a["nome"] for a in corpo_json["items"]} == esperados
        assert corpo_json["total"] == len(esperados)


def test_o_mesmo_nome_em_condominios_diferentes_e_permitido(client, session, predio, outro_predio):
    for alvo in (predio, outro_predio):
        foto = criar_arquivo(session, alvo)
        resposta = client.post(
            "/api/v1/areas-comuns",
            headers=alvo.cabecalho_de(Perfil.ADMINISTRACAO),
            json=corpo(foto.id, nome="Salão de festas"),
        )
        assert resposta.status_code == 201, resposta.text


def test_condominio_id_no_corpo_e_rejeitado(client, session, predio, outro_predio):
    foto = criar_arquivo(session, predio)
    resposta = client.post(
        "/api/v1/areas-comuns",
        headers=predio.cabecalho_de(Perfil.ADMINISTRACAO),
        json=corpo(foto.id, condominio_id=str(outro_predio.condominio.id)),
    )
    assert resposta.status_code == 422


def test_usuario_de_dois_condominios_so_ve_o_do_token(client, session, predio, outro_predio):
    """Mesmo usuário vinculado aos dois: o `cid` do token decide, nunca o cliente."""
    criar_area(session, predio, "Só do A")
    criar_area(session, outro_predio, "Só do B")
    vincular(session, predio.administracao, outro_predio.condominio, perfil="administracao")
    token = token_de(predio.administracao, outro_predio.condominio.id, perfil="administracao")
    resposta = client.get("/api/v1/areas-comuns", headers=cabecalho(token))
    assert [a["nome"] for a in resposta.json()["items"]] == ["Só do B"]
