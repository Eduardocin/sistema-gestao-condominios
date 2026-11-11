import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    """Erro HTTP com um `code` estável.

    O front decide o que fazer pelo `code` (ex.: `not_authenticated`) e só exibe a
    `message`, que pode mudar de texto sem quebrar ninguém.

    `reason` é opcional e serve para o 409: diz *qual* conflito aconteceu (ex.: `ultimo_usuarios`)
    sem o front precisar ler a mensagem (convenções da API, seção 4).
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.reason = reason


class RecursoNaoEncontrado(Exception):
    """O recurso não existe OU é de outro condomínio (R4): para o cliente, é a mesma coisa.

    Sem argumentos de propósito: não há onde colocar um ID ou um nome que vaze na resposta.
    Os repositories levantam esta exceção; quem a traduz para HTTP é o handler abaixo.
    """


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RecursoNaoEncontrado)
    async def recurso_nao_encontrado(request: Request, exc: RecursoNaoEncontrado) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Recurso não encontrado."}},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        # Erros lançados pelo FastAPI/Starlette não têm `code` próprio: caem em "http_error".
        erro = {"code": getattr(exc, "code", "http_error"), "message": str(exc.detail)}
        # `reason` só aparece quando existe: quem não o conhece continua funcionando igual.
        if reason := getattr(exc, "reason", None):
            erro["reason"] = reason
        return JSONResponse(
            status_code=exc.status_code, content={"error": erro}, headers=exc.headers
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
