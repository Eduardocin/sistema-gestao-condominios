import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Não devolver valores de entrada: futuramente podem conter senhas ou dados pessoais.
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Dados inválidos."}},
        )

    @app.middleware("http")
    async def unexpected_error(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            logger.exception("Falha não tratada em %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {"code": "internal_error", "message": "Erro interno do servidor."}
                },
            )
