import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.contexto import ContextoCondominio, ContextoPlataforma
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import require_platform_permission
from app.modules.auth.dependencies import UsuarioAutenticado, get_usuario_autenticado
from app.modules.condominios import schemas, service
from app.modules.condominios.dependencies import condominio_do_cadastro, contexto_do_cadastro
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


estrutura_router = APIRouter(prefix="/estrutura", tags=["correcao-cadastro"])
ContextoCadastroDep = Annotated[ContextoCondominio, Depends(contexto_do_cadastro)]


@cadastro_router.get("/estrutura", response_model=schemas.EstruturaSaida)
def consultar_estrutura(
    contexto: ContextoCadastroDep, session: SessionDep
) -> schemas.EstruturaSaida:
    return service.estrutura_do_cadastro(session, contexto)


@cadastro_router.put("", response_model=schemas.CondominioSaida)
def corrigir_dados(
    dados: schemas.EdicaoCondominio,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
) -> schemas.CondominioSaida:
    return service.CorrecaoCadastroService(session, contexto).editar_dados(
        dados, ip=ip_do_cliente(request)
    )


@cadastro_router.post("/reenvio", response_model=schemas.ReenvioSaida)
def reenviar(
    dados: schemas.AcaoCorrecao,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.ReenvioSaida:
    return service.CorrecaoCadastroService(session, contexto).reenviar(
        dados, ip=ip_do_cliente(request), relogio=relogio
    )


@estrutura_router.put("/blocos/{id}", response_model=schemas.BlocoCorrecaoSaida)
def corrigir_bloco(
    id: uuid.UUID,
    dados: schemas.EdicaoBloco,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
) -> schemas.BlocoCorrecaoSaida:
    return service.CorrecaoCadastroService(session, contexto).editar_bloco(
        id, dados, ip=ip_do_cliente(request)
    )


@estrutura_router.put("/andares/{id}", response_model=schemas.AndarCorrecaoSaida)
def corrigir_andar(
    id: uuid.UUID,
    dados: schemas.EdicaoAndar,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
) -> schemas.AndarCorrecaoSaida:
    return service.CorrecaoCadastroService(session, contexto).editar_andar(
        id, dados, ip=ip_do_cliente(request)
    )


@estrutura_router.put("/unidades/{id}", response_model=schemas.UnidadeAnalise)
def corrigir_unidade(
    id: uuid.UUID,
    dados: schemas.EdicaoUnidade,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
) -> schemas.UnidadeAnalise:
    return service.CorrecaoCadastroService(session, contexto).editar_unidade(
        id, dados, ip=ip_do_cliente(request)
    )


@estrutura_router.post("/blocos", status_code=201, response_model=schemas.BlocoCorrecaoSaida)
def adicionar_bloco(
    dados: schemas.EdicaoBloco,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    response: Response,
) -> schemas.BlocoCorrecaoSaida:
    saida = service.CorrecaoCadastroService(session, contexto).cadastrar_bloco(
        dados, ip=ip_do_cliente(request)
    )
    response.headers["Location"] = "/api/v1/condominio/estrutura"
    return saida


@estrutura_router.post(
    "/blocos/{id}/andares", status_code=201, response_model=schemas.AndarCorrecaoSaida
)
def adicionar_andar(
    id: uuid.UUID,
    dados: schemas.EdicaoAndar,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    response: Response,
) -> schemas.AndarCorrecaoSaida:
    saida = service.CorrecaoCadastroService(session, contexto).cadastrar_andar(
        id, dados, ip=ip_do_cliente(request)
    )
    response.headers["Location"] = "/api/v1/condominio/estrutura"
    return saida


@estrutura_router.post(
    "/andares/{id}/unidades", status_code=201, response_model=schemas.UnidadeAnalise
)
def adicionar_unidade(
    id: uuid.UUID,
    dados: schemas.EdicaoUnidade,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    response: Response,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.UnidadeAnalise:
    saida = service.CorrecaoCadastroService(session, contexto).cadastrar_unidade(
        id, dados, ip=ip_do_cliente(request), relogio=relogio
    )
    response.headers["Location"] = "/api/v1/condominio/estrutura"
    return saida


@estrutura_router.post("/{tipo}/{id}/desativacao", response_model=schemas.ElementoEstruturaSaida)
def desativar_estrutura(
    tipo: schemas.TipoEstrutura,
    id: uuid.UUID,
    dados: schemas.AcaoCorrecao,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.ElementoEstruturaSaida:
    return service.CorrecaoCadastroService(session, contexto).alterar_status_estrutura(
        tipo, id, False, dados, ip=ip_do_cliente(request), relogio=relogio
    )


@estrutura_router.post("/{tipo}/{id}/reativacao", response_model=schemas.ElementoEstruturaSaida)
def reativar_estrutura(
    tipo: schemas.TipoEstrutura,
    id: uuid.UUID,
    dados: schemas.AcaoCorrecao,
    contexto: ContextoCadastroDep,
    session: SessionDep,
    request: Request,
    relogio: Annotated[Relogio, Depends(get_relogio)],
) -> schemas.ElementoEstruturaSaida:
    return service.CorrecaoCadastroService(session, contexto).alterar_status_estrutura(
        tipo, id, True, dados, ip=ip_do_cliente(request), relogio=relogio
    )
