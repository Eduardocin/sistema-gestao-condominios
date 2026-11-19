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
Não implementa reenvio, desativação, reativação nem qualquer vínculo de morador.

Testes: [aprovação](../../../tests/task29/test_aprovacao.py) e
[concorrência com sessões reais](../../../tests/task29/test_concorrencia.py).
Tratamento das chaves, proprietários e divergências: [unidades](../unidades/README.md).
