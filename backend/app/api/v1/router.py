from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.modules.auth.router import router as auth_router
from app.modules.permissoes_aba.router import router as permissoes_aba_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(permissoes_aba_router)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Verifica a API sem depender da disponibilidade do banco de dados."""
    return HealthResponse(status="ok")
