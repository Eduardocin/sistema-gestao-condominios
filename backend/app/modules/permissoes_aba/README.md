# permissoes_aba

Permissões por aba dos moradores de uma unidade (TASK-21 / US-304). Contrato HTTP em [`docs/api-contracts/nucleo.md`](../../../../docs/api-contracts/nucleo.md), seção 8. Regras em [`docs/permissoes-e-multitenant.md`](../../../../docs/permissoes-e-multitenant.md), seção 8.

| Arquivo | Responsabilidade |
| --- | --- |
| `router.py` | `GET` e `PUT` em `/api/v1/unidades/{unidade_id}/moradores`. Declara a cadeia de autorização e traduz HTTP para o service |
| `schemas.py` | Corpo do `PUT` (`extra="forbid"`, só as 7 abas, só `true`/`false`) e formato das respostas |
| `service.py` | Passo 6 da matriz: trava do último com a aba Usuários, auditoria e commit (tudo-ou-nada) |
| `repository.py` | Consultas, todas filtradas pelo condomínio. Inclui a tranca da unidade e o registro de auditoria |

Os models (`MoradorUnidade`, `PermissaoAba`) ficam em [`unidades/models.py`](../unidades/models.py).

## Como a cadeia protege cada rota

```text
require_permission("vinculos:ver")            perfil pode listar moradores?        403
require_permission("permissoes_aba:editar")   perfil pode editar permissões?       403 (só Morador)
require_aba("usuarios")                       unidade é dele?                      404
                                              é Morador sem a aba Usuários?        403
corpo da requisição                           aba inválida, valor não booleano     422
service                                       último com a aba Usuários            409
```

## Pontos de atenção

- **Tranca da unidade:** o `PUT` tranca a linha da unidade (`FOR NO KEY UPDATE`) antes de contar quem tem a aba Usuários. Sem isso, duas pessoas tirando a aba uma da outra ao mesmo tempo deixariam a unidade sem ninguém. Foi verificado com duas conexões reais: com a tranca, um pedido passa e o outro recebe 409; sem ela, os dois passam.
- **Auditoria provisória:** `RepositorioAuditoria.registrar` grava direto em `registros_auditoria`. Quando a TASK-24 (US-1004) entregar o serviço de auditoria, troque o corpo desse método.
- **IP:** vem de `request.client.host`. Atrás de um proxy reverso será o IP do proxy, até o uvicorn ser configurado com `--proxy-headers`.
- **Permissões iniciais:** quem cria o `MoradorUnidade` (fluxo de vínculo, US-301) também cria as 7 linhas de `permissoes_aba`: primeiro morador com tudo, os seguintes sem `usuarios` (proposta a confirmar com o Paulo).
