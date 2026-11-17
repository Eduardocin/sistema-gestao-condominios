import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.contexto import ContextoPlataforma
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_platform_permission
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.condominios import schemas, service
from app.modules.condominios.dependencies import condominio_do_cadastro
from app.modules.condominios.models import Condominio
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


plataforma_router = APIRouter(prefix="/plataforma/condominios", tags=["aprovacao-condominios"])
cadastro_router = APIRouter(prefix="/condominio", tags=["condominios"])
PlataformaVer = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("cadastro_condominio:ver"))
]
PlataformaEditar = Annotated[
    ContextoPlataforma, Depends(require_platform_permission("cadastro_condominio:editar"))
]


@cadastro_router.get("", response_model=schemas.CondominioSaida)
def consultar_cadastro(
    condominio: Annotated[Condominio, Depends(condominio_do_cadastro)],
    session: SessionDep,
) -> schemas.CondominioSaida:
    return service.dados_condominio(session, condominio)


@plataforma_router.get("", response_model=schemas.PaginaFila)
def fila(
    contexto: PlataformaVer, session: SessionDep, filtros: Annotated[schemas.FiltrosFila, Query()]
) -> schemas.PaginaFila:
    return service.listar_fila(session, filtros)


@plataforma_router.get("/{id}", response_model=schemas.DetalhePlataforma)
def detalhe(
    id: uuid.UUID, contexto: PlataformaVer, session: SessionDep
) -> schemas.DetalhePlataforma:
    return service.detalhe_plataforma(session, id)


@plataforma_router.post("/{id}/aprovacao", response_model=schemas.CondominioSaida)
def aprovar(
    id: uuid.UUID,
    dados: schemas.AcaoAprovacao,
    contexto: PlataformaEditar,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.CondominioSaida:
    return service.decidir(
        session, contexto, id, "aprovado", ip=ip_do_cliente(request), relogio=relogio
    )


@plataforma_router.post("/{id}/rejeicao", response_model=schemas.CondominioSaida)
def rejeitar(
    id: uuid.UUID,
    dados: schemas.RejeicaoEntrada,
    contexto: PlataformaEditar,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.CondominioSaida:
    return service.decidir(
        session,
        contexto,
        id,
        "rejeitado",
        motivo=dados.motivo,
        ip=ip_do_cliente(request),
        relogio=relogio,
    )
