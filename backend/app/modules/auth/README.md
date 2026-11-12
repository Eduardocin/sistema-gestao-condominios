# auth

Login e emissão de JWT (TASK-80 / US-101). Contrato HTTP em `docs/api-contracts/auth.md`.

| Arquivo | Responsabilidade |
| --- | --- |
| `router.py` | Rotas `/api/v1/auth/*`. Só traduz HTTP para chamadas ao service |
| `schemas.py` | Formatos de entrada e saída |
| `presentation.py` | Montagem do `LoginResponse`, compartilhada pelo login e cadastro de contas |
| `service.py` | Regras: credenciais, bloqueio, escolha do condomínio (R7), renovação do token |
| `repository.py` | Consultas ao banco |
| `security.py` | argon2id e JWT (sem banco nem HTTP, fácil de testar) |
| `rate_limit.py` | Limite de tentativas de login (em memória) |
| `dependencies.py` | `get_usuario_autenticado` (identidade) e `get_current_context` (identidade + condomínio) |
| `autorizacao.py` | `require_permission` (perfil), `require_platform_permission` (ADM), `require_aba` (unidade + aba do Morador) e `garantir_acesso_a_unidade` |

Rotas **de condomínio** usam `require_permission("recurso:acao")` para conferir a permissão do perfil. Essa dependência usa `ContextoDep` (`get_current_context`), que valida token, vínculo e condomínio ativos e entrega o contexto usado pelo repositório base. Rotas que atuam sobre uma unidade (`/unidades/{unidade_id}/...`) somam `require_aba("<aba>")`: ela confere que a unidade é de quem pede (404) e, para o Morador, que a aba está Com Acesso (403). Quando a unidade vem no corpo ou na query, o service chama `garantir_acesso_a_unidade`. Guia: [Como criar um endpoint respeitando o isolamento](../../../../docs/architecture.md#como-criar-um-endpoint-novo-respeitando-o-isolamento).

`get_usuario_autenticado` é a base das rotas autenticadas **sem** condomínio selecionado (escolha de condomínio e `/auth/me`). Login e refresh têm contratos próprios. A autorização por perfil e unidade (TASK-19) e por aba (TASK-21) está disponível. As unidades do Morador vêm de `moradores_unidade` (ADR 0003); a coluna `vinculos_condominio.unidade_id` não é mais consultada pela autorização. Pendência: `/auth/me` ainda lê a unidade da coluna legada e não devolve as abas do próprio Morador.
