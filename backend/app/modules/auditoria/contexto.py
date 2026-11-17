"""Metadados internos da requisição compartilhados com as dependências síncronas.

O ContextVar isola requisições concorrentes; o objeto mutável permite que dependências
executadas no threadpool publiquem somente a identidade e o escopo já validados.
"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.core.contexto import ContextoCondominio
from app.modules.auditoria import service


@dataclass
class EstadoRequisicao:
    ip: str | None
    usuario_id: uuid.UUID | None = None
    condominio_id: uuid.UUID | None = None
    perfil: str | None = None
    permissao: str | None = None


_estado: ContextVar[EstadoRequisicao | None] = ContextVar("auditoria_requisicao", default=None)


def ip_do_cliente(request: Request) -> str | None:
    # Não confiar em X-Forwarded-For/Forwarded arbitrários. Proxy confiável é configuração ASGI.
    return service.ip_valido(request.client.host if request.client else None)


def identificar_conta(usuario_id: uuid.UUID, *, plataforma: bool) -> None:
    if (estado := _estado.get()) is not None:
        estado.usuario_id = usuario_id
        estado.perfil = "plataforma" if plataforma else None


def identificar_contexto(contexto: ContextoCondominio) -> None:
    if (estado := _estado.get()) is not None:
        estado.condominio_id = contexto.condominio_id
        estado.perfil = contexto.perfil


def identificar_negacao(permissao: str) -> None:
    if (estado := _estado.get()) is not None:
        estado.permissao = permissao


async def auditar_requisicao(request: Request, call_next: RequestResponseEndpoint) -> Response:
    estado = EstadoRequisicao(ip_do_cliente(request))
    token = _estado.set(estado)
    try:
        resposta = await call_next(request)
        if estado.usuario_id is not None:
            acao = None
            detalhe: dict[str, Any] = {"status_http": resposta.status_code}
            rota = request.scope.get("route")
            if rota is not None:
                detalhe["rota"] = rota.path
                detalhe["metodo"] = request.method
            if resposta.status_code == 403:
                acao = "seguranca.acesso_negado"
                if estado.permissao:
                    detalhe["permissao"] = estado.permissao
            elif (
                resposta.status_code == 404
                and rota is not None
                and estado.condominio_id is not None
            ):
                # Tentativa recusada pelo escopo. Não consulta outro tenant para comprovar
                # existência: o evento, assim como o 404, não afirma que o ID exista.
                acao = "seguranca.acesso_cross_tenant"
                detalhe["motivo"] = "recurso_fora_do_escopo_ou_inexistente"
            if acao:
                await run_in_threadpool(
                    service.registrar_evento_seguranca,
                    acao=acao,
                    usuario_id=estado.usuario_id,
                    condominio_id=estado.condominio_id,
                    perfil=estado.perfil,
                    ip=estado.ip,
                    detalhe=detalhe,
                )
        return resposta
    finally:
        _estado.reset(token)
