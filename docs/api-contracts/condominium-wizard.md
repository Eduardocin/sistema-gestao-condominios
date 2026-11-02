# Wizard de cadastro de condomínio (TASK-28)

O wizard permite iniciar, salvar, retomar e concluir um cadastro sem acesso direto ao banco.
Cada rascunho tem um token aleatório de acesso, mostrado somente na resposta inicial. O banco
guarda apenas o hash do token. Envie o token no header `X-Wizard-Token` em todas as outras rotas
do rascunho. Guarde-o com segurança no cliente: quem possui o token pode alterar e concluir esse
cadastro. Rascunhos expiram em 30 dias.

## Endpoints e sequência

1. `POST /api/v1/condominios/wizard` inicia o rascunho e retorna `id` e `token`.
2. `PUT /api/v1/condominios/wizard/{id}/etapas/dados-gerais` salva nome e endereço.
3. `PUT /api/v1/condominios/wizard/{id}/etapas/blocos` salva a lista de blocos/torres.
4. `PUT /api/v1/condominios/wizard/{id}/etapas/unidades` define andares e unidades por andar.
5. `PUT /api/v1/condominios/wizard/{id}/etapas/areas-comuns` salva áreas; lista vazia é válida.
6. `PUT /api/v1/condominios/wizard/{id}/etapas/responsavel` salva os dados da Administração.
7. `GET /api/v1/condominios/wizard/{id}` retoma os dados salvos. A senha e seu hash nunca são
   retornados.
8. `POST /api/v1/condominios/wizard/{id}/finalizar` valida e grava o cadastro completo.

Uma etapa não pode ser salva até a etapa anterior estar completa. Editar uma etapa invalida as
etapas seguintes, que devem ser reenviadas. Erros de validação retornam `422`; token ou rascunho
inexistente retornam `404`; etapa fora de ordem ou wizard incompleto retornam `409`; rascunho
expirado retorna `410`.

## Exemplo de geração em massa

Blocos:

```json
{"blocos": [{"nome": "A"}, {"nome": "B"}, {"nome": "C"}]}
```

Unidades:

```json
{
  "geracoes": [
    {"bloco": "A", "andar_inicial": 1, "quantidade_andares": 10, "unidades_por_andar": 4},
    {"bloco": "B", "andar_inicial": 1, "quantidade_andares": 10, "unidades_por_andar": 4},
    {"bloco": "C", "andar_inicial": 1, "quantidade_andares": 10, "unidades_por_andar": 4}
  ]
}
```

Isso gera 120 unidades com identificadores como `A-01-01` e `C-10-04`. O máximo é 10.000
unidades por condomínio.

## Conclusão e integridade

A finalização cria condomínio, blocos, unidades, áreas comuns, usuário de Administração, vínculo e
evento de auditoria na mesma transação. Em falha, nenhuma dessas entidades é persistida e o
rascunho continua disponível para correção. A nova conta e seu vínculo começam pendentes/inativos,
seguindo a TASK-27. O condomínio também começa inativo até o fluxo autorizado de aprovação
(TASK-29) ativá-lo.

O sucesso retorna os IDs do condomínio e da conta, informa se o condomínio está ativo, o total de
unidades geradas e o estado pendente da conta. Após a confirmação, o rascunho e os dados
temporários (incluindo o hash da senha) são removidos. A resposta também entrega
`token_status_solicitacao` uma única vez; o solicitante deve guardá-lo para consultar o status e
eventual motivo de rejeição. A aprovação, a chave e a consulta de decisão estão documentadas em
[condominium-approval.md](./condominium-approval.md).
