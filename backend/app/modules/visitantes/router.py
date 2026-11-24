import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.permissoes import Perfil
from app.core.tempo import Relogio, get_relogio
from app.db.session import get_session
from app.modules.auditoria.contexto import ip_do_cliente
from app.modules.auth.autorizacao import (
    MENSAGEM_SEM_PERMISSAO,
    registrar_negacao,
    require_permission,
)
from app.modules.auth.dependencies import ContextoDep
from app.modules.visitantes import schemas as s
from app.modules.visitantes.service import VisitantesService

router = APIRouter(tags=["visitantes"])
SessionDep = Annotated[Session, Depends(get_session)]
RelogioDep = Annotated[Relogio, Depends(get_relogio)]
Page = Annotated[int, Query(ge=1)]
Size = Annotated[int, Query(ge=1, le=100)]
Busca = Annotated[str | None, Query(max_length=120)]


def somente_morador(
    session: SessionDep, contexto: ContextoDep, relogio: RelogioDep
) -> VisitantesService:
    if contexto.perfil != Perfil.MORADOR:
        registrar_negacao(
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
            perfil=contexto.perfil,
            permissao="visitantes:morador",
        )
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    return VisitantesService(session, contexto, relogio)


def somente_portaria(
    session: SessionDep, contexto: ContextoDep, relogio: RelogioDep
) -> VisitantesService:
    if contexto.perfil != Perfil.FUNCIONARIO:
        registrar_negacao(
            usuario_id=contexto.usuario_id,
            condominio_id=contexto.condominio_id,
            perfil=contexto.perfil,
            permissao="visitantes:portaria",
        )
        raise ApiError(403, "forbidden", MENSAGEM_SEM_PERMISSAO)
    return VisitantesService(session, contexto, relogio)


Morador = Annotated[VisitantesService, Depends(somente_morador)]
Portaria = Annotated[VisitantesService, Depends(somente_portaria)]
Ver = Depends(require_permission("visitantes:ver"))
Criar = Depends(require_permission("visitantes:criar"))
Editar = Depends(require_permission("visitantes:editar"))
Cancelar = Depends(require_permission("visitantes:desativar"))


@router.get("/visitantes", dependencies=[Ver])
def listar_visitantes(
    service: Morador,
    unidade_id: uuid.UUID,
    busca: Busca = None,
    situacao: s.Situacao | None = None,
    page: Page = 1,
    page_size: Size = 20,
) -> s.Pagina[s.VisitanteMorador]:
    return service.pagina_morador(unidade_id, busca, situacao, page, page_size)


@router.post("/visitantes", status_code=201, dependencies=[Criar])
def cadastrar(
    dados: s.CadastroVisitante, service: Morador, request: Request, response: Response
) -> s.VisitanteMorador:
    item = service.cadastrar(dados, ip_do_cliente(request))
    response.headers["Location"] = f"/api/v1/visitantes/{item.id}"
    return item


@router.get("/visitantes/{visitante_id}", dependencies=[Ver])
def detalhe_visitante(visitante_id: uuid.UUID, service: Morador) -> s.VisitanteMorador:
    return service.detalhe_morador(visitante_id)


@router.put("/visitantes/{visitante_id}", dependencies=[Editar])
def editar(
    visitante_id: uuid.UUID, dados: s.EdicaoVisitante, service: Morador, request: Request
) -> s.VisitanteMorador:
    return service.editar(visitante_id, dados, ip_do_cliente(request))


@router.post("/visitantes/{visitante_id}/cancelamento", dependencies=[Cancelar])
def cancelar(
    visitante_id: uuid.UUID, service: Morador, request: Request, dados: s.Entrada | None = None
) -> s.VisitanteMorador:
    return service.cancelar(visitante_id, ip_do_cliente(request))


@router.get("/portaria/visitantes", dependencies=[Ver])
def buscar_por_nome(
    service: Portaria,
    unidade_id: uuid.UUID | None = None,
    busca: Busca = None,
    page: Page = 1,
    page_size: Size = 20,
) -> s.Pagina[s.VisitantePortaria]:
    return service.pagina_portaria(unidade_id, busca, None, page, page_size)


@router.post("/portaria/visitantes/busca-documento", dependencies=[Ver])
def buscar_por_documento(
    dados: s.BuscaDocumento,
    service: Portaria,
    response: Response,
    page: Page = 1,
    page_size: Size = 20,
) -> s.Pagina[s.VisitantePortaria]:
    response.headers["Cache-Control"] = "no-store"
    return service.pagina_portaria(dados.unidade_id, None, dados.cpf, page, page_size)


@router.get("/portaria/autorizacoes", dependencies=[Ver])
def autorizacoes(
    service: Portaria, visitante_id: uuid.UUID, unidade_id: uuid.UUID
) -> list[s.Autorizacao]:
    return service.autorizacoes(visitante_id, unidade_id)


@router.get("/portaria/visitantes/moradores", dependencies=[Ver])
def moradores_para_contato(service: Portaria, unidade_id: uuid.UUID) -> list[s.Referencia]:
    return service.moradores_para_contato(unidade_id)


@router.post("/portaria/visitantes/avulsos", status_code=201, dependencies=[Criar])
def registrar_avulso(
    dados: s.CadastroAvulso, service: Portaria, request: Request, response: Response
) -> s.VisitaSaida:
    item = service.registrar_avulso(dados, ip_do_cliente(request))
    response.headers["Location"] = f"/api/v1/visitas/{item.id}"
    return item


@router.get("/visitas", dependencies=[Ver])
def listar_visitas(
    service: Portaria,
    busca: Busca = None,
    status: s.StatusVisita | None = None,
    page: Page = 1,
    page_size: Size = 20,
) -> s.Pagina[s.VisitaSaida]:
    return service.pagina_visitas(busca, status, page, page_size)


@router.get("/visitas/{visita_id}", dependencies=[Ver])
def detalhe_visita(visita_id: uuid.UUID, service: Portaria) -> s.VisitaSaida:
    return service.detalhe_visita(visita_id)


@router.post("/visitas", status_code=201, dependencies=[Editar])
def entrar(
    dados: s.EntradaVisita, service: Portaria, request: Request, response: Response
) -> s.VisitaSaida:
    item = service.entrar(dados, ip_do_cliente(request))
    response.headers["Location"] = f"/api/v1/visitas/{item.id}"
    return item


@router.post("/visitas/{visita_id}/saida", dependencies=[Editar])
def sair(
    visita_id: uuid.UUID, dados: s.FuncionarioEntrada, service: Portaria, request: Request
) -> s.VisitaSaida:
    return service.sair(visita_id, dados.funcionario_id, ip_do_cliente(request))


@router.get("/portaria/contatos", dependencies=[Ver])
def listar_contatos(
    service: Portaria, page: Page = 1, page_size: Size = 20
) -> s.Pagina[s.ContatoSaida]:
    return service.pagina_contatos(page, page_size)


@router.post("/portaria/contatos", status_code=201, dependencies=[Editar])
def registrar_contato(
    dados: s.ContatoSemEntrada, service: Portaria, request: Request
) -> s.ContatoSaida:
    return service.registrar_contato(dados, ip_do_cliente(request))
