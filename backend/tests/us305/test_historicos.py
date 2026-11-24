import uuid
from datetime import date, time

import pytest
from sqlalchemy import inspect

from app.modules.auditoria.models import RegistroAuditoria
from app.modules.encomendas.models import Encomenda
from app.modules.funcionarios.models import Funcionario
from app.modules.ocorrencias.models import Ocorrencia
from app.modules.reservas.models import AreaComum, Reserva
from app.modules.storage.models import Arquivo
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
    funcionario = Funcionario(condominio_id=p.condominio.id, nome="Portaria", funcao="porteiro")
    session.add_all([arquivo, funcionario])
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
        foto_nota_arquivo_id=arquivo.id,
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
