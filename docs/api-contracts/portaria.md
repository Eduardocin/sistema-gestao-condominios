# Portaria — contrato REST (TASK-12)

Status: encomendas (TASK-36) e entrada e saída de visitantes (TASK-37) têm API e telas autenticadas. A prévia `/prototipos/portaria` continua usando dados locais. Cadastro avulso e consulta de veículos na portaria ficam na TASK-64.

Base: `/api/v1`. JSON em UTF-8, IDs UUID e datas ISO 8601 com fuso, emitidas pelo servidor. Na interface, datas são apresentadas no fuso do condomínio. Atualizações de status usam ações explícitas, sem `PATCH status` genérico.

## Segurança e respostas comuns

- Exigir JWT válido, condomínio ativo e vínculo/permissão carregados pela autorização central. `condominio_id` vem do contexto, nunca da URL ou do corpo. Rejeitar campos extras nos schemas de escrita.
- Aplicar escopo do condomínio a todos os recursos e referências: unidade, morador, funcionário, visitante, autorização e arquivo. Referências externas ao escopo retornam 404 genérico.
- Morador acessa apenas unidades com vínculo ativo e aba correspondente habilitada. Para encomendas, a confirmação também exige que sua conta esteja vinculada ao morador ativo identificado como recebedor na entrega.
- `funcionario_id` identifica um nome ativo do condomínio; registrar também a identidade da conta autenticada no evento de auditoria. A conta compartilhada não identifica sozinha quem atuou.
- Listas: `{"items": [], "page": 1, "page_size": 20, "total": 0}`. `page` >= 1, `page_size` de 1 a 100; ordenação por data decrescente e ID como desempate. Busca e filtros sempre dentro do escopo autorizado.
- Objeto individual retorna diretamente seu JSON. Erros seguem `{"error":{"code":"...","message":"..."}}`, compatível com a estrutura de [health.md](health.md) e com os códigos propostos na matriz.

| HTTP | `code` | Situação |
| --- | --- | --- |
| 401 | `not_authenticated` | Credencial ausente, inválida, expirada ou revogada; incluir `WWW-Authenticate: Bearer` |
| 403 | `forbidden` | Perfil/aba/vínculo sem acesso ou condomínio indisponível |
| 404 | `not_found` | Recurso ou referência inexistente ou fora do escopo; mensagem genérica |
| 409 | `conflict` | Transição repetida, visita já ativa ou autorização inválida/expirada |
| 422 | `validation_error` | Campos inválidos, foto ausente, autorização não concedida |
| 503 | `storage_unavailable` | Storage temporariamente indisponível durante o recebimento |
| 500 | `internal_error` | Falha inesperada com mensagem genérica, sem detalhes internos |

`403` não deve ser usado para revelar a existência de um objeto de outro condomínio. Os nomes de códigos são proposta para o módulo; o backend atual de health ainda usa `http_error` em erros HTTP genéricos.

## Consultas para formulários

Funcionário: `GET /portaria/unidades?busca=101`, `GET /portaria/unidades/{id}/moradores` e `GET /funcionarios?ativo=true`. Para a lista de quem pode confirmar uma entrega, passar `somente_confirmaveis=true` aos moradores; o backend retorna somente vínculos ativos com a aba Encomendas ativa. Na consulta de visitantes, usar as rotas descritas abaixo.

As opções de unidade retornam `id`, `identificacao`, `bloco` e `andar`. Os nomes do bloco e do andar distinguem unidades com a mesma identificação. Unidades antigas sem andar retornam `null` nesses dois campos.

Retornar apenas `id` e identificação/nome necessários ao formulário, com paginação comum; listar somente unidades, vínculos e nomes ativos do condomínio. Documento pessoal e outros dados de cadastro não integram essas respostas. O servidor valida novamente todas as referências na escrita.

## Encomendas

| Método e rota | Perfil / escopo | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /encomendas` | Funcionário e Administração (condomínio); morador (suas unidades com aba ativa) | Query `busca`, `status`, `page`, `page_size` | 200, lista |
| `GET /encomendas/{id}` | Mesmo escopo de leitura | — | 200, objeto com histórico |
| `POST /encomendas` | Funcionário ativo | `multipart/form-data`: `unidade_id`, `destinatario_morador_unidade_id`, `descricao`, `recebido_por_funcionario_id`, `foto` | 201, objeto; `Location` do recurso |
| `POST /encomendas/{id}/entrega` | Funcionário ativo | JSON `recebedor_morador_unidade_id`, `entregue_por_funcionario_id` | 200, objeto atualizado |
| `POST /encomendas/{id}/confirmacao` | Morador que recebeu | `{}`; identidade vem do contexto | 200, objeto atualizado |

No recebimento, a foto é enviada no mesmo `multipart/form-data` que os demais campos. Aceita JPG/JPEG, PNG ou WebP até 5 MiB. O backend valida a imagem e a envia ao storage privado; a transação registra os metadados do arquivo, a encomenda, auditoria e o evento de e-mail na outbox. `condominio_id` e identidade do funcionário vêm do contexto autenticado, não do formulário. O evento `encomenda_registrada` fica pendente em `envios_email`; o worker de envio da US-803 ainda não está implementado, portanto o sucesso do recebimento não significa que o e-mail foi enviado.

`descricao` aceita de 1 a 200 caracteres após trim. A unidade, o morador destinatário e o funcionário informado devem estar ativos e pertencer ao condomínio autenticado; o morador deve ter vínculo ativo com a unidade. Campos extras, inclusive `condominio_id`, são rejeitados.

Objeto de encomenda:

```json
{
  "id": "UUID",
  "unidade": {"id": "UUID", "identificacao": "Bloco A / 101"},
  "destinatario": {"id": "UUID", "nome": "Ana Martins"},
  "descricao": "Caixa pequena · Livraria",
  "foto_arquivo_id": "UUID",
  "status": "aguardando_retirada",
  "recebimento": {"em": "2026-10-20T15:00:00Z", "funcionario_id": "UUID", "funcionario_nome": "Carlos Silva"},
  "entrega": null,
  "confirmacao": null,
  "pode_confirmar": false
}
```

O objeto também contém `unidade`, `destinatario` (ambos com `id` e nome/identificação) e `foto_arquivo_id`. Após entrega, `status = entregue_aguardando_confirmacao` e `entrega` inclui data, funcionário que registrou e morador recebedor, com nomes para exibição. Após confirmação, `status = retirada_confirmada` e `confirmacao` inclui data e morador. `pode_confirmar` só é verdadeiro na resposta ao morador ativo que recebeu a encomenda. Datas são emitidas pelo servidor em ISO 8601 com fuso.

Regras: destinatário e recebedor têm vínculo ativo na unidade; recebedor pode diferir do destinatário e também precisa ter acesso ativo à aba Encomendas. A opção `somente_confirmaveis=true` na consulta de moradores filtra a lista da portaria por essa permissão. Entrega só parte de `aguardando_retirada`; confirmação só parte de `entregue_aguardando_confirmacao`. Repetição retorna 409. Uma encomenda de outro condomínio ou fora das unidades autorizadas retorna 404; o morador que não é recebedor não pode confirmar e recebe 404. Perfil/aba sem acesso retorna 403; conteúdo ou referências inválidas retornam 422; indisponibilidade do MinIO retorna 503. Pendências não expiram nem se confirmam automaticamente. A portaria não possui endpoint para confirmar pelo morador.

Para ler a foto, usar `GET /arquivos/{foto_arquivo_id}/download` com Bearer. A rota verifica o escopo da encomenda e devolve uma URL assinada temporária; o storage permanece privado.

## Autorização prévia por período

- `GET /portaria/visitantes?busca=&unidade_id=&page=&page_size=` busca cadastros pelo nome, com unidade opcional.
- `POST /portaria/visitantes/busca-documento?page=&page_size=` consulta por CPF completo. O corpo contém `unidade_id` e `cpf`; o CPF não vai na URL nem no retorno.
- Ambas retornam `items`, `total`, `page`, `page_size`. As opções incluem `id`, `nome`, `unidade_id`, `unidade` (id e nome com bloco e andar), `entrada_prevista`, `saida_prevista` e `ambigua`. Se nome, unidade e período forem iguais dentro do resultado, `ambigua=true` mesmo em páginas diferentes. A portaria deve refinar a busca ou solicitar ao morador que revise o cadastro.

| Método e rota | Perfil / escopo | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /portaria/autorizacoes?visitante_id=UUID&unidade_id=UUID` | Funcionário, condomínio | Consulta do cadastro e seu período autorizado | 200, lista de autorizações vigentes projetadas do cadastro |

Decisão de 22/10/2026: adotar a abordagem do PR #5. A autorização decorre do cadastro feito pelo morador, vale para a unidade cadastrada e pode ser usada em várias visitas durante o período. Não existe consumo por uso único. A consulta é uma projeção, não exige uma tabela adicional de autorizações: `id` identifica o cadastro autorizado; a resposta traz também `visitante_id`, `unidade_id`, `autorizado_por`, `inicio` e `fim`.

No DER, `entrada_prevista` e `saida_prevista` são datas inclusivas no fuso do condomínio. A API deve convertê-las em limites com fuso: do início do primeiro dia até o início do dia seguinte à saída prevista, com limite final exclusivo (`inicio <= agora < fim`). Validar também cadastro não cancelado, vínculo ativo e permissão do morador autorizador. A criação/edição do cadastro continua no módulo de Vitor; este contrato não cria um segundo cadastro de autorizações. Na prévia local, os limites já são timestamps de exemplo.

## Visitas e contatos externos

| Método e rota | Perfil | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /visitas` | Funcionário | `busca`, `status`, paginação | 200, lista |
| `GET /visitas/{id}` | Funcionário | — | 200, histórico |
| `POST /visitas` | Funcionário | Entrada autorizada abaixo | 201, visita `em_andamento` |
| `POST /visitas/{id}/saida` | Funcionário | `funcionario_id` | 200, visita `encerrada` |
| `POST /portaria/contatos` | Funcionário | Contato negado/sem resposta abaixo | 201, contato sem visita |
| `GET /portaria/contatos` | Funcionário | Paginação | 200, lista de contatos |

Entrada com autorização prévia:

```json
{"visitante_id":"UUID","unidade_id":"UUID","funcionario_id":"UUID","autorizacao_id":"UUID"}
```

Entrada após contato externo:

```json
{
  "visitante_id":"UUID",
  "unidade_id":"UUID",
  "funcionario_id":"UUID",
  "contato":{"morador_id":"UUID","canal":"interfone","resposta":"autorizou"}
}
```

Exigir **exatamente um** entre `autorizacao_id` e `contato`. Canal: `interfone` ou `telefone`. O morador consultado deve ter vínculo ativo na unidade. Contato com `resposta` diferente de `autorizou` não cria visita (422); registrar separadamente em `/portaria/contatos`, com os mesmos dados e `resposta = negou | sem_resposta`. Retorno do contato contém `id`, referências, resposta, canal, `registrado_em` e funcionário; nunca uma visita liberada.

Visita retorna `id`, `visitante` (id/nome), `unidade` (id/nome), `status`, `entrada` (em/funcionário), `autorizacao_id` e `autorizacao` com a janela registrada ou `contato`, e `saida` (null até encerramento; depois em/funcionário). A conta autenticada permanece na auditoria interna. O histórico conserva a evidência validada na entrada. Registros anteriores à migração podem retornar os campos de evidência como `null`.

Na entrada: validar visitante existente e cadastrado para a unidade selecionada; não admitir visitante avulso nesta etapa; verificar a autorização naquele momento e impedir outra visita em andamento do mesmo cadastro. A autorização não é consumida: após registrar a saída, outra visita pode usar a mesma permissão enquanto o período estiver vigente. A unicidade de visita aberta deve ser garantida também no banco; pedidos concorrentes para o mesmo cadastro só podem gerar uma visita ativa, com 409 para o perdedor. Na saída: aceitar somente `em_andamento`, preservar histórico e impedir repetição (409). Sem saída registrada, a visita permanece ativa, sem confirmação do morador ou encerramento automático. Fora do período, exigir novo contato externo autorizado antes de uma nova entrada.

## Casos obrigatórios antes de integrar

Testar leitura e escrita cruzadas entre dois condomínios para todos os recursos e referências; cadastro de visitante de outra unidade; escopo de unidade do morador; ação de confirmação por identidade diferente; funcionário inativo; foto sem escopo; entrega/saída duplicada; duas entradas concorrentes para o mesmo cadastro; reentrada válida após saída e dentro do período; ausência, expiração e cancelamento da autorização; negativa e falta de resposta sem visita criada. Os testes da prévia React cobrem as regras locais de apresentação e transição. A migração `20261121_0008` guarda contatos sem entrada em `contatos_portaria` e a evidência de entrada em `registros_visita`.

Pendências e responsáveis: [decisoes-pendentes.md](../portaria/decisoes-pendentes.md).
