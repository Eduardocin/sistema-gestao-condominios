"""Dados dos testes de visitantes, criados direto pelos models."""

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.funcionarios.models import Funcionario
from app.modules.unidades.models import Unidade
from app.modules.visitantes.models import RegistroVisita, Visitante
from tests.autorizacao.cenario import Predio


def criar_visitante(
    session: Session,
    predio: Predio,
    *,
    unidade: Unidade | None = None,
    nome: str = "Carlos Souza",
    cpf: str | None = None,
    entrada: date = date(2026, 11, 14),
    saida: date = date(2026, 11, 16),
    cancelado_em: datetime | None = None,
) -> Visitante:
    visitante = Visitante(
        condominio_id=predio.condominio.id,
        unidade_id=(unidade or predio.unidade_101).id,
        nome=nome,
        cpf=cpf,
        entrada_prevista=entrada,
        saida_prevista=saida,
        cadastrado_por_usuario_id=predio.morador.id,
        cancelado_em=cancelado_em,
    )
    session.add(visitante)
    session.flush()
    return visitante


def registrar_visita(
    session: Session, predio: Predio, visitante: Visitante, *, saida_em: datetime | None = None
) -> RegistroVisita:
    """Uma entrada na portaria; com `saida_em`, a visita já terminou."""
    funcionario = Funcionario(
        condominio_id=predio.condominio.id, nome="Porteiro", funcao="porteiro"
    )
    session.add(funcionario)
    session.flush()
    visita = RegistroVisita(
        condominio_id=predio.condominio.id,
        visitante_id=visitante.id,
        entrada_por_funcionario_id=funcionario.id,
        saida_em=saida_em,
        saida_por_funcionario_id=funcionario.id if saida_em else None,
    )
    session.add(visita)
    session.flush()
    return visita


def corpo(predio: Predio, unidade: Unidade | None = None, **campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "unidade_id": str((unidade or predio.unidade_101).id),
        "nome": "Carlos Souza",
        "cpf": "12345678909",
        "idade": 35,
        "observacoes": "Carro prata, placa ABC1D23",
        "entrada_prevista": "2026-11-14",
        "saida_prevista": "2026-11-15",
    }
    base.update(campos)
    return base
