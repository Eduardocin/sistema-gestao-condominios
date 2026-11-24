"""Dados dos testes de veículos, criados direto pelos models."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.unidades.models import Unidade
from app.modules.visitantes.models import Veiculo
from tests.autorizacao.cenario import Predio


def criar_veiculo(
    session: Session,
    predio: Predio,
    *,
    unidade: Unidade | None = None,
    placa: str = "ABC1D23",
    marca: str = "Fiat",
    modelo: str = "Argo",
    cor: str = "Prata",
    removido: bool = False,
) -> Veiculo:
    veiculo = Veiculo(
        condominio_id=predio.condominio.id,
        unidade_id=(unidade or predio.unidade_101).id,
        placa=placa,
        marca=marca,
        modelo=modelo,
        cor=cor,
        ativo=not removido,
        removido_em=datetime.now(UTC) if removido else None,
    )
    session.add(veiculo)
    session.flush()
    return veiculo


def corpo(predio: Predio, unidade: Unidade | None = None, **campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "unidade_id": str((unidade or predio.unidade_101).id),
        "placa": "ABC1D23",
        "marca": "Fiat",
        "modelo": "Argo",
        "cor": "Prata",
    }
    base.update(campos)
    return base
