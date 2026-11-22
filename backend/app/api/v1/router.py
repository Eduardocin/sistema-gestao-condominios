from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.modules.auditoria.router import router as auditoria_router
from app.modules.auth.router import router as auth_router
from app.modules.avisos.router import router as avisos_router
from app.modules.condominios.router import cadastro_router, plataforma_router
from app.modules.condominios.router import router as condominios_router
from app.modules.contas.router import router as contas_router
from app.modules.encomendas.router import portaria_router as portaria_encomendas_router
from app.modules.encomendas.router import router as encomendas_router
from app.modules.funcionarios.router import responsaveis_router
from app.modules.funcionarios.router import router as funcionarios_router
from app.modules.ocorrencias.router import router as ocorrencias_router
from app.modules.permissoes_aba.router import router as permissoes_aba_router
from app.modules.reservas.router import router as reservas_router
from app.modules.storage.router import router as storage_router
from app.modules.unidades.router import router as unidades_router
from app.modules.vinculos.router import router as vinculos_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(auditoria_router)
router.include_router(avisos_router)
router.include_router(condominios_router)
router.include_router(plataforma_router)
router.include_router(cadastro_router)
router.include_router(unidades_router)
router.include_router(vinculos_router)
router.include_router(contas_router)
router.include_router(encomendas_router)
router.include_router(portaria_encomendas_router)
router.include_router(funcionarios_router)
router.include_router(responsaveis_router)
router.include_router(ocorrencias_router)
router.include_router(permissoes_aba_router)
router.include_router(reservas_router)
router.include_router(storage_router)


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Verifica a API sem depender da disponibilidade do banco de dados."""
    return HealthResponse(status="ok")
