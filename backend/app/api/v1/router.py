from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.modules.auth.router import router as auth_router
from app.modules.condominios.aprovacao_router import router as condominios_aprovacao_router
from app.modules.condominios.wizard_router import router as condominios_wizard_router
from app.modules.unidades.router import router as unidades_vinculos_router
from app.modules.usuarios.router import router as usuarios_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(condominios_aprovacao_router)
router.include_router(condominios_wizard_router)
router.include_router(unidades_vinculos_router)
router.include_router(usuarios_router)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Verifica a API sem depender da disponibilidade do banco de dados."""
    return HealthResponse(status="ok")
