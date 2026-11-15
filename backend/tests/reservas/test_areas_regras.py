"""Áreas comuns: validação, nome único, foto, visibilidade, horário e ativação."""

import uuid
from datetime import timedelta

import pytest

from app.core.permissoes import Perfil
from app.modules.reservas.repository import RepositorioArquivos
from tests.reservas.cenario import (
    HOJE,
    amanha,
    corpo,
    criar_area,
    criar_arquivo,
    criar_reserva,
)

URL = "/api/v1/areas-comuns"


@pytest.fixture
def adm(predio):
    return predio.cabecalho_de(Perfil.ADMINISTRACAO)


@pytest.fixture
def morador(predio):
    return predio.cabecalho_de(Perfil.MORADOR)


# --- criação e formato da resposta -------------------------------------------------------------


def test_criar_devolve_201_location_e_o_objeto(client, session, predio, adm):
    foto = criar_arquivo(session, predio)
    resposta = client.post(URL, headers=adm, json=corpo(foto.id))
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()
    assert dados == {
        "id": dados["id"],
        "nome": "Churrasqueira",
        "foto_arquivo_id": str(foto.id),
        "regras": "Limpar após o uso.",
        "abre_as": "09:00",
        "fecha_as": "21:00",
        "capacidade": 20,
        "ativa": True,
    }
    assert resposta.headers["Location"] == f"{URL}/{dados['id']}"
    assert client.get(resposta.headers["Location"], headers=adm).json() == dados


def test_nome_e_aparado_e_regras_e_opcional(client, session, predio, adm):
    foto = criar_arquivo(session, predio)
    corpo_sem_regras = corpo(foto.id, nome="  Sauna  ")
    del corpo_sem_regras["regras"]
    resposta = client.post(URL, headers=adm, json=corpo_sem_regras)
    assert resposta.status_code == 201
    assert resposta.json()["nome"] == "Sauna"
    assert resposta.json()["regras"] is None


def test_limites_validos_sao_aceitos(client, session, predio, adm):
    foto = criar_arquivo(session, predio)
    resposta = client.post(
        URL,
        headers=adm,
        json=corpo(
            foto.id,
            nome="x" * 100,
            regras="r" * 2000,
            abre_as="00:00",
            fecha_as="23:00",
            capacidade=32767,
        ),
    )
    assert resposta.status_code == 201, resposta.text


# --- validação (422) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mudancas",
    [
        {"abre_as": "08:30"},
        {"fecha_as": "21:30"},
        {"abre_as": "8:00"},
        {"abre_as": "08:00:00"},
        {"fecha_as": "24:00"},
        {"abre_as": 8},
        {"abre_as": None},
        {"abre_as": "10:00", "fecha_as": "10:00"},  # fecha == abre: janela de 0h
        {"abre_as": "10:00", "fecha_as": "09:00"},  # fecha < abre
        {"capacidade": 0},
        {"capacidade": -3},
        {"capacidade": 32768},
        {"capacidade": "20"},
        {"capacidade": 2.5},
        {"capacidade": None},
        {"nome": ""},
        {"nome": "   "},
        {"nome": "x" * 101},
        {"nome": None},
        {"regras": "r" * 2001},
        {"foto_arquivo_id": "nao-e-uuid"},
        {"foto_arquivo_id": None},
        {"condominio_id": str(uuid.uuid4())},
        {"ativa": False},
        {"qualquer_coisa": 1},
    ],
    ids=lambda m: ",".join(f"{k}={v!r}"[:40] for k, v in m.items()),
)
def test_corpo_invalido_e_422(client, session, predio, adm, mudancas):
    foto = criar_arquivo(session, predio)
    for resposta in (
        client.post(URL, headers=adm, json=corpo(foto.id, **mudancas)),
        client.put(
            f"{URL}/{criar_area(session, predio).id}", headers=adm, json=corpo(foto.id, **mudancas)
        ),
    ):
        assert resposta.status_code == 422, resposta.text
        assert resposta.json()["error"]["code"] == "validation_error"


def test_foto_ausente_e_422(client, predio, adm):
    sem_foto = corpo(uuid.uuid4())
    del sem_foto["foto_arquivo_id"]
    assert client.post(URL, headers=adm, json=sem_foto).status_code == 422


def test_nenhuma_area_e_gravada_quando_a_entrada_e_invalida(client, session, predio, adm):
    foto = criar_arquivo(session, predio)
    client.post(URL, headers=adm, json=corpo(foto.id, capacidade=0))
    assert client.get(URL, headers=adm).json()["total"] == 0


# --- nome único (409) --------------------------------------------------------------------------


def test_nome_duplicado_ignora_maiusculas_e_espacos(client, session, predio, adm):
    foto = criar_arquivo(session, predio)
    assert (
        client.post(URL, headers=adm, json=corpo(foto.id, nome="Churrasqueira")).status_code == 201
    )

    resposta = client.post(URL, headers=adm, json=corpo(foto.id, nome="  CHURRASQUEIRA "))
    assert resposta.status_code == 409
    erro = resposta.json()["error"]
    assert (erro["code"], erro["reason"]) == ("conflict", "nome_duplicado")

    # O savepoint deixou a sessão sã: o pedido seguinte funciona e só há uma área.
    assert client.post(URL, headers=adm, json=corpo(foto.id, nome="Sauna")).status_code == 201
    assert client.get(URL, headers=adm).json()["total"] == 2


def test_put_com_nome_de_outra_area_e_409(client, session, predio, adm):
    criar_area(session, predio, "Quadra")
    area = criar_area(session, predio, "Piscina")
    foto = criar_arquivo(session, predio)
    resposta = client.put(f"{URL}/{area.id}", headers=adm, json=corpo(foto.id, nome="QUADRA"))
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "nome_duplicado"
    session.refresh(area)
    assert area.nome == "Piscina"


def test_put_mantendo_o_proprio_nome_e_aceito_mesmo_com_outra_caixa(client, session, predio, adm):
    area = criar_area(session, predio, "Piscina")
    foto = criar_arquivo(session, predio)
    resposta = client.put(
        f"{URL}/{area.id}", headers=adm, json=corpo(foto.id, nome="PISCINA", capacidade=10)
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["nome"] == "PISCINA"
    assert resposta.json()["capacidade"] == 10


def test_nome_de_area_desativada_continua_ocupado(client, session, predio, adm):
    criar_area(session, predio, "Quadra", ativa=False)
    foto = criar_arquivo(session, predio)
    resposta = client.post(URL, headers=adm, json=corpo(foto.id, nome="quadra"))
    assert resposta.status_code == 409


# --- foto (422) --------------------------------------------------------------------------------


def test_foto_inexistente_e_422(client, session, predio, adm):
    area = criar_area(session, predio)
    for resposta in (
        client.post(URL, headers=adm, json=corpo(uuid.uuid4())),
        client.put(f"{URL}/{area.id}", headers=adm, json=corpo(uuid.uuid4())),
    ):
        assert resposta.status_code == 422
        erro = resposta.json()["error"]
        assert (erro["code"], erro["reason"]) == ("validation_error", "foto_invalida")


def test_foto_de_outro_condominio_e_422(client, session, predio, outro_predio, adm):
    foto_alheia = criar_arquivo(session, outro_predio)
    resposta = client.post(URL, headers=adm, json=corpo(foto_alheia.id))
    assert resposta.status_code == 422
    assert resposta.json()["error"]["reason"] == "foto_invalida"


def test_arquivo_sem_condominio_nao_serve_de_foto(client, session, predio, adm):
    arquivo_da_conta = criar_arquivo(session, predio, de_condominio=False)
    resposta = client.post(URL, headers=adm, json=corpo(arquivo_da_conta.id))
    assert resposta.status_code == 422


def test_a_fk_composta_e_a_ultima_defesa(client, session, predio, outro_predio, adm, monkeypatch):
    """Se a conferência do repository falhasse, a FK do banco ainda vira 422 `foto_invalida`."""
    monkeypatch.setattr(RepositorioArquivos, "existe", lambda self, arquivo_id: True)
    foto_alheia = criar_arquivo(session, outro_predio)
    area = criar_area(session, predio)

    criar = client.post(URL, headers=adm, json=corpo(foto_alheia.id))
    editar = client.put(f"{URL}/{area.id}", headers=adm, json=corpo(foto_alheia.id))
    for resposta in (criar, editar):
        assert resposta.status_code == 422, resposta.text
        assert resposta.json()["error"]["reason"] == "foto_invalida"


# --- leitura: visibilidade, filtro e paginação -------------------------------------------------


def test_morador_lista_so_ativas_e_nao_consegue_pedir_as_outras(client, session, predio, morador):
    criar_area(session, predio, "Ativa")
    criar_area(session, predio, "Desativada", ativa=False)
    for query in ("", "?ativa=false", "?ativa=true"):
        dados = client.get(f"{URL}{query}", headers=morador).json()
        assert [a["nome"] for a in dados["items"]] == ["Ativa"], query
        assert dados["total"] == 1


def test_morador_recebe_404_na_area_desativada(client, session, predio, morador, adm):
    area = criar_area(session, predio, ativa=False)
    assert client.get(f"{URL}/{area.id}", headers=morador).status_code == 404
    assert client.get(f"{URL}/{area.id}", headers=adm).status_code == 200  # a Administração vê


def test_administracao_filtra_por_ativa(client, session, predio, adm):
    criar_area(session, predio, "B ativa")
    criar_area(session, predio, "A inativa", ativa=False)

    def nomes(query):
        return [a["nome"] for a in client.get(f"{URL}{query}", headers=adm).json()["items"]]

    assert nomes("") == ["A inativa", "B ativa"]  # todas, por nome
    assert nomes("?ativa=true") == ["B ativa"]
    assert nomes("?ativa=false") == ["A inativa"]


def test_paginacao(client, session, predio, adm):
    for nome in ("a1", "b2", "c3"):
        criar_area(session, predio, nome)
    pagina_1 = client.get(f"{URL}?page_size=2", headers=adm).json()
    pagina_2 = client.get(f"{URL}?page=2&page_size=2", headers=adm).json()
    assert (pagina_1["page"], pagina_1["page_size"], pagina_1["total"]) == (1, 2, 3)
    assert [a["nome"] for a in pagina_1["items"]] == ["a1", "b2"]
    assert [a["nome"] for a in pagina_2["items"]] == ["c3"]


@pytest.mark.parametrize("query", ["?page=0", "?page_size=0", "?page_size=101", "?ativa=talvez"])
def test_paginacao_invalida_e_422(client, adm, query):
    assert client.get(f"{URL}{query}", headers=adm).status_code == 422


def test_area_inexistente_e_404(client, adm):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=adm).status_code == 404


# --- horário x reservas ativas -----------------------------------------------------------------


def _put_horario(client, adm, area, foto, abre, fecha):
    return client.put(
        f"{URL}/{area.id}", headers=adm, json=corpo(foto.id, abre_as=abre, fecha_as=fecha)
    )


def test_put_que_deixa_reserva_ativa_futura_fora_do_horario_e_409(client, session, predio, adm):
    area = criar_area(session, predio)  # 08:00 a 22:00
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, area, data=amanha(), hora=20)  # slot 20:00-21:00

    resposta = _put_horario(client, adm, area, foto, "08:00", "20:00")  # fecha antes do fim
    assert resposta.status_code == 409
    erro = resposta.json()["error"]
    assert (erro["code"], erro["reason"]) == ("conflict", "reservas_fora_do_horario")

    resposta = _put_horario(client, adm, area, foto, "21:00", "22:00")  # abre depois do início
    assert resposta.status_code == 409

    session.refresh(area)
    assert (area.abre_as.hour, area.fecha_as.hour) == (8, 22)  # nada foi gravado


def test_reserva_que_ainda_cabe_nao_bloqueia(client, session, predio, adm):
    area = criar_area(session, predio)
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, area, data=amanha(), hora=20)
    assert _put_horario(client, adm, area, foto, "08:00", "21:00").status_code == 200  # 20-21 cabe
    assert (
        _put_horario(client, adm, area, foto, "20:00", "22:00").status_code == 200
    )  # começa às 20


def test_reserva_de_hoje_bloqueia(client, session, predio, adm):
    area = criar_area(session, predio)
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, area, data=HOJE, hora=21)
    assert _put_horario(client, adm, area, foto, "08:00", "21:00").status_code == 409


def test_reserva_cancelada_ou_passada_nao_bloqueia(client, session, predio, adm):
    area = criar_area(session, predio)
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, area, data=amanha(), hora=21, status="cancelada")
    criar_reserva(session, predio, area, data=HOJE - timedelta(days=1), hora=21)
    assert _put_horario(client, adm, area, foto, "08:00", "10:00").status_code == 200


def test_reserva_de_outra_area_nao_bloqueia(client, session, predio, adm):
    area = criar_area(session, predio, "Salão")
    outra = criar_area(session, predio, "Quadra")
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, outra, data=amanha(), hora=21)
    assert _put_horario(client, adm, area, foto, "08:00", "10:00").status_code == 200


def test_put_sem_mudar_o_horario_nao_consulta_reservas(client, session, predio, adm):
    area = criar_area(session, predio)  # 08:00 a 22:00
    foto = criar_arquivo(session, predio)
    criar_reserva(session, predio, area, data=amanha(), hora=23)  # já estava fora do horário
    resposta = client.put(
        f"{URL}/{area.id}",
        headers=adm,
        json=corpo(foto.id, nome="Salão novo", abre_as="08:00", fecha_as="22:00"),
    )
    assert resposta.status_code == 200, resposta.text


# --- desativar e reativar ----------------------------------------------------------------------


def test_desativar_reativar_e_repetir(client, session, predio, adm):
    area = criar_area(session, predio)
    base = f"{URL}/{area.id}"

    resposta = client.post(f"{base}/desativacao", headers=adm, json={})
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is False

    resposta = client.post(f"{base}/desativacao", headers=adm, json={})
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "area_ja_desativada"

    resposta = client.post(f"{base}/reativacao", headers=adm, json={})
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is True

    resposta = client.post(f"{base}/reativacao", headers=adm)  # sem corpo também vale
    assert resposta.status_code == 409
    assert resposta.json()["error"]["reason"] == "area_ja_ativa"

    assert client.post(f"{base}/desativacao", headers=adm).status_code == 200  # sem corpo


@pytest.mark.parametrize("acao", ["desativacao", "reativacao"])
def test_acao_com_campo_no_corpo_e_422(client, session, predio, adm, acao):
    area = criar_area(session, predio)
    resposta = client.post(f"{URL}/{area.id}/{acao}", headers=adm, json={"motivo": "x"})
    assert resposta.status_code == 422


def test_desativar_nao_mexe_nas_reservas(client, session, predio, adm):
    area = criar_area(session, predio)
    reserva = criar_reserva(session, predio, area, data=amanha(), hora=10)
    assert client.post(f"{URL}/{area.id}/desativacao", headers=adm, json={}).status_code == 200
    session.refresh(reserva)
    assert reserva.status == "ativa"


def test_put_nao_reativa_nem_desativa(client, session, predio, adm):
    area = criar_area(session, predio, ativa=False)
    foto = criar_arquivo(session, predio)
    resposta = client.put(f"{URL}/{area.id}", headers=adm, json=corpo(foto.id))
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is False
