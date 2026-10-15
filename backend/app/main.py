import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.db.session import get_engine


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
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
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
