# Autenticação — contrato HTTP (TASK-80)

Rotas implementadas em `backend/app/modules/auth`. Convenção de erros: `{"error": {"code", "message"}}` ([health.md](health.md)). Regras de token e multi-tenant: [matriz de permissões](../permissoes-e-multitenant.md), seções 4 e 5.

## Tokens

| Token | Validade (padrão) | Para que serve |
| --- | --- | --- |
| `access_token` | 15 minutos | Vai em `Authorization: Bearer <token>` em todas as rotas |
| `refresh_token` | 7 dias | Só para `POST /auth/refresh`; não vale como access token |

Claims: `sub` (usuário), `cid` (condomínio, ausente antes de escolher um), `sv` (versão da sessão), `typ` (`access` ou `refresh`), `perfil` (**só para a interface**), `iat` e `exp`. Assinatura HS256 com `JWT_SECRET_KEY`. Perfil e permissões são sempre relidos do banco; aumentar `usuarios.sessao_versao` derruba todas as sessões da conta.

## `POST /api/v1/auth/login` (público)

```json
{"identificador": "ana@exemplo.com", "senha": "Senha#Forte123"}
```

`identificador` é o e-mail (maiúsculas e espaços são normalizados). Telefone entra quando a coluna existir no banco. Resposta 200:

```json
{
  "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer", "expires_in": 900,
  "usuario": {"id": "UUID", "nome": "Ana Martins", "email": "ana@exemplo.com"},
  "condominio": {"id": "UUID", "nome": "Residencial Aurora", "perfil": "morador", "status": "ativo"},
  "condominios": [{"id": "UUID", "nome": "Residencial Aurora", "perfil": "morador", "status": "ativo"}],
  "requer_selecao": false,
  "administrador_plataforma": false
}
```

| Situação | `condominio` | `requer_selecao` | `cid` no token |
| --- | --- | --- | --- |
| Um vínculo ativo e liberado | O condomínio | `false` | Presente |
| Vários vínculos ativos | `null` | `true` | Ausente. Chamar `selecionar-condominio` |
| Nenhum vínculo | `null` | `false` | Ausente |
| ADM da plataforma | `null` | `false` | Ausente |
| Um vínculo, mas condomínio fora do ar e perfil diferente de Administração (R7) | `null` | `false` | Ausente. O `status` aparece em `condominios` |

| Erro | HTTP | `code` |
| --- | --- | --- |
| E-mail inexistente, senha errada, conta inativa ou sem senha (mesma resposta e mesma mensagem: "E-mail ou senha incorretos.") | 401 | `not_authenticated` |
| Corpo inválido | 422 | `validation_error` |
| 5 falhas seguidas no mesmo e-mail (`LOGIN_MAX_FAILURES`) | 429 | `too_many_attempts`, com `Retry-After` em segundos |
| Conta com perfil local de Funcionário/Administração sem `nome_responsavel` | 422 | `validation_error` |

Para perfis de Funcionário e Administração, que usam credenciais compartilhadas, o cliente deve
enviar `nome_responsavel` no corpo do login. Exemplo:

```json
{
  "identificador": "portaria@exemplo.com",
  "senha": "Senha#Forte123",
  "nome_responsavel": "João da Portaria"
}
```

O nome é autodeclarado (não há PIN individual no MVP) e fica registrado no evento de auditoria.
As próximas ações críticas desses perfis também devem informar novamente o responsável na chamada
de `audit.log(...)`.

## `POST /api/v1/auth/selecionar-condominio` (Bearer)

`{"condominio_id": "UUID"}`. Devolve o mesmo formato do login, com `cid` no token. Sem vínculo ativo: 404 `not_found` (não revela que o condomínio existe, R4). Condomínio fora do ar e perfil diferente de Administração: 403 `forbidden` (R7).

## `POST /api/v1/auth/refresh` (público)

`{"refresh_token": "..."}` → `{"access_token", "token_type", "expires_in"}`. Confere de novo no banco usuário ativo, `sv`, vínculo e perfil. Qualquer falha: 401 `not_authenticated`. O refresh token **não é rotacionado**: continua valendo até expirar ou até a `sv` mudar.

## `GET /api/v1/auth/me` (Bearer)

```json
{
  "usuario": {"id": "UUID", "nome": "Ana Martins", "email": "ana@exemplo.com"},
  "condominio": {"id": "UUID", "nome": "Residencial Aurora", "perfil": "morador", "status": "ativo"},
  "unidades": [{"id": "UUID", "identificacao": "Bloco A / 101"}],
  "administrador_plataforma": false
}
```

`unidades` só para o Morador. Permissões por aba entram na TASK-21. Token sem Bearer ou inválido: 401 com `WWW-Authenticate: Bearer`. Vínculo retirado depois do login: 403 `forbidden`.

## Limitações conhecidas

- O contador de tentativas fica na memória do processo (vale para um único servidor).
- O status do condomínio é provisório: `ativo` ou `desativado`, a partir de `condominios.ativo`.
- Não há rotação nem revogação individual de refresh token; para derrubar sessões, aumentar `sessao_versao`.
- Login e falha de credenciais geram eventos de auditoria; falhas sem usuário conhecido registram
  o identificador informado como ator.
