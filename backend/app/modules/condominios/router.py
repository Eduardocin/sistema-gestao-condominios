from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.condominios import service
from app.modules.condominios.schemas import (
    CadastroCondominio,
    CadastroCondominioSaida,
    CondominioResumo,
)
from app.modules.usuarios.models import Usuario


class RotaCadastro(APIRoute):
    """Detalhes do 422 do assistente sem mudar o envelope das outras APIs."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        tratar = super().get_route_handler()

        async def validar(request: Request) -> Response:
            try:
                return await tratar(request)
            except RequestValidationError as erro:
                detalhes = []
                for item in erro.errors():
                    localizacao = item["loc"][1:]
                    if item["type"] == "extra_forbidden":
                        localizacao = localizacao[:-1]  # não ecoa nome arbitrário de campo extra
                    campo = ""
                    for parte in localizacao:
                        campo += f"[{parte}]" if isinstance(parte, int) else f".{parte}"
                    mensagem = "Valor inválido para este campo."
                    if item["type"] == "value_error":
                        mensagem = str(item.get("ctx", {}).get("error", mensagem))
                    detalhes.append({"campo": campo.lstrip(".") or "corpo", "mensagem": mensagem})
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "validation_error",
                            "message": "Dados inválidos.",
                            "details": detalhes,
                        }
                    },
                )

        return validar


router = APIRouter(prefix="/condominios", tags=["condominios"], route_class=RotaCadastro)
SessionDep = Annotated[Session, Depends(get_session)]


def get_administracao(
    autenticado: Annotated[UsuarioAutenticado, Depends(get_usuario_autenticado)],
) -> Usuario:
    service.exigir_administracao(autenticado.usuario)
    return autenticado.usuario


AdministracaoDep = Annotated[Usuario, Depends(get_administracao)]


@router.post("", status_code=201, response_model=CadastroCondominioSaida)
def cadastrar(
    dados: CadastroCondominio,
    usuario: AdministracaoDep,
    session: SessionDep,
    request: Request,
    response: Response,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> CadastroCondominioSaida:
    saida = service.cadastrar(session, usuario, dados, ip=ip_do_cliente(request), relogio=relogio)
    response.headers["Location"] = "/api/v1/condominios/meus"
    return saida


@router.get("/meus", response_model=list[CondominioResumo])
def listar_meus(usuario: AdministracaoDep, session: SessionDep) -> list[CondominioResumo]:
    return service.listar_meus(session, usuario)
