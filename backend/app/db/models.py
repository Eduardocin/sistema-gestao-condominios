"""Importe aqui cada novo modelo para que o Alembic enxergue seu metadata."""

from app.modules.condominios.models import Condominio, VinculoCondominio
from app.modules.unidades.models import Unidade
from app.modules.usuarios.models import Usuario

__all__ = ["Condominio", "Unidade", "Usuario", "VinculoCondominio"]
