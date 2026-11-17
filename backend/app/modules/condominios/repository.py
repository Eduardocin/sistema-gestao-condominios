"""Bootstrap do condomínio e listagem global estritamente pelos vínculos da conta.

Não há busca arbitrária por ID. Na criação, o escopo dos filhos é o UUID recém-gerado
pelo servidor; o cliente não fornece IDs de condomínio, bloco, andar ou criador.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.condominios.models import Condominio, CondominioAnalise, VinculoCondominio
from app.modules.condominios.schemas import BlocoEntrada, CadastroCondominio, ContagemEstrutura
from app.modules.unidades.models import Andar, Bloco, Unidade


def criar_condominio(
    session: Session, dados: CadastroCondominio, *, usuario_id: uuid.UUID, momento: datetime
) -> Condominio:
    condominio = Condominio(
        nome=dados.nome,
        cnpj=dados.cnpj,
        **dados.endereco.model_dump(),
        status="pendente",
        criado_por_usuario_id=usuario_id,
        enviado_em=momento,
    )
    session.add(condominio)
    session.flush()
    return condominio


def criar_estrutura(
    session: Session, *, condominio_id: uuid.UUID, dados: list[BlocoEntrada]
) -> ContagemEstrutura:
    blocos = [Bloco(condominio_id=condominio_id, nome=bloco.nome, ativo=True) for bloco in dados]
    session.add_all(blocos)
    session.flush()
    # Flush por nível garante as FKs sem consultas/flush para cada unidade.
    andares = [
        (
            Andar(
                condominio_id=condominio_id,
                bloco_id=bloco.id,
                nome=andar.nome,
                ordem=andar.ordem,
                ativo=True,
            ),
            andar,
        )
        for bloco, entrada in zip(blocos, dados, strict=True)
        for andar in entrada.andares
    ]
    session.add_all([andar for andar, _ in andares])
    session.flush()
    unidades = [
        Unidade(
            condominio_id=condominio_id, andar_id=andar.id, identificacao=identificacao, ativo=True
        )
        for andar, entrada in andares
        for identificacao in entrada.unidades
    ]
    session.add_all(unidades)
    session.flush()
    return ContagemEstrutura(blocos=len(blocos), andares=len(andares), unidades=len(unidades))


def vincular_criador(session: Session, *, condominio_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    session.add(
        VinculoCondominio(
            condominio_id=condominio_id, usuario_id=usuario_id, perfil="administracao", ativo=True
        )
    )
    session.flush()


def registrar_envio(
    session: Session, *, condominio_id: uuid.UUID, usuario_id: uuid.UUID, momento: datetime
) -> None:
    session.add(
        CondominioAnalise(
            condominio_id=condominio_id, usuario_id=usuario_id, evento="enviado", criado_em=momento
        )
    )
    session.flush()


def listar_da_administracao(session: Session, usuario_id: uuid.UUID) -> list[Condominio]:
    consulta = (
        select(Condominio)
        .join(VinculoCondominio, VinculoCondominio.condominio_id == Condominio.id)
        .where(
            VinculoCondominio.usuario_id == usuario_id,
            VinculoCondominio.perfil == "administracao",
            VinculoCondominio.ativo.is_(True),
        )
        .order_by(Condominio.nome, Condominio.id)
    )
    return list(session.scalars(consulta))
