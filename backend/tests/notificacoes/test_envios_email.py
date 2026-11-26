"""US-803: o worker esvazia a fila `envios_email` e o ADM acompanha e reenvia."""

import smtplib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.permissoes import Perfil
from app.modules.notificacoes.models import EnvioEmail
from app.modules.notificacoes.service import mascarar, processar_pendentes
from app.modules.notificacoes.smtp import Mensagem
from tests.reservas.cenario import DIA, criar_area, criar_reserva
from tests.test_encomendas_api import criar_encomenda
from tests.test_encomendas_api import criar_funcionario as criar_funcionario_portaria

URL = "/api/v1/plataforma/envios-email"
PERFIS = [Perfil.MORADOR, Perfil.FUNCIONARIO, Perfil.ADMINISTRACAO, Perfil.PLATAFORMA]


class Caixa:
    """Backend de teste: guarda o que foi enviado ou falha como mandarem."""

    def __init__(self, falha: Exception | None = None) -> None:
        self.enviadas: list[Mensagem] = []
        self.falha = falha

    def enviar(self, mensagem: Mensagem) -> None:
        if self.falha is not None:
            raise self.falha
        self.enviadas.append(mensagem)


def fabrica(session):
    """Entrega a sessão do teste sem fechá-la (ela está dentro da transação que desfazemos)."""

    @contextmanager
    def abrir():
        yield session

    return abrir


def rodar(session, backend, **kw):
    return processar_pendentes(fabrica(session), backend, max_tentativas=3, **kw)


def enfileirar(session, predio, evento="condominio_aprovado", **campos) -> EnvioEmail:
    dados = {
        "condominio_id": predio.condominio.id,
        "destinatario": "ana@exemplo.com",
        "evento": evento,
        "recurso_tipo": "condominio",
        "recurso_id": predio.condominio.id,
    }
    dados.update(campos)
    envio = EnvioEmail(**dados)
    session.add(envio)
    session.flush()
    session.refresh(envio)
    return envio


def erro(resposta):
    return resposta.json()["error"]


# --- worker -----------------------------------------------------------------------------------


def test_envia_e_marca_como_enviado(session, predio):
    envio = enfileirar(session, predio)
    caixa = Caixa()

    resultado = rodar(session, caixa)

    assert (resultado.enviados, resultado.falhas) == (1, 0)
    session.refresh(envio)
    assert envio.status == "enviado"
    assert envio.enviado_em is not None
    assert envio.ultimo_erro is None
    [mensagem] = caixa.enviadas
    assert mensagem.destinatario == "ana@exemplo.com"
    assert predio.condominio.nome in mensagem.assunto


def test_nao_reenvia_o_que_ja_foi_enviado(session, predio):
    enfileirar(session, predio)
    caixa = Caixa()
    rodar(session, caixa)
    rodar(session, caixa)
    assert len(caixa.enviadas) == 1


def test_fila_vazia_nao_faz_nada(session, predio):
    assert rodar(session, Caixa()).model_dump() == {"enviados": 0, "falhas": 0, "esgotados": 0}


def test_corpo_da_reserva_cancelada(session, predio):
    area = criar_area(session, predio)
    reserva = criar_reserva(session, predio, area, data=DIA, hora=18, status="cancelada")
    envio = enfileirar(
        session, predio, "reserva_cancelada", recurso_tipo="reserva", recurso_id=reserva.id
    )
    caixa = Caixa()
    rodar(session, caixa)
    session.refresh(envio)
    assert envio.status == "enviado"
    corpo = caixa.enviadas[0].corpo
    assert area.nome in corpo
    assert f"{DIA:%d/%m/%Y}" in corpo
    assert "18:00" in corpo


def test_corpo_da_encomenda_registrada(session, predio):
    funcionario = criar_funcionario_portaria(session, predio)
    encomenda = criar_encomenda(session, predio, funcionario, descricao="Caixa da loja")
    envio = enfileirar(
        session,
        predio,
        "encomenda_registrada",
        recurso_tipo="encomenda",
        recurso_id=encomenda.id,
    )
    caixa = Caixa()
    rodar(session, caixa)
    session.refresh(envio)
    assert envio.status == "enviado"
    assert "Caixa da loja" in caixa.enviadas[0].corpo
    assert predio.unidade_101.identificacao in caixa.enviadas[0].corpo


def test_falha_conta_tentativa_e_guarda_so_o_tipo_do_erro(session, predio):
    envio = enfileirar(session, predio)
    resultado = rodar(session, Caixa(ConnectionRefusedError("ana@exemplo.com recusado")))
    assert (resultado.enviados, resultado.falhas, resultado.esgotados) == (0, 1, 0)
    session.refresh(envio)
    assert (envio.status, envio.tentativas) == ("pendente", 1)
    assert envio.ultimo_erro == "ConnectionRefusedError"
    assert "ana@" not in envio.ultimo_erro


def test_erro_smtp_guarda_o_codigo(session, predio):
    envio = enfileirar(session, predio)
    rodar(session, Caixa(smtplib.SMTPResponseException(451, b"tente depois")))
    session.refresh(envio)
    assert envio.ultimo_erro == "SMTPResponseException 451"


def test_tentativa_nao_se_repete_na_mesma_rodada(session, predio):
    envio = enfileirar(session, predio)
    rodar(session, Caixa(OSError()))
    session.refresh(envio)
    assert envio.tentativas == 1  # uma por rodada: o intervalo do worker espaça as outras


def test_esgotadas_as_tentativas_vira_falhou(session, predio):
    envio = enfileirar(session, predio)
    caixa = Caixa(OSError())
    for _ in range(3):
        resultado = rodar(session, caixa)
    assert resultado.esgotados == 1
    session.refresh(envio)
    assert (envio.status, envio.tentativas) == ("falhou", 3)
    # Falhou não volta sozinho para a fila.
    rodar(session, Caixa())
    session.refresh(envio)
    assert envio.status == "falhou"


def test_falha_de_um_nao_trava_os_outros(session, predio):
    ruim = enfileirar(session, predio, destinatario="ruim@exemplo.com")
    bom = enfileirar(session, predio, destinatario="bom@exemplo.com")

    class Seletivo(Caixa):
        def enviar(self, mensagem):
            if mensagem.destinatario.startswith("ruim"):
                raise OSError
            super().enviar(mensagem)

    caixa = Seletivo()
    resultado = rodar(session, caixa)
    assert (resultado.enviados, resultado.falhas) == (1, 1)
    session.refresh(ruim)
    session.refresh(bom)
    assert (ruim.status, bom.status) == ("pendente", "enviado")


def test_recurso_que_sumiu_falha_de_uma_vez(session, predio):
    envio = enfileirar(
        session,
        predio,
        "reserva_cancelada",
        recurso_tipo="reserva",
        recurso_id=uuid.uuid4(),
    )
    caixa = Caixa()
    resultado = rodar(session, caixa)
    assert resultado.esgotados == 1
    session.refresh(envio)
    assert (envio.status, envio.ultimo_erro) == ("falhou", "recurso_inexistente")
    assert caixa.enviadas == []


def test_recurso_de_outro_condominio_nao_vaza_para_o_corpo(session, predio, outro_predio):
    area = criar_area(session, outro_predio)
    reserva = criar_reserva(session, outro_predio, area, data=DIA, hora=18)
    envio = enfileirar(
        session, predio, "reserva_cancelada", recurso_tipo="reserva", recurso_id=reserva.id
    )
    caixa = Caixa()
    rodar(session, caixa)
    session.refresh(envio)
    assert envio.status == "falhou"
    assert caixa.enviadas == []


def test_recuperacao_de_senha_nao_tem_modelo_aqui(session, predio):
    envio = enfileirar(session, predio, "recuperacao_senha")
    caixa = Caixa()
    rodar(session, caixa)
    session.refresh(envio)
    assert (envio.status, envio.ultimo_erro) == ("falhou", "evento_sem_modelo")
    assert caixa.enviadas == []


def test_respeita_a_ordem_de_chegada(session, predio):
    primeiro = enfileirar(session, predio, destinatario="a@exemplo.com")
    segundo = enfileirar(session, predio, destinatario="b@exemplo.com")
    primeiro.criado_em = datetime(2020, 1, 1, tzinfo=UTC)
    segundo.criado_em = datetime(2020, 1, 2, tzinfo=UTC)
    session.flush()
    caixa = Caixa()
    rodar(session, caixa)
    assert [m.destinatario for m in caixa.enviadas] == ["a@exemplo.com", "b@exemplo.com"]


def test_limite_do_lote(session, predio):
    for i in range(3):
        enfileirar(session, predio, destinatario=f"u{i}@exemplo.com")
    caixa = Caixa()
    rodar(session, caixa, limite=2)
    assert len(caixa.enviadas) == 2


def test_mascara_do_endereco():
    assert mascarar("ana@exemplo.com") == "a***@exemplo.com"
    assert mascarar("sem-arroba") == "***"


# --- acompanhamento ---------------------------------------------------------------------------


@pytest.mark.parametrize("indice", range(len(PERFIS)), ids=[str(p) for p in PERFIS])
def test_so_o_adm_da_plataforma_acompanha_e_reenvia(client, session, predio, indice):
    envio = enfileirar(session, predio, status="falhou", tentativas=3)
    headers = predio.cabecalho_de(PERFIS[indice])
    esperado = PERFIS[indice] == Perfil.PLATAFORMA
    assert (client.get(URL, headers=headers).status_code == 200) is esperado
    assert (client.post(f"{URL}/{envio.id}/reenvio", headers=headers).status_code == 202) is (
        esperado
    )


def test_sem_token_e_401(client):
    assert client.get(URL).status_code == 401
    assert client.post(f"{URL}/{uuid.uuid4()}/reenvio").status_code == 401


def test_lista_com_destinatario_mascarado_e_sem_corpo(client, session, predio):
    enfileirar(session, predio)
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    dados = client.get(URL, headers=adm).json()
    [item] = [i for i in dados["items"] if i["destinatario"] == "a***@exemplo.com"]
    assert set(item) == {
        "id",
        "evento",
        "destinatario",
        "status",
        "tentativas",
        "ultimo_erro",
        "criado_em",
        "enviado_em",
    }


def test_filtros_da_lista(client, session, predio, outro_predio):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    falhou = enfileirar(session, predio, status="falhou", tentativas=3)
    enfileirar(session, predio, "reserva_cancelada", recurso_tipo="reserva")
    alheio = enfileirar(session, outro_predio)

    def ids(**params):
        dados = client.get(URL, headers=adm, params=params).json()
        return {i["id"] for i in dados["items"]}

    assert ids(status="falhou", condominio_id=str(predio.condominio.id)) == {str(falhou.id)}
    assert ids(condominio_id=str(outro_predio.condominio.id)) == {str(alheio.id)}
    assert len(ids(evento="reserva_cancelada", condominio_id=str(predio.condominio.id))) == 1
    hoje = datetime.now(UTC).date()
    assert str(falhou.id) in ids(de=hoje.isoformat(), ate=hoje.isoformat())
    assert (
        ids(ate=(hoje - timedelta(days=30)).isoformat(), condominio_id=str(predio.condominio.id))
        == set()
    )


@pytest.mark.parametrize(
    "params", [{"status": "x"}, {"evento": "x"}, {"de": "ontem"}, {"lixo": "1"}]
)
def test_filtro_invalido_e_422(client, predio, params):
    assert (
        client.get(URL, headers=predio.cabecalho_de(Perfil.PLATAFORMA), params=params).status_code
        == 422
    )


def test_reenvio_recoloca_na_fila_e_o_worker_entrega(client, session, predio):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    envio = enfileirar(session, predio, status="falhou", tentativas=3, ultimo_erro="OSError")

    resposta = client.post(f"{URL}/{envio.id}/reenvio", headers=adm)

    assert resposta.status_code == 202, resposta.text
    corpo = resposta.json()
    assert (corpo["status"], corpo["tentativas"], corpo["ultimo_erro"]) == ("pendente", 0, None)
    caixa = Caixa()
    rodar(session, caixa)
    session.refresh(envio)
    assert envio.status == "enviado"
    assert len(caixa.enviadas) == 1


@pytest.mark.parametrize("status", ["pendente", "enviado"])
def test_so_falhou_pode_ser_reenviado(client, session, predio, status):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    campos = {"enviado_em": datetime.now(UTC)} if status == "enviado" else {}
    envio = enfileirar(session, predio, status=status, **campos)
    resposta = client.post(f"{URL}/{envio.id}/reenvio", headers=adm)
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "envio_nao_falhou"


def test_recuperacao_de_senha_nunca_e_reenviada(client, session, predio):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    envio = enfileirar(session, predio, "recuperacao_senha", status="falhou", tentativas=3)
    session.commit()  # o erro da requisição desfaz a sessão; o que veio antes precisa sobreviver
    resposta = client.post(f"{URL}/{envio.id}/reenvio", headers=adm)
    assert resposta.status_code == 409
    assert erro(resposta)["reason"] == "reenvio_nao_permitido"
    session.refresh(envio)
    assert envio.status == "falhou"


def test_reenvio_de_envio_inexistente_e_404(client, predio):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    assert client.post(f"{URL}/{uuid.uuid4()}/reenvio", headers=adm).status_code == 404


def test_segundo_reenvio_seguido_e_409(client, session, predio):
    adm = predio.cabecalho_de(Perfil.PLATAFORMA)
    envio = enfileirar(session, predio, status="falhou", tentativas=3)
    assert client.post(f"{URL}/{envio.id}/reenvio", headers=adm).status_code == 202
    assert client.post(f"{URL}/{envio.id}/reenvio", headers=adm).status_code == 409
    total = session.scalars(select(EnvioEmail).where(EnvioEmail.id == envio.id)).all()
    assert len(total) == 1
