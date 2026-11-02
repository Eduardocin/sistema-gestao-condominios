# Vínculo de morador com unidade (TASK-30)

O fluxo pressupõe uma conta de Morador ativa, criada previamente, e o vínculo inativo ao
condomínio criado no cadastro por chave da TASK-29. Uma solicitação pendente não ativa o vínculo
ao condomínio nem permite selecionar o condomínio no login. A aprovação associa a unidade e
ativa o vínculo existente; módulos dependentes de unidade devem consultar somente vínculos ativos.

## Solicitar vínculo

`POST /api/v1/unidades/vinculos/solicitar` exige autenticação do Morador e recebe:

```json
{
  "bloco": "A",
  "unidade": "A-01-01",
  "chave_acesso": "chave emitida pela Administração",
  "responsavel_principal": false
}
```

A chave deve pertencer a um condomínio aprovado e é consumida atomicamente com a solicitação.
O condomínio é identificado pela chave; a API confere que bloco e unidade pertencem a ele e que o
Morador já possui cadastro de perfil `morador` no mesmo condomínio. Uma chave só pode criar uma
solicitação. Solicitações duplicadas abertas e vínculos já aprovados são recusados (`409`).
Solicitações rejeitadas podem ser refeitas com uma nova chave.

Uma unidade aceita vários Moradores. O pedido de `responsavel_principal` é opcional; a Administração
decide se o aprova. O banco garante no máximo um responsável principal aprovado por unidade.

## Fila e decisão administrativa

As rotas exigem token da Administração ativa do condomínio selecionado no login:

- `GET /api/v1/unidades/vinculos/pendentes`: lista a fila do condomínio do token.
- `POST /api/v1/unidades/vinculos/{solicitacao_id}/aprovar`: aprova o pedido, ativa o vínculo
  Morador–condomínio e associa a unidade.
- `POST /api/v1/unidades/vinculos/{solicitacao_id}/rejeitar`: rejeita o pedido sem ativar o
  vínculo. O motivo é obrigatório.

Como Administração é conta compartilhada, as decisões recebem `nome_responsavel` para auditoria:

```json
{"nome_responsavel": "Pessoa responsável"}
```

Rejeição:

```json
{
  "motivo": "Comprovante de residência pendente",
  "nome_responsavel": "Pessoa responsável"
}
```

As decisões registram `mudanca_permissao` e `notificacao_condominio` na mesma transação. O evento
de notificação é persistido para processamento futuro; o envio de e-mail está fora do escopo.
Somente solicitações pendentes podem ser decididas; decisões repetidas retornam `409`.
