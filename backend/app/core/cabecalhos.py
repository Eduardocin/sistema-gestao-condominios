"""Cabeçalhos de segurança em todas as respostas (TASK-54).

Middleware ASGI puro e o mais externo da aplicação: vale também para 401, 404, 422 e 500,
inclusive os gerados pelos handlers de erro.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Swagger e ReDoc carregam scripts e estilos de CDN; a CSP restritiva quebraria essas páginas.
ROTAS_DE_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


class CabecalhosDeSeguranca:
    def __init__(self, app: ASGIApp, *, producao: bool) -> None:
        self.app = app
        self.producao = producao

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        caminho: str = scope.get("path", "")

        async def enviar(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                cabecalhos = list(mensagem.get("headers", []))
                existentes = {nome.lower() for nome, _ in cabecalhos}

                def definir(nome: str, valor: str) -> None:
                    chave = nome.lower().encode("latin-1")
                    if chave not in existentes:
                        cabecalhos.append((chave, valor.encode("latin-1")))

                definir("X-Content-Type-Options", "nosniff")
                definir("X-Frame-Options", "DENY")
                definir("Referrer-Policy", "no-referrer")
                if caminho.startswith("/api/"):
                    # Respostas da API trazem dado pessoal: nada de cache no navegador ou proxy.
                    definir("Cache-Control", "no-store")
                if not caminho.startswith(ROTAS_DE_DOCUMENTACAO):
                    definir("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                if self.producao:
                    # Só em produção: em dev roda em http://localhost e o HSTS atrapalharia.
                    definir("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                mensagem["headers"] = cabecalhos
            await send(mensagem)

        await self.app(scope, receive, enviar)
