# Portaria — proposta de contrato REST (TASK-12)

Status: rascunho para revisão com modelo de dados, autorização central e armazenamento. Endpoints abaixo **não estão implementados**. A prévia `/prototipos/portaria` não os chama; IDs curtos e fotos em memória usados nela não são payloads de produção.

Base: `/api/v1`. JSON em UTF-8, IDs UUID e datas ISO 8601 com fuso, emitidas pelo servidor. Na interface, datas são apresentadas no fuso do condomínio. Atualizações de status usam ações explícitas, sem `PATCH status` genérico.

## Segurança e respostas comuns

- Exigir JWT válido, condomínio ativo e vínculo/permissão carregados pela autorização central. `condominio_id` vem do contexto, nunca da URL ou do corpo. Rejeitar campos extras nos schemas de escrita.
- Aplicar escopo do condomínio a todos os recursos e referências: unidade, morador, funcionário, visitante, autorização e arquivo. Referências externas ao escopo retornam 404 genérico.
- Morador acessa apenas unidades com vínculo ativo e aba Encomendas/Visitantes habilitada. Confirmação de encomenda também exige ser o recebedor registrado. A regra consta da matriz após o PR #5; sua implementação na autorização central continua pendente.
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
| 500 | `internal_error` | Falha inesperada com mensagem genérica, sem detalhes internos |

`403` não deve ser usado para revelar a existência de um objeto de outro condomínio. Os nomes de códigos são proposta para o módulo; o backend atual de health ainda usa `http_error` em erros HTTP genéricos.

## Consultas para formulários

Funcionário: `GET /portaria/unidades?busca=101`, `GET /portaria/unidades/{id}/moradores`, `GET /portaria/funcionarios` e `GET /portaria/visitantes?busca=Carlos`.

Retornar apenas `id` e identificação/nome necessários ao formulário, com paginação comum; listar somente unidades, vínculos e nomes ativos do condomínio. Documento pessoal e outros dados de cadastro não integram essas respostas. O servidor valida novamente todas as referências na escrita.

## Encomendas

| Método e rota | Perfil / escopo | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /encomendas` | Funcionário (condomínio); morador (suas unidades) | Query `busca`, `status`, `page`, `page_size` | 200, lista |
| `GET /encomendas/{id}` | Mesmo escopo | — | 200, objeto com histórico |
| `POST /encomendas` | Funcionário | JSON de recebimento | 201, objeto; `Location` do recurso |
| `POST /encomendas/{id}/entrega` | Funcionário | `recebedor_id`, `funcionario_id` | 200, objeto atualizado |
| `POST /encomendas/{id}/confirmacao` | Morador que recebeu | `{}`; identidade vem do contexto | 200, objeto atualizado |

Recebimento:

```json
{
  "unidade_id": "UUID",
  "destinatario_id": "UUID",
  "descricao": "Caixa pequena · Livraria",
  "foto_arquivo_id": "UUID",
  "funcionario_id": "UUID"
}
```

Descrição de 1 a 200 caracteres após trim (proposta). Foto obrigatória: arquivo de imagem validado, pertencente ao contexto e destinado a este módulo. O armazenamento da TASK-26 fornecerá o ID; não aceitar URL arbitrária, caminho de disco nem imagem base64 neste endpoint. JPG/PNG/WebP e 5 MB são limites propostos, sujeitos à revisão da TASK-26. O upload e sua limpeza não são definidos como implementados por este contrato.

Objeto de encomenda:

```json
{
  "id": "UUID",
  "unidade": {"id": "UUID", "identificacao": "Bloco A / 101"},
  "destinatario": {"id": "UUID", "nome": "Ana Martins"},
  "descricao": "Caixa pequena · Livraria",
  "foto_arquivo_id": "UUID",
  "status": "aguardando_retirada",
  "recebimento": {"em": "2026-10-20T15:00:00Z", "funcionario_id": "UUID"},
  "entrega": null,
  "confirmacao": null
}
```

Após entrega, `status = entregue_aguardando_confirmacao` e `entrega = {"em":"...","funcionario_id":"UUID","recebedor_id":"UUID"}`. Após confirmação, `status = retirada_confirmada` e `confirmacao = {"em":"...","morador_id":"UUID"}`. Nomes de exibição dos responsáveis podem ser incluídos nas estruturas de histórico, somente no escopo autorizado. Datas e atores anteriores são preservados.

Regras: destinatário e recebedor têm vínculo ativo na unidade; recebedor pode diferir do destinatário. Entrega só parte de `aguardando_retirada`; confirmação só parte de `entregue_aguardando_confirmacao`. Repetição retorna 409. Morador que não é o recebedor não tem acesso à ação sobre esse objeto (404). Pendências não expiram nem se confirmam automaticamente. A portaria não possui endpoint para confirmar pelo morador.

Leitura da foto deve ser protegida pelo escopo da encomenda. O mecanismo de download e a eventual URL temporária serão definidos na TASK-26; não expor arquivos publicamente.

## Autorização prévia por período

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

Visita retorna `id`, `visitante` (id/nome), `unidade` (id/identificação), `status`, `entrada` (em/funcionário), `autorizacao_id` ou `contato`, e `saida` (null até encerramento; depois em/funcionário). A conta autenticada permanece na auditoria interna. Histórico deve conservar a evidência da autorização usada, mesmo após sua validade terminar.

Na entrada: validar visitante existente e cadastrado para a unidade selecionada; não admitir visitante avulso nesta etapa; verificar a autorização naquele momento e impedir outra visita em andamento do mesmo cadastro. A autorização não é consumida: após registrar a saída, outra visita pode usar a mesma permissão enquanto o período estiver vigente. A unicidade de visita aberta deve ser garantida também no banco; pedidos concorrentes para o mesmo cadastro só podem gerar uma visita ativa, com 409 para o perdedor. Na saída: aceitar somente `em_andamento`, preservar histórico e impedir repetição (409). Sem saída registrada, a visita permanece ativa, sem confirmação do morador ou encerramento automático. Fora do período, exigir novo contato externo autorizado antes de uma nova entrada.

## Casos obrigatórios antes de integrar

Testar leitura e escrita cruzadas entre dois condomínios para todos os recursos e referências; cadastro de visitante de outra unidade; escopo de unidade do morador; ação de confirmação por identidade diferente; funcionário inativo; foto sem escopo; entrega/saída duplicada; duas entradas concorrentes para o mesmo cadastro; reentrada válida após saída e dentro do período; ausência, expiração e cancelamento da autorização; negativa e falta de resposta sem visita criada. Os testes da prévia React cobrem somente as regras locais de apresentação e transição. A representação persistente dos contatos sem entrada permanece pendente no DER.

Pendências e responsáveis: [decisoes-pendentes.md](../portaria/decisoes-pendentes.md).
