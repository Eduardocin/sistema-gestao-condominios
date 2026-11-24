# Unidades, proprietários e chaves — TASK-29 / US-207

Reutiliza [modelos](models.py), repositório com isolamento por condomínio, validadores de
CPF/CNPJ/e-mail/telefone, responsáveis, auditoria e storage. Sem dependências ou migrations.
Contrato: [núcleo, seção 6](../../../../docs/api-contracts/nucleo.md#6-proprietário-e-chaves-de-acesso-us-207-must-sprint-1).

## API e permissões

Todas as rotas abaixo exigem Administração, vínculo ativo e condomínio ativo lidos do banco.
O condomínio vem do JWT validado; IDs de outras unidades/condomínios resultam em 404 genérico.
ADM, Funcionário e Morador não recebem chaves nem dados de proprietário nestas rotas.

| Método e rota | Comportamento |
| --- | --- |
| `GET /api/v1/unidades` | Filtros `bloco_id`, `andar_id`, `busca` literal, `sem_proprietario`, `ativo=true`; `page=1`, `page_size=20` (1–100), `total`; identificação/ID crescentes |
| `GET /api/v1/unidades/{id}` | Identificação, bloco/andar, estado, proprietário, chave vigente ou `null`, leitura dos moradores já existentes |
| `PUT /api/v1/unidades/{id}/proprietario` | Cria ou substitui o único proprietário; `responsavel_id` obrigatório |
| `GET /api/v1/unidades/{id}/chave` | Código e data em UTC; 404 sem chave vigente/unidade inativa |
| `POST /api/v1/unidades/{id}/chave` | `{"responsavel_id":"UUID"}`; 201 + `Location`; 409 se já existe chave |
| `POST /api/v1/unidades/{id}/chave/regeneracao` | Mesmo corpo; revoga a anterior e cria a nova; 200 |
| `POST /api/v1/unidades/{id}/chave/revogacao` | Mesmo corpo; revoga e deixa a unidade sem chave; 200 com `revogada_em` |

Regenerar/revogar sem chave vigente retorna 409 `sem_chave_vigente`. Escritas de chave em
unidade inativa retornam 409 `unidade_inativa`. Geração duplicada: 409 `chave_vigente`.
Escritas rejeitam campos extras, inclusive IDs de escopo, código, datas e privilégios.

As permissões são as da matriz central (`chaves_acesso:ver/criar/editar/desativar` e
`proprietarios:editar`). A leitura de detalhe inclui chave, por isso usa a permissão restrita
`chaves_acesso:ver`. Não se abre essa resposta a perfis que só podem ver a estrutura.

## Atomicidade e concorrência

A US-305 reutiliza a trava da unidade e o repositório de chaves para revogar a vigente na
mesma transação da desvinculação. Não gera outra chave nem cancela registros operacionais.
Depois, a Administração deve usar a rota de **geração**, pois a regeneração continua
exigindo uma chave vigente. A nova chave deve ser fornecida somente às pessoas legitimamente
autorizadas. A revogação automática é identificada no único evento `vinculo.desfazer`, sem
duplicar `chave.revogar`. As três ações manuais de chave mantêm suas semânticas.

O bloqueio `FOR UPDATE` na unidade serializa geração, regeneração, revogação e cadastro/edição
do proprietário, inclusive a primeira criação. O índice parcial existente garante no máximo
uma chave vigente; a constraint global de código inclui chaves antigas e revogadas.
`secrets.choice` gera dez caracteres, armazenados sem hífen e exibidos em grupos de cinco.
Cada colisão de código reverte somente o savepoint da tentativa; há até cinco sorteios.
Se todos colidirem, retorna 503 sem alterar a chave anterior. Outros erros SQL são traduzidos
para erro genérico, impedindo que parâmetros com códigos cheguem ao logger de exceções.
Auditoria e escrita confirmam juntas; falha na auditoria também reverte revogação/regeneração.

## Proprietário e arquivos

Nome e CPF/CNPJ são obrigatórios; dígitos verificadores são validados. E-mails são normalizados
em minúsculas, com até dois itens. WhatsApps têm até dois itens; telefone opcional e WhatsApps
exigem DDD e 10 ou 11 dígitos, sem máscara. Listas vazias e telefone/foto nulos são permitidos.
A foto é referência a imagem já enviada pelo próprio usuário para `fotos` no mesmo condomínio,
validada por `RepositorioFotos`; não se aceita URL/base64 nem se cria serviço de upload.
A política de download reconhece a associação ao proprietário e permite Administração do
condomínio. Na TASK-30, a leitura da foto para Morador passa pelo próprio vínculo ativo e aba
Unidades, conforme o [módulo de vínculos](../vinculos/README.md). O ADM continua sem acesso.

`proprietario.editar` registra presença anterior/posterior e documento com máscara central;
não inclui contatos ou imagem. Eventos `chave.gerar`, `chave.regenerar` e `chave.revogar`
registram somente IDs das chaves e recurso/unidade, nunca códigos. Todos usam conta,
responsável ativo do próprio condomínio, IP e data/hora do mecanismo central.

## Precisões e divergências documentais

- Adota a chave **por unidade** do contrato, sem expiração e sem uso único. Vários moradores
  poderão usá-la até revogação/regeneração. Não cria campos para os comportamentos divergentes
  do card da TASK-29. A validação para vínculo foi implementada na TASK-30, sem consumir a chave.
- O contrato e a implementação usam **31** símbolos alfanuméricos, excluindo `0 O 1 I L`.
  Usa-se explicitamente `23456789ABCDEFGHJKMNPQRSTUVWXYZ`, com
  dez posições (aproximadamente 49,54 bits), preservando as exclusões sem inventar símbolos.
- Os corpos das ações de chave da seção 6.2 exigem `responsavel_id`, conforme a convenção
  geral de contas compartilhadas e a auditoria. Ele é obrigatório nas chaves e no proprietário.
  Responsável ausente: 422; alheio/inativo: 404. Não há outro
  mecanismo de autenticação ou exceção à identificação do responsável.
- A confirmação por e-mail da US-203 é registrada na outbox existente na transação de
  aprovação. Entrega efetiva, SMTP e processamento ficam na Sprint 3.
- Unicidade de CNPJ é preservada; possíveis duplicidades são apenas sinalizadas por nome/local.

Não implementa vínculos, convites, aprovação de moradores, permissões por aba, tentativas de
chave ou envio de mensagens. Os moradores do detalhe são apenas leitura do modelo existente.
Fotos no cadastro inicial do prédio continuam com a limitação de bootstrap da TASK-28.

Testes: [chaves/proprietários](../../../tests/task29/test_unidades.py),
[aprovação/rollback](../../../tests/task29/test_aprovacao.py) e
[concorrência real](../../../tests/task29/test_concorrencia.py), com fixtures existentes e
PostgreSQL exclusivo do worktree. A limpeza remove somente UUIDs criados pelos testes.
