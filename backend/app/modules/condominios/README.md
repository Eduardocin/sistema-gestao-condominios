# Cadastro de condomínio — TASK-28 / US-202

Reutiliza os modelos existentes de [condomínio](models.py),
[bloco/andar/unidade](../unidades/models.py), vínculo administrativo e histórico de análise.
Não há migration nem dependência nova. Contrato: [núcleo, seção 4](../../../../docs/api-contracts/nucleo.md#4-condomínio-cadastro-estados-e-dados).

## API

| Método e rota | Entrada / resposta |
| --- | --- |
| `POST /api/v1/condominios` | Árvore completa; 201 com `id`, `nome`, `cnpj`, `status`, `enviado_em` e `estrutura` (contagens de blocos/andares/unidades) |
| `GET /api/v1/condominios/meus` | Lista direta de `{id, nome, status, perfil}`, sem paginação, conforme contrato |

Ambas exigem `get_usuario_autenticado` e conta com `tipo_cadastro=administracao` no banco.
ADM da plataforma e outras contas recebem 403; sessão inválida/ausente recebe 401. Não exigem
`cid`. O condomínio eventualmente selecionado no token não define o destino de um novo cadastro.
Criador e IDs da árvore são definidos pelo servidor. O corpo rejeita campos desconhecidos em
todos os níveis, inclusive IDs, estado, privilégios e quantidades em lugar da árvore explícita.

`POST` exige nome de 3–120 caracteres, CNPJ numérico válido de 14 dígitos e endereço completo.
CEP tem oito dígitos; UF tem duas letras e é normalizada em maiúsculas. Os campos do endereço
respeitam os tamanhos dos modelos. A estrutura exige:

- 1–20 blocos, nome de 1–50 caracteres, sem repetição no condomínio;
- 1–100 andares por bloco, nome de 1–50 caracteres, sem repetição no bloco;
- ordem inteira de 0–200 (booleanos/texto não são aceitos);
- 1–60 unidades por andar, até 2000 no condomínio; identificação de 1–20 caracteres com letras,
  dígitos, espaço, hífen e barra, sem repetição no andar.

Espaços externos são removidos dos nomes/identificações. A igualdade segue as constraints
existentes, preservando maiúsculas/minúsculas. Numeração não sequencial e identificações iguais
em andares/blocos diferentes são permitidas. Dados inválidos retornam 422 `validation_error`;
erros de schema incluem `error.details` com caminho do campo, sem valores recebidos. Essa
extensão é local ao router; o envelope das outras APIs permanece inalterado.

O índice `uq_condominios_cnpj` decide a unicidade, inclusive sob concorrência. Sua violação
retorna 409 `cnpj_ja_cadastrado`, sem criar registros parciais. `Location` aponta para
`/api/v1/condominios/meus`. A listagem mostra somente vínculos administrativos ativos da conta,
incluindo condomínios pendentes, rejeitados e desativados, ordenados por nome e ID.

## Transação e autorização

Um único commit confirma condomínio pendente, blocos, andares, unidades ativas, vínculo
administrativo ativo do criador, histórico `enviado` e auditoria `condominio.enviar`.
O repository faz flush por nível para garantir as FKs, sem commits intermediários.
Falhas de persistência, auditoria ou commit revertem toda a operação.

A auditoria usa `registrar_acao`, com conta/IP autenticados, condomínio recém-criado e contagens
da estrutura. Perfil local e responsável ficam nulos: é o cadastro global, anterior à seleção
de um papel local e à lista de responsáveis. Não registra CNPJ, endereço, documentos, senhas ou
tokens nos metadados. A lista de responsáveis continua disponível pelo fluxo existente após a
seleção do condomínio. Criar ou selecionar um pendente não libera as rotas operacionais.
O cadastro inicial não aprova nem gera chaves; esses efeitos entram na TASK-29 abaixo.
Vínculo de Morador continua na TASK-30.

## Escopo e dependências

Etapas visuais, expansão em massa das identificações e conferência da árvore são do frontend.
Não há rascunho persistido, retomada nem endpoints de gravação por etapa. Esses itens literais
do card divergem do contrato adotado. Áreas comuns continuam no módulo de reservas existente;
o payload de cadastro não cria áreas nem um novo sistema de responsáveis.

O storage atual exige condomínio já existente e não oferece upload inicial de logo/documentos.
`logo_arquivo_id=null`/omitido e `documentos=[]`/omitido são aceitos. Referências não vazias são
rejeitadas com 422 `arquivos_indisponiveis_no_cadastro`, mesmo se pertencerem ao criador em outro
condomínio. Não se move arquivo, altera seu escopo ou cria serviço de upload alternativo.

Testes: [cadastro](../../../tests/test_condominios_cadastro.py) e
[concorrência real](../../../tests/test_condominios_concorrencia.py), em PostgreSQL exclusivo.
A concorrência usa transações reais e limpa somente os UUIDs criados pelo teste, seguindo o
padrão já usado pela auditoria. Nenhum banco, volume ou contêiner é recriado/apagado.

## Aprovação e rejeição — TASK-29 / US-203

Reutiliza os modelos, a autorização de plataforma e a auditoria central, sem migration.

| Método e rota | Permissão / comportamento |
| --- | --- |
| `GET /api/v1/plataforma/condominios` | ADM, `cadastro_condominio:ver`; padrão `status=pendente`, busca literal por nome/CNPJ, `page=1`, `page_size=20` (1–100), `total`; ordem `enviado_em ASC, id ASC` |
| `GET /api/v1/plataforma/condominios/{id}` | ADM; dados, endereço, documentos, contagens, árvore e histórico, sem chaves nem proprietários |
| `POST /api/v1/plataforma/condominios/{id}/aprovacao` | ADM, `cadastro_condominio:editar`; corpo `{}`, somente `pendente → ativo` |
| `POST /api/v1/plataforma/condominios/{id}/rejeicao` | ADM; corpo `{"motivo":"..."}`, 1–500 caracteres após remover espaços externos; somente `pendente → rejeitado` |
| `GET /api/v1/condominio` | Administração com `cid` e vínculo ativo, em qualquer status; inclui motivo da rejeição e histórico cronológico |

A fila inclui CNPJ, data de envio, nome/e-mail da conta criadora, documentos e resumo da
estrutura. A sinalização de possível duplicidade usa nome/cidade/UF iguais após aparar espaços
e ignorar caixa, ou logradouro/número/cidade/UF iguais. Valores ausentes não são comparados.
É um aviso, não uma decisão automática; o índice único de CNPJ permanece inalterado.
O download do documento continua no storage existente, que já autoriza o ADM exclusivamente
nos documentos do cadastro e anexos de suporte. Não há nova API de upload.

`SELECT FOR UPDATE` no condomínio serializa decisões concorrentes. A transação vencedora
confirma status/data, uma chave por unidade ativa, histórico `aprovado`, fila `EnvioEmail`
com evento `condominio_aprovado` e auditoria `condominio.aprovar`. As demais decisões recebem
409 `transicao_invalida`. Nenhum helper confirma isoladamente; falha em qualquer etapa
reverte tudo. A rejeição grava status/motivo, histórico e `condominio.rejeitar`, sem e-mail.

O destinatário vem de `criado_por_usuario_id`, nunca do cliente. Cadastro legado sem criador
retorna 409 `cadastro_sem_administracao`, sem efeitos parciais. O processamento e envio SMTP
continuam na Sprint 3. O evento de aprovação contém somente status/quantidade de chaves;
os códigos não entram na auditoria. Ator ADM, IP e horário vêm dos mecanismos existentes.

O ADM não precisa de `cid` e não ganha acesso operacional. A leitura singular usa uma
dependência restrita à identidade/vínculo administrativo, inclusive em pendente/rejeitado;
não altera a dependência de operações diárias, que continua exigindo condomínio ativo.
O reenvio é documentado em Correção e reenvio — TASK-57 / US-204. As transições de status
da plataforma estão documentadas abaixo.

Testes: [aprovação](../../../tests/task29/test_aprovacao.py) e
[concorrência com sessões reais](../../../tests/task29/test_concorrencia.py).
Tratamento das chaves, proprietários e divergências: [unidades](../unidades/README.md).

## Desativação e reativação pela plataforma

| Método e rota | Permissão / comportamento |
| --- | --- |
| `POST /api/v1/plataforma/condominios/{id}/desativacao` | ADM, `cadastro_condominio:editar`; corpo `{}`, somente `ativo → desativado` |
| `POST /api/v1/plataforma/condominios/{id}/reativacao` | ADM, `cadastro_condominio:editar`; corpo `{}`, somente `desativado → ativo` |

As ações bloqueiam a linha do condomínio com `SELECT FOR UPDATE`, gravam a trilha
`condominio.desativar`/`condominio.reativar` com estado anterior e novo na mesma transação e
retornam 409 `transicao_invalida` para qualquer outra origem. Se a auditoria falhar, o status
é revertido. As linhas de estrutura, contas e vínculos não são removidas. Enquanto o status
for `desativado`, nenhum perfil local pode selecionar o condomínio nem usar rotas operacionais;
a Administração mantém acesso de correção apenas em `pendente` e `rejeitado`.


## Correção e reenvio — TASK-57 / US-204

As novas rotas usam o prefixo `/api/v1`:

| Rota | Comportamento |
| --- | --- |
| `GET /condominio` (existente) | Administração lê cadastro, motivo e análises |
| `GET /condominio/estrutura` | Administração lê a árvore existente, inclusive itens inativos, sem dados pessoais ou chaves |
| `PUT /condominio` | Corrige nome, CNPJ e endereço |
| `PUT /estrutura/blocos/{id}` | Corrige nome |
| `PUT /estrutura/andares/{id}` | Corrige nome e ordem |
| `PUT /estrutura/unidades/{id}` | Corrige identificação |
| `POST /condominio/reenvio` | Retorna o cadastro rejeitado à análise |

As quatro edições aceitam `pendente`, `rejeitado` e `ativo` (US-205/206);
`desativado` retorna 403. Reenvio continua exclusivo de `rejeitado`, com 409
`transicao_invalida` nos demais estados. Todas exigem `responsavel_id` ativo do próprio
condomínio. A leitura
administrativa continua disponível nos quatro estados. Identidade e vínculo vêm dos
mecanismos existentes, pelo contexto específico do cadastro; a autorização operacional
não foi flexibilizada. Sem identidade: 401; sem vínculo/perfil/cid: 403; referências
inexistentes ou de outro condomínio: 404. Corpo inválido ou campos extras: 422.

Reenvio recebe `{"responsavel_id":"UUID"}` (precisão do antigo exemplo `{}`, para respeitar
a auditoria central). Na mesma transação: bloqueia a linha do condomínio, revalida o
estado, muda para `pendente`, atualiza `enviado_em`, limpa o motivo corrente, acrescenta
`reenviado` em `condominio_analises` e registra `condominio.reenviar`. A resposta inclui
`enviado_em`. Rejeições anteriores continuam legíveis em `analises`.

Correções usam uma trava conflitante com a decisão do ADM e não recriam registros. IDs, pais,
proprietários, moradores e demais referências permanecem. Auditoria central:
`condominio.editar` e `estrutura.editar`, com a conta, responsável, IP e campos alterados.
CNPJ passa pela máscara central. Constraints existentes protegem a unicidade
(`cnpj_ja_cadastrado` ou `nome_duplicado`); falhas de auditoria/persistência revertem tudo.

## Gestão de estrutura e dados — US-205/206

Além dos PUT existentes, implementados:

- `POST /estrutura/blocos`, `POST /estrutura/blocos/{id}/andares` e
  `POST /estrutura/andares/{id}/unidades`: criação individual, 201, com o mesmo corpo do
  PUT correspondente. Elemento pai deve existir no condomínio e estar ativo.
- `POST /estrutura/{tipo}/{id}/desativacao` e `/reativacao`: corpo
  `{"responsavel_id":"UUID"}`; `tipo` é `blocos`, `andares` ou `unidades`.
  Unidade com morador ativo não pode ser desativada; bloco/andar com unidade ativa também
  não. Reativação exige pais ativos e não reativa filhos automaticamente.
- Desativação revoga a chave vigente. Unidade criada/reativada em condomínio ativo recebe
  chave pelo serviço existente, se não houver vigente. Chaves anteriores e todos os
  registros históricos permanecem; não há exclusão física nem cancelamento em cascata.
- `PUT /condominio` aceita `logo_arquivo_id`: omitido preserva, nulo desassocia, UUID
  associa imagem de `fotos` enviada pela mesma conta no mesmo condomínio. A política de
  download reconhece a logo para os perfis locais, mantendo isolamento e a restrição do
  ADM da plataforma. Upload continua exigindo condomínio ativo, pelo storage atual.
- A alternância já funciona por `GET /condominios/meus` e
  `POST /auth/selecionar-condominio`; autenticação e roteador central não foram alterados.

As escritas de estrutura usam `FOR NO KEY UPDATE` no condomínio (serializa a gestão e
conflita com decisões do ADM, preservando o `KEY SHARE` das FKs da portaria) e
`FOR UPDATE` na unidade quando alterada. Status, chave e um evento `estrutura.editar`
são transacionais. A falha de qualquer etapa reverte todas.

Limites: sem transferência, criação em lote, reconstrução da árvore, rascunhos, novo
upload, e-mail ou alteração de frontend. Upload no cadastro inicial/pendente/rejeitado,
US-208 e US-210 continuam pendentes. Não há nova migration. Os PRs de visitantes/veículos
foram analisados sem incorporação; executar suas regressões quando forem integrados.

Testes focados: [test_condominios_reenvio.py](../../../tests/test_condominios_reenvio.py).
Cobrem correções, IDs/vínculos preservados, histórico de rejeições, estados, perfis,
isolamento, responsáveis, unicidade, rollback após auditoria e disputas de reenvio com
outro reenvio, edição e aprovação em sessões PostgreSQL independentes.

Testes da US-205/206: [test_condominios_estrutura.py](../../../tests/test_condominios_estrutura.py),
com estados, criação, unicidade, pais, chaves, histórico, logo, alternância, rollback e
disputa com inserção de encomenda em sessão independente.
