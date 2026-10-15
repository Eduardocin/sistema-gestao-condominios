# Contrato HTTP inicial

`GET /api/v1/health` é público e retorna HTTP 200:

```json
{"status": "ok"}
```

Verifica somente se a API responde. Não consulta PostgreSQL. A conexão e o schema são verificados separadamente pelas migrações e testes de integração.

Erros usam o formato:

```json
{"error": {"code": "http_error", "message": "Not Found"}}
```

| Situação | HTTP | Código |
| --- | --- | --- |
| Erro HTTP, incluindo rota ausente | Status da exceção | `http_error` |
| Entrada inválida | 422 | `validation_error` |
| Falha inesperada | 500 | `internal_error` |

Falhas inesperadas usam mensagem genérica. Rejeições de preflight CORS são respostas do middleware, fora desse envelope. Documentação interativa em `/docs` e schema em `/openapi.json`.
