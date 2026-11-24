import uuid
from datetime import date, time

import pytest
from sqlalchemy import inspect, select

from app.core.contexto import ContextoCondominio
from app.core.errors import RecursoNaoEncontrado
from app.modules.auditoria.models import RegistroAuditoria
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.notificacoes.models import EnvioEmail
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.reservas.models import AreaComum, Reserva
from app.modules.storage.models import Arquivo
from app.modules.storage.policy import autorizar_download
from app.modules.visitantes.models import RegistroVisita, Veiculo, Visitante
from tests.us305.conftest import desfazer, headers_morador, morador

pytestmark = pytest.mark.postgres


def test_registros_e_autores_preservados_com_acesso_pelas_permissoes_atuais(client, session, caso):
    p = caso.a
    alvo = caso.alvo
    morador(session, p, usuario=alvo.usuario, unidade=p.unidade_102, gestor=True)
    arquivo = Arquivo(
        condominio_id=p.condominio.id,
        chave_storage=f"teste-us305/{uuid.uuid4()}",
        nome_original="foto.jpg",
        tipo_mime="image/jpeg",
        tamanho_bytes=10,
        enviado_por_usuario_id=alvo.usuario.id,
    )
    foto_id = uuid.uuid4()
    foto_encomenda = Arquivo(
        id=foto_id,
        condominio_id=p.condominio.id,
        chave_storage=f"condominio/{p.condominio.id}/encomendas/{foto_id}",
        nome_original="nota.jpg",
        tipo_mime="image/jpeg",
        tamanho_bytes=10,
        enviado_por_usuario_id=alvo.usuario.id,
    )
    funcionario = Funcionario(condominio_id=p.condominio.id, nome="Portaria", funcao="porteiro")
    session.add_all([arquivo, foto_encomenda, funcionario])
    session.flush()
    area = AreaComum(
        condominio_id=p.condominio.id,
        nome="Salão",
        foto_arquivo_id=arquivo.id,
        abre_as=time(8),
        fecha_as=time(22),
        capacidade=10,
    )
    visitante = Visitante(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        nome="Visita histórica",
        entrada_prevista=date(2030, 1, 1),
        saida_prevista=date(2030, 1, 2),
        cadastrado_por_usuario_id=alvo.usuario.id,
    )
    session.add_all([area, visitante])
    session.flush()
    veiculo = Veiculo(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        placa="ABC1D23",
        marca="Fiat",
        modelo="Argo",
        cor="Prata",
    )
    ocorrencia = Ocorrencia(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        aberta_por_usuario_id=alvo.usuario.id,
        titulo="Histórico",
        detalhe="Registro preservado",
    )
    reserva = Reserva(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        area_id=area.id,
        usuario_id=alvo.usuario.id,
        data=date(2030, 1, 1),
        hora_inicio=time(10),
    )
    encomenda = Encomenda(
        condominio_id=p.condominio.id,
        unidade_id=p.unidade_101.id,
        destinatario_morador_unidade_id=alvo.associacao.id,
        descricao="Encomenda histórica",
        foto_nota_arquivo_id=foto_encomenda.id,
        recebido_por_funcionario_id=funcionario.id,
    )
    visita = RegistroVisita(
        condominio_id=p.condominio.id,
        visitante_id=visitante.id,
        entrada_por_funcionario_id=funcionario.id,
    )
    anterior = RegistroAuditoria(
        condominio_id=p.condominio.id,
        usuario_id=alvo.usuario.id,
        perfil="morador",
        acao="registro.historico",
        recurso_tipo="morador_unidade",
        recurso_id=alvo.associacao.id,
    )
    objetos = [
        arquivo,
        foto_encomenda,
        funcionario,
        area,
        visitante,
        veiculo,
        ocorrencia,
        reserva,
        encomenda,
        visita,
        anterior,
    ]
    session.add_all(objetos)
    session.commit()
    snapshots = [
        (
            type(obj),
            obj.id,
            {coluna.key: getattr(obj, coluna.key) for coluna in inspect(obj).mapper.column_attrs},
        )
        for obj in objetos
    ]
    headers = headers_morador(alvo.usuario, p.condominio.id)
    contexto_alvo = ContextoCondominio(
        usuario_id=alvo.usuario.id,
        condominio_id=p.condominio.id,
        perfil="morador",
        vinculo_id=alvo.vinculo.id,
    )
    autorizar_download(session, contexto_alvo, foto_encomenda, alvo.usuario)
    params = {"unidade_id": str(p.unidade_101.id)}
    for modulo in ("encomendas", "reservas", "ocorrencias"):
        resposta = client.get(f"/api/v1/{modulo}", headers=headers, params=params)
        assert resposta.status_code == 200 and resposta.json()["total"] == 1
    rotas = [
        f"/api/v1/{modulo}/{obj.id}"
        for modulo, obj in (
            ("visitantes", visitante),
            ("veiculos", veiculo),
            ("ocorrencias", ocorrencia),
            ("reservas", reserva),
            ("encomendas", encomenda),
        )
    ]
    for rota in rotas:
        assert client.get(rota, headers=headers).status_code == 200
    assert desfazer(client, caso).status_code == 200
    session.expire_all()
    for modelo, id_, antes in snapshots:
        obj = session.get(modelo, id_)
        assert obj is not None
        assert {
            coluna.key: getattr(obj, coluna.key) for coluna in inspect(obj).mapper.column_attrs
        } == antes
    for rota in rotas:
        assert client.get(rota, headers=headers).status_code == 404
        assert client.get(rota, headers=p.cabecalho_de("morador")).status_code == 200
    # Mesmo JWT continua legítimo na outra unidade, mas não alcança os fluxos da removida.
    assert (
        client.get(f"/api/v1/minhas-unidades/{p.unidade_102.id}", headers=headers).status_code
        == 200
    )
    for modulo in ("encomendas", "reservas", "ocorrencias"):
        assert client.get(f"/api/v1/{modulo}", headers=headers, params=params).status_code == 404
    for acao in ("comentarios", "reabertura"):
        assert (
            client.post(
                f"/api/v1/ocorrencias/{ocorrencia.id}/{acao}",
                headers=headers,
                json={"texto": "Pedido depois da desvinculação"},
            ).status_code
            == 404
        )
    assert (
        client.post(
            f"/api/v1/reservas/{reserva.id}/cancelamento", headers=headers, json={}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/reservas",
            headers=headers,
            json={**params, "area_id": str(area.id), "data": "2030-01-01", "hora_inicio": "11:00"},
        ).status_code
        == 404
    )
    with pytest.raises(RecursoNaoEncontrado):
        autorizar_download(session, contexto_alvo, foto_encomenda, alvo.usuario)
    administracao = p.cabecalho_de("administracao")
    relatorio = client.get("/api/v1/encomendas/relatorio", headers=administracao, params=params)
    assert relatorio.status_code == 200 and relatorio.json()["totais"]["registradas"] == 1
    assert client.get("/api/v1/encomendas/relatorio", headers=headers).status_code == 403
    bloqueios = f"/api/v1/areas-comuns/{area.id}/bloqueios"
    assert client.get(bloqueios, headers=headers).status_code == 403
    bloqueio = client.post(
        bloqueios,
        headers=administracao,
        json={
            "data_inicio": "2030-01-01",
            "data_fim": "2030-01-01",
            "motivo": "Manutenção",
            "responsavel_id": str(caso.responsavel.id),
            "confirmar_cancelamentos": True,
        },
    )
    assert bloqueio.status_code == 201 and bloqueio.json()["reservas_canceladas"] == 1
    session.refresh(reserva)
    assert reserva.status == "cancelada"
    envio = session.scalar(select(EnvioEmail).where(EnvioEmail.recurso_id == reserva.id))
    assert envio.evento == "reserva_cancelada" and envio.destinatario == alvo.usuario.email
