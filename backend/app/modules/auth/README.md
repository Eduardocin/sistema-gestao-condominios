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
| `dependencies.py` | `get_usuario_autenticado`, a base para proteger qualquer rota |

Para proteger uma rota nova, dependa de `get_usuario_autenticado`. Ela só garante **quem** é o usuário; vínculo, perfil e permissões são da autorização central (TASK-19).
