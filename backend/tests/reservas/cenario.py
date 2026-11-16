"""Dados dos testes das áreas comuns. Tudo é criado direto pelos models (não há upload ainda)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.modules.funcionarios.models import ResponsavelAdministracao
from app.modules.reservas.models import AreaComum, BloqueioArea, Reserva
from app.modules.storage.models import Arquivo
from app.modules.unidades.models import MoradorUnidade, PermissaoAba, Unidade
from app.modules.usuarios.models import Usuario
from tests.autorizacao.cenario import Predio
from tests.isolamento.cenario import cabecalho, criar_usuario, token_de, vincular

HOJE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def criar_arquivo(session: Session, predio: Predio, *, de_condominio: bool = True) -> Arquivo:
    arquivo = Arquivo(
        condominio_id=predio.condominio.id if de_condominio else None,
        chave_storage=f"teste/{uuid.uuid4().hex}.jpg",
        nome_original="foto.jpg",
        tipo_mime="image/jpeg",
        tamanho_bytes=1024,
        enviado_por_usuario_id=predio.administracao.id,
    )
    session.add(arquivo)
    session.flush()
    return arquivo


def criar_area(
    session: Session, predio: Predio, nome: str = "Salão de festas", **campos: Any
) -> AreaComum:
    valores: dict[str, Any] = {
        "foto_arquivo_id": criar_arquivo(session, predio).id,
        "regras": None,
        "abre_as": time(8),
        "fecha_as": time(22),
        "capacidade": 40,
        "ativa": True,
    }
    valores.update(campos)
    area = AreaComum(condominio_id=predio.condominio.id, nome=nome, **valores)
    session.add(area)
    session.flush()
    return area


def criar_reserva(
    session: Session,
    predio: Predio,
    area: AreaComum,
    *,
    data: date,
    hora: int,
    status: str = "ativa",
    unidade: Unidade | None = None,
    usuario: Usuario | None = None,
) -> Reserva:
    """Reserva gravada direto (sem as regras do service), por padrão da 101 e do morador dela."""
    cancelada: dict[str, Any] = {}
    if status == "cancelada":
        cancelada = {
            "cancelada_em": datetime.now(UTC),
            "cancelada_por_usuario_id": predio.morador.id,
        }
    reserva = Reserva(
        condominio_id=predio.condominio.id,
        area_id=area.id,
        unidade_id=(unidade or predio.unidade_101).id,
        usuario_id=(usuario or predio.morador).id,
        data=data,
        hora_inicio=time(hora),
        status=status,
        **cancelada,
    )
    session.add(reserva)
    session.flush()
    return reserva


def corpo(foto_id: uuid.UUID, /, **campos: Any) -> dict[str, Any]:
    """Corpo válido de POST/PUT; `campos` sobrescreve (ou acrescenta) campos, inclusive a foto."""
    base: dict[str, Any] = {
        "nome": "Churrasqueira",
        "foto_arquivo_id": str(foto_id),
        "regras": "Limpar após o uso.",
        "abre_as": "09:00",
        "fecha_as": "21:00",
        "capacidade": 20,
    }
    base.update(campos)
    return base


def amanha() -> date:
    return HOJE + timedelta(days=1)


# --- Fase 2: reservas -----------------------------------------------------------------------

FUSO = ZoneInfo("America/Sao_Paulo")
# Relógio congelado dos testes de reserva: segunda-feira, 10/06/2030, 14:30 em São Paulo.
AGORA = datetime(2030, 6, 10, 14, 30, tzinfo=FUSO)
HOJE_CONGELADO = AGORA.date()
DIA = HOJE_CONGELADO + timedelta(days=1)  # um dia futuro qualquer
ONTEM = HOJE_CONGELADO - timedelta(days=1)


def definir_aba(
    session: Session,
    morador_unidade: MoradorUnidade,
    *,
    aba: str = "reservas",
    com_acesso: bool = True,
) -> None:
    """Cria ou troca a linha da aba do morador nesta unidade."""
    linha = session.get(PermissaoAba, (morador_unidade.id, aba))
    if linha is None:
        session.add(
            PermissaoAba(
                condominio_id=morador_unidade.condominio_id,
                morador_unidade_id=morador_unidade.id,
                aba=aba,
                com_acesso=com_acesso,
            )
        )
    else:
        linha.com_acesso = com_acesso
    session.flush()


def novo_morador(
    session: Session, predio: Predio, unidade: Unidade, *, nome: str = "Pessoa de Teste"
) -> tuple[Usuario, MoradorUnidade, dict[str, str]]:
    """Mais um morador ativo da `unidade`, já com a aba Reservas Com Acesso, e o cabeçalho dele."""
    usuario = criar_usuario(session)
    usuario.nome = nome
    vincular(session, usuario, predio.condominio, perfil="morador")
    morador_unidade = MoradorUnidade(
        condominio_id=predio.condominio.id,
        unidade_id=unidade.id,
        usuario_id=usuario.id,
        origem="cadastro",
    )
    session.add(morador_unidade)
    session.flush()
    definir_aba(session, morador_unidade)
    token = token_de(usuario, predio.condominio.id, perfil="morador")
    return usuario, morador_unidade, cabecalho(token)


def criar_responsavel(
    session: Session, predio: Predio, nome: str = "Carlos (síndico)", *, ativo: bool = True
) -> ResponsavelAdministracao:
    responsavel = ResponsavelAdministracao(
        condominio_id=predio.condominio.id, nome=nome, ativo=ativo
    )
    session.add(responsavel)
    session.flush()
    return responsavel


def criar_bloqueio(
    session: Session,
    predio: Predio,
    area: AreaComum,
    de: date,
    ate: date,
    *,
    removido: bool = False,
) -> BloqueioArea:
    bloqueio = BloqueioArea(
        condominio_id=predio.condominio.id,
        area_id=area.id,
        data_inicio=de,
        data_fim=ate,
        motivo="Manutenção",
        responsavel_id=criar_responsavel(session, predio, f"Resp {uuid.uuid4().hex[:6]}").id,
        removido_em=datetime.now(UTC) if removido else None,
        removido_por_usuario_id=predio.administracao.id if removido else None,
    )
    session.add(bloqueio)
    session.flush()
    return bloqueio


def pedido(area: AreaComum, unidade: Unidade, dia: date = DIA, hora: str = "10:00") -> dict:
    return {
        "unidade_id": str(unidade.id),
        "area_id": str(area.id),
        "data": dia.isoformat(),
        "hora_inicio": hora,
    }
