import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.cabecalhos import CabecalhosDeSeguranca
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging_seguro import instalar_filtros_de_log
from app.db.session import get_engine
from app.modules.auditoria.contexto import auditar_requisicao


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger(__name__).info("API iniciada")
    yield
    get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    # Depois do basicConfig, para alcançar o handler da raiz e os do uvicorn.
    instalar_filtros_de_log()
    producao = settings.app_env == "production"
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        # Em produção o esquema da API não fica público.
        docs_url=None if producao else "/docs",
        redoc_url=None if producao else "/redoc",
        openapi_url=None if producao else "/openapi.json",
    )
    register_error_handlers(app)
    app.middleware("http")(auditar_requisicao)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    # Adicionado por último = o mais externo: cobre também as respostas de erro e do CORS.
    app.add_middleware(CabecalhosDeSeguranca, producao=producao)
    app.include_router(router)
    return app


app = create_app()
