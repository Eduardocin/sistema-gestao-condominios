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
| `autorizacao.py` | `require_permission`, `require_platform_permission` e verificação de acesso à unidade |

Rotas **de condomínio** usam `require_permission("recurso:acao")` para conferir a permissão do perfil. Essa dependência usa `ContextoDep` (`get_current_context`), que valida token, vínculo e condomínio ativos e entrega o contexto usado pelo repositório base. Para operações sobre uma unidade, o service também chama `garantir_acesso_a_unidade`. Guia: [Como criar um endpoint respeitando o isolamento](../../../../docs/architecture.md#como-criar-um-endpoint-novo-respeitando-o-isolamento).

`get_usuario_autenticado` é a base das rotas autenticadas **sem** condomínio selecionado (escolha de condomínio e `/auth/me`). Login e refresh têm contratos próprios. A autorização por perfil e unidade está disponível na TASK-19; permissões por aba continuam na TASK-21. A verificação de unidades ainda usa o vínculo legado até a integração com `moradores_unidade`.
