"""Importe aqui cada novo modelo para que o Alembic enxergue seu metadata."""

from app.modules.auditoria.models import EventoAuditoria
from app.modules.condominios.models import (
    AreaComum,
    BlocoCondominio,
    ChaveAcesso,
    Condominio,
    RascunhoCondominio,
    VinculoCondominio,
)
from app.modules.unidades.models import SolicitacaoVinculoUnidade, Unidade
from app.modules.usuarios.models import Usuario

__all__ = [
    "AreaComum",
    "BlocoCondominio",
    "ChaveAcesso",
    "Condominio",
    "EventoAuditoria",
    "RascunhoCondominio",
    "SolicitacaoVinculoUnidade",
    "Unidade",
    "Usuario",
    "VinculoCondominio",
]
