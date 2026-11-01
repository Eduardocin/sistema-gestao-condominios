# auth

Login e emissão de JWT (TASK-80 / US-101). Contrato HTTP em `docs/api-contracts/auth.md`.

| Arquivo | Responsabilidade |
| --- | --- |
| `router.py` | Rotas `/api/v1/auth/*`. Só traduz HTTP para chamadas ao service |
| `schemas.py` | Formatos de entrada e saída |
| `service.py` | Regras: credenciais, bloqueio, escolha do condomínio (R7), renovação do token |
| `repository.py` | Consultas ao banco |
| `security.py` | argon2id e JWT (sem banco nem HTTP, fácil de testar) |
| `rate_limit.py` | Limite de tentativas de login (em memória) |
| `dependencies.py` | `get_usuario_autenticado` (identidade) e `get_current_context` (identidade + condomínio) |

Para proteger uma rota **de condomínio**, dependa de `ContextoDep` (`get_current_context`): ela valida o token, confere vínculo e condomínio ativos no banco e entrega o contexto que os repositories usam para filtrar. Guia completo: [Como criar um endpoint novo respeitando o isolamento](../../../../docs/architecture.md#como-criar-um-endpoint-novo-respeitando-o-isolamento).

`get_usuario_autenticado` continua sendo a base das rotas **sem** condomínio no token (login, escolha de condomínio, `/auth/me`). Ela só garante **quem** é o usuário. Perfil, unidade e aba são da autorização central (TASK-19 e TASK-21).
