import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.db.session import get_engine
from app.modules.auditoria.contexto import auditar_requisicao
from app.modules.notificacoes.worker import laco


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger(__name__).info("API iniciada")
    settings = get_settings()
    worker = asyncio.create_task(laco(settings)) if settings.email_worker_ativo else None
    yield
    if worker is not None:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
    get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.middleware("http")(auditar_requisicao)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(router)
    return app


app = create_app()
