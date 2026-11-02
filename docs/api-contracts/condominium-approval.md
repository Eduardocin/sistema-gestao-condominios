# Aprovação de condomínios e chaves de acesso (TASK-29)

As decisões de aprovação são restritas ao administrador da plataforma autenticado (`administrador_plataforma=true`).
Administradores de um condomínio não podem aprovar solicitações da plataforma. Toda decisão gera
evento de auditoria e um segundo evento `notificacao_condominio` para a fila de notificações; o
envio de e-mail fica para outra sprint.

## Fila e decisões

- `GET /api/v1/condominios/aprovacoes/pendentes` lista solicitações pendentes, incluindo nome e
  e-mail do solicitante. Requer token bearer do administrador da plataforma.
- `POST /api/v1/condominios/{id}/aprovar` aprova o condomínio, ativa a conta e o vínculo de
  Administração solicitante e gera uma chave de acesso com validade de sete dias. A chave em
  texto claro é mostrada somente nesta resposta.
- `POST /api/v1/condominios/{id}/rejeitar` exige `{"motivo": "..."}` não vazio. Rejeita o
  condomínio, marca a conta de Administração solicitante como rejeitada/inativa e grava o motivo
  para consulta posterior.

Após aprovação ou rejeição, novas decisões para a mesma solicitação retornam `409`. A aprovação e
os eventos de auditoria/notificação são persistidos na mesma transação.

## Consulta do solicitante

`POST /api/v1/condominios/wizard/{id}/finalizar` retorna `token_status_solicitacao` uma única vez.
O cliente deve guardá-lo como segredo. `GET /api/v1/condominios/solicitacoes/{id}` aceita esse
segredo no header `X-Token-Solicitacao` e retorna o status e, se rejeitado, `motivo_rejeicao`.
O banco armazena somente o hash do token.

## Chaves de acesso

- `POST /api/v1/condominios/chaves/validar` recebe `{"chave_acesso": "..."}` e responde se a chave
  está válida e qual condomínio ela representa; não consome a chave.
- `POST /api/v1/condominios/{id}/chaves/regenerar` requer administrador da plataforma. Revoga a
  chave anterior ainda disponível e emite outra com sete dias de validade. Só há uma chave
  disponível por condomínio.
- `POST /api/v1/condominios/{id}/chaves/revogar` revoga a chave disponível sem criar uma nova.
- O cadastro `POST /api/v1/usuarios/moradores` e `POST /api/v1/usuarios/funcionarios` exige uma
  chave válida. O cadastro consome a chave e cria o vínculo pendente do usuário ao condomínio na
  mesma transação. Chaves expiradas, revogadas, inválidas ou usadas são recusadas (`422`).

Funcionário também exige `nome_responsavel`, pois o perfil `funcionario` é uma conta compartilhada
para fins de auditoria. As contas novas e seus vínculos começam pendentes/inativos.

As chaves são geradas com entropia criptográfica e o banco guarda somente SHA-256; elas são únicas,
expiram em sete dias e são de uso único. A validade da chave não é substituto para a aprovação do
cadastro de Morador/Funcionário.
