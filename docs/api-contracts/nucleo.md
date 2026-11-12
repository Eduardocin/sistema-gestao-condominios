# Núcleo — proposta de contrato REST (TASK-78)

Status: rascunho para revisão do Gabriel e do front (Guilherme e Matheus) e aprovação no portão dos leads. O cadastro de contas da seção 3.1–3.2 está implementado na TASK-31, assim como a autenticação da seção 2 (TASK-80). Os demais endpoints de negócio continuam propostas, salvo indicação específica. Detalhes do recorte implementado: [contas](../../backend/app/modules/contas/README.md).

O núcleo é o que existe antes de qualquer módulo de negócio funcionar: contas, condomínio, estrutura do prédio, aprovação pelo ADM, chaves de acesso e vínculo do morador. Também fixa, como referência para o front, as duas rotas de login da TASK-80.

Convenções comuns (envelope de erro, paginação, ações explícitas, `responsavel_id`, arquivos, fuso, rotas sem `cid`): [convencoes.md](convencoes.md). Modelo de dados: [modelo-de-dados.md](../modelo-de-dados.md), seções 3.1, 3.2 e 5. Permissões e token: [matriz](../permissoes-e-multitenant.md), seções 3, 4, 5 e 7. Edição da estrutura do prédio: [plataforma.md](plataforma.md), seção 7.

Histórias cobertas: US-101, US-104, US-201 a US-204, US-206 a US-208, US-301, US-302, US-303, US-304 e US-305. (US-102 e US-103 aparecem na tabela 3.3, só como rotas de apoio.)

## 1. Regras que valem para o módulo todo

- O `condominio_id` vem do token (R1). As rotas de `/plataforma/...` são as únicas que recebem um ID de condomínio na URL (R9). `POST /condominios`, `POST /vinculos/chave` e as rotas de conta rodam **sem** `cid` no token ([convencoes.md](convencoes.md) seção 2).
- **Isolamento do cadastro:** quando o condomínio **não está `ativo`**, a Administração só vê e corrige o cadastro (R7). A tabela da seção 4.1 diz exatamente quais rotas valem em cada status.
- Nenhum perfil apaga registro. ADM desativa; Administração desativa; ninguém exclui.
- Mensagem de erro de credencial é sempre genérica ("E-mail ou senha incorretos."), sem dizer qual dos dois falhou.
- `usuarios.email` é guardado em **minúsculas** (ADR 0002); CPF, CNPJ e telefone só com dígitos. A máscara é coisa da tela (DER, convenções).

## 2. Autenticação — referência para a TASK-80

O comportamento implementado do login tem como fonte [auth.md](auth.md), entregue no
[PR #11](https://github.com/Eduardocin/sistema-gestao-condominios/pull/11).
Esta seção resume a integração com o front; não cria um segundo contrato de autenticação.
Enquanto o PR #11 não entrar na main, essas rotas continuam sendo uma dependência desta proposta.

### 2.1 Login e seleção de condomínio

`POST /auth/login` recebe:

```json
{"identificador": "ana@exemplo.com", "senha": "••••••••"}
```

Na implementação da TASK-80, `identificador` aceita **e-mail**, normalizado pelo
servidor. Login por telefone permanece requisito da US-101 a integrar quando o
banco oferecer a coluna correspondente; não é comportamento já disponível.

A resposta de sessão inclui `access_token`, `refresh_token`, `token_type`,
`expires_in`, `usuario` (`id`, `nome`, `email`), `condominio`, `condominios`,
`requer_selecao` e `administrador_plataforma`. O exemplo completo e os códigos
HTTP estão em `auth.md`.

- Um único vínculo ativo **e liberado** seleciona o condomínio e emite `cid`.
- Vários vínculos ativos deixam `condominio = null`, `requer_selecao = true` e
  token sem `cid`; o front chama `POST /auth/selecionar-condominio`.
- Nenhum vínculo ou ADM da plataforma: token sem `cid`, sem seleção obrigatória.
- Um vínculo em condomínio indisponível para o perfil não é selecionado;
  `requer_selecao = false` e o status aparece na lista de condomínios.

`POST /auth/selecionar-condominio` recebe `{"condominio_id": "UUID"}`, exige Bearer
e devolve uma nova sessão. Sem vínculo ativo: 404 genérico. Condomínio não
liberado para o perfil: 403. A implementação atual usa o booleano `ativo` e
permite à Administração voltar ao fluxo de cadastro; os quatro status do
núcleo e a autorização por ação continuam dependentes da evolução do banco
e da TASK-19. Essa exceção não autoriza operações do dia a dia.

Credenciais erradas, usuário inativo ou sem senha retornam o mesmo 401.
O limite de tentativas já existe: padrão de 5 falhas por e-mail, com bloqueio
de 15 minutos, 429 e `Retry-After`. O contador fica na memória de uma instância.
Falhas de login usam log; o evento persistente de auditoria aguarda a US-1004.

### 2.2 Renovação e dados da sessão

`POST /auth/refresh` recebe `{"refresh_token": "..."}` e devolve um novo access
token, seu tipo e validade. Os padrões são 15 minutos para access e 7 dias para
refresh. O refresh não é rotacionado; mudança de `sessao_versao` invalida as sessões.
Assinatura HS256 configurada por `JWT_SECRET_KEY`; nomes e limites em `auth.md`.

`GET /auth/me` exige Bearer, mas aceita token sem `cid`. Devolve `usuario`,
`condominio`, `unidades` e `administrador_plataforma`. Por enquanto, unidades
trazem `id` e `identificacao`, com o vínculo disponível no banco atual.

**Campos futuros não são garantidos pela TASK-80:** `usuario.tipo_cadastro`
é persistido pelo cadastro de contas, mas ainda não é exposto na sessão; permissões por aba dependem da
TASK-21; múltiplas unidades dependem da tabela morador–unidade. Os exemplos
das demais seções deste contrato continuam propostas para esses fluxos.

A dependência `get_usuario_autenticado` valida a identidade e a sessão. As
rotas de negócio de um condomínio usam `get_current_context` (TASK-18), que além
da identidade confere no banco o vínculo ativo e o condomínio ativo (401 ou 403) e
entrega o contexto usado para filtrar os dados (404 para o que é de outro
condomínio); veja [Como criar um endpoint novo respeitando o isolamento](../architecture.md#como-criar-um-endpoint-novo-respeitando-o-isolamento).
Unidade, perfil e ação ainda dependem da autorização central (TASK-19);
não basta receber um token válido.

## 3. Contas

### 3.1 Criar conta de morador (US-104, Must, Sprint 1)

`POST /contas/morador` — público.

```json
{"nome": "Ana Martins", "telefone": "11987654321", "email": "ana@exemplo.com", "senha": "••••••••"}
```

| Campo | Regra |
| --- | --- |
| `nome` | Obrigatório, nome completo: 2 ou mais palavras, 3 a 120 caracteres (proposta) |
| `telefone` | Obrigatório, só dígitos com DDD, 10 ou 11 dígitos; único |
| `email` | Obrigatório, formato válido, até 254 caracteres, minúsculas; único |
| `senha` | Obrigatória, 8 a 128 caracteres, com ao menos uma letra e um dígito, diferente do e-mail (proposta de "regra mínima"). Guardada com argon2id |

A **foto** é opcional na US-104, mas o upload exige uma conta autenticada (TASK-26). **Proposta:** a foto não vai neste pedido; entra depois, por `PUT /contas/me` (US-103). A mesma regra vale para o documento comprobatório da Administração (seção 3.2).

Resposta 201: o mesmo objeto do login (a conta já sai autenticada, porque a US-104 manda o morador direto para a tela de vincular unidade). Sem vínculo, `condominios` vem vazio. Cria `usuarios` com `tipo_cadastro = 'morador'`.

Erros: 409 `conflict` com `reason` = `email_ja_cadastrado` ou `telefone_ja_cadastrado`; 422 nas demais. Esses 409 revelam que o e-mail existe; é um custo conhecido do cadastro aberto e depende do limite de tentativas da pendência de rate limit.

### 3.2 Criar conta de Administração (US-201, Must, Sprint 1)

`POST /contas/administracao` — público, **rota separada** da de morador ("a tela é separada").

```json
{"nome": "Condomínio Aurora Gestão Ltda", "documento": "12345678000199", "email": "sindico@exemplo.com", "telefone": "11987654321", "senha": "••••••••"}
```

`nome` (nome ou razão social, 3 a 120), `documento` (CPF de 11 ou CNPJ de 14 dígitos, **com validação dos dígitos verificadores**, único), `email`, `telefone` e `senha` com as mesmas regras de 3.1. O **documento comprobatório** (ata ou contrato) é opcional e é enviado no cadastro do prédio (seção 4.2), porque o DER o guarda por condomínio (`condominio_documentos`). Resposta 201 igual à de 3.1, com `tipo_cadastro = 'administracao'`. Erros: 409 com `reason` = `email_ja_cadastrado`, `telefone_ja_cadastrado` ou `documento_ja_cadastrado`.

`tipo_cadastro` já existe na tabela `usuarios` e é preenchido por estas rotas. A criação de conta não implementa o assistente de cadastro do prédio nem cria vínculos automaticamente.

### 3.3 Demais rotas de conta (Gabriel, Sprint 3, só resumo)

| Método e rota | Quem | O que faz | História |
| --- | --- | --- | --- |
| `GET /contas/me` | Qualquer conta | Dados da conta | US-103 |
| `PUT /contas/me` | Qualquer conta | Edita nome, telefone, e-mail e `foto_arquivo_id` | US-103 |
| `PUT /contas/me/senha` | Qualquer conta | `{"senha_atual", "senha_nova"}`; incrementa `sessao_versao` e devolve um token novo | US-103, US-210 |
| `POST /contas/recuperacao-senha` | Público | `{"email"}`; **sempre 202**, exista ou não a conta; enfileira o e-mail `recuperacao_senha` | US-102 |
| `POST /contas/redefinicao-senha` | Público | `{"token", "senha_nova"}`; token de uso único (`UPDATE ... WHERE usado_em IS NULL`) e com validade; incrementa `sessao_versao` | US-102 |

## 4. Condomínio (cadastro, estados e dados)

### 4.1 Estados e transições (US-202, US-203, US-204, US-208)

Estados (`condominios.status`, regra 7 do DER): `pendente`, `ativo`, `rejeitado`, `desativado`.

| De | Para | Quem e como | Efeitos |
| --- | --- | --- | --- |
| (novo) | `pendente` | Administração, `POST /condominios` | Evento `enviado` em `condominio_analises`; vínculo `administracao` do criador; auditoria `condominio.enviar` |
| `pendente` | `ativo` | ADM, `aprovacao` | Uma chave por unidade; e-mail `condominio_aprovado`; evento `aprovado`; auditoria `condominio.aprovar` |
| `pendente` | `rejeitado` | ADM, `rejeicao` com `motivo` | Grava `motivo_rejeicao`; evento `rejeitado`; auditoria `condominio.rejeitar` |
| `rejeitado` | `pendente` | Administração, `reenvio` | Limpa `motivo_rejeicao` (o histórico fica em `condominio_analises`); evento `reenviado`; auditoria `condominio.reenviar` |
| `ativo` | `desativado` | ADM, `desativacao` | Evento `desativado`; auditoria `condominio.desativar` |
| `desativado` | `ativo` | ADM, `reativacao` | Evento `reativado`; auditoria `condominio.reativar` |

Qualquer outra transição retorna 409 (`reason: "transicao_invalida"`). Não existe rascunho: o assistente envia o prédio inteiro de uma vez e o condomínio nasce `pendente`.

**O que cada status permite** (R7, com uma precisão: `desativado` é só leitura):

| Rota | `pendente` / `rejeitado` | `ativo` | `desativado` |
| --- | --- | --- | --- |
| `GET /condominio`, `GET /condominios/meus`, `GET /auth/me` | Sim | Sim | Sim |
| `PUT /condominio`, edição da estrutura, `POST /condominio/documentos` | Sim (Administração) | Sim | 403 |
| `POST /condominio/reenvio` | Só `rejeitado` | — | — |
| Todas as demais (encomendas, reservas, vínculos, avisos...) | 403 | Conforme a matriz | 403 |

### 4.2 Cadastrar o prédio — o assistente envia tudo de uma vez (US-202, Must, Sprint 1)

`POST /condominios` — conta com `tipo_cadastro = 'administracao'`, sem `cid`. A mesma conta pode cadastrar vários prédios (cada chamada cria um condomínio).

O assistente do front pergunta nome, blocos, quantidade de andares, apartamentos por andar e o nome de cada apartamento, e mostra a árvore para conferência (**tudo isso é do front**). O que chega à API é a **árvore explícita**, sem "quantidades": o front expande 3 andares × 4 apartamentos nos 12 nomes. Um único pedido, validado e gravado **numa transação só**: ou entra tudo, ou nada.

```json
{
  "nome": "Residencial Aurora",
  "cnpj": "12345678000199",
  "endereco": {"cep": "50030230", "logradouro": "Rua da Aurora", "numero": "100", "complemento": null,
               "bairro": "Boa Vista", "cidade": "Recife", "uf": "PE"},
  "logo_arquivo_id": null,
  "documentos": ["UUID"],
  "blocos": [
    {
      "nome": "Bloco A",
      "andares": [
        {"nome": "1º andar", "ordem": 1, "unidades": ["101", "102", "103"]},
        {"nome": "2º andar", "ordem": 2, "unidades": ["201", "202", "203"]}
      ]
    }
  ]
}
```

| Campo | Regra |
| --- | --- |
| `nome` | 3 a 120 caracteres |
| `cnpj` | 14 dígitos, dígitos verificadores válidos, único (regra 6 do DER) |
| `endereco` | `cep` (8 dígitos), `logradouro`, `numero`, `bairro`, `cidade` e `uf` (2 letras) obrigatórios; `complemento` opcional |
| `logo_arquivo_id`, `documentos` | Opcionais; IDs da TASK-26 (ata ou contrato entram em `documentos`, até 5) |
| `blocos[].nome` | 1 a 50 caracteres, único no condomínio |
| `andares[].nome` / `ordem` | 1 a 50 caracteres, único no bloco; `ordem` de 0 (térreo) a 200 |
| `unidades[]` | 1 a 20 caracteres (letras, dígitos, espaço, `-`, `/`), único no andar. Numeração não sequencial é aceita ("101" pode repetir em blocos diferentes) |
| Tamanho | Pelo menos 1 bloco, 1 andar e 1 unidade. Limites propostos: 20 blocos, 100 andares por bloco, 60 unidades por andar e 2000 unidades no total, para proteger a transação |

Resposta 201, com o cabeçalho `Location: /api/v1/condominios/meus` (ver nota):

```json
{"id": "UUID", "nome": "Residencial Aurora", "cnpj": "12345678000199", "status": "pendente",
 "enviado_em": "2026-11-10T14:03:00Z", "estrutura": {"blocos": 1, "andares": 2, "unidades": 6}}
```

Nota: como o recurso do dia a dia é `GET /condominio` (singular, do token), a resposta traz o `id` e o `Location` aponta para `/api/v1/condominios/meus`; para trabalhar nesse prédio, o front chama `POST /auth/selecionar-condominio`.

Erros do assistente: 422 com `error.details` apontando o campo (`blocos[0].andares[1].unidades[2]`, [convencoes.md](convencoes.md) seção 4); 409 `conflict` com `reason = "cnpj_ja_cadastrado"`. **Efeitos na mesma transação:** `condominios` (`pendente`, `enviado_em`, `criado_por_usuario_id`), `blocos`, `andares`, `unidades` (todas `ativo`), `condominio_documentos`, um `vinculos_condominio` ativo de perfil `administracao` para o criador, o evento `enviado` e a auditoria `condominio.enviar`. **Não gera chaves de acesso**: isso é na aprovação (US-203).

### 4.3 Dados do condomínio e histórico (US-204, US-206)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /condominios/meus` | Administração (sem `cid`) | — | 200, lista `{id, nome, status, perfil}` dos prédios com vínculo ativo, para "alternar entre prédios" |
| `GET /condominio` | Morador e Funcionário: só `id` e `nome`. Administração: completo | — | 200, objeto |
| `PUT /condominio` | Administração | `nome`, `cnpj`, `endereco`, `logo_arquivo_id` | 200, objeto |
| `POST /condominio/reenvio` | Administração | `{}` | 200, objeto com `status = 'pendente'` |
| `GET /condominio/documentos` | Administração | — | 200, lista de documentos |
| `POST /condominio/documentos` | Administração | `{"arquivo_id": "UUID"}` | 201, documento |

`GET /condominio` para a Administração:

```json
{
  "id": "UUID", "nome": "Residencial Aurora", "cnpj": "12345678000199", "status": "rejeitado",
  "endereco": {"cep": "50030230", "logradouro": "Rua da Aurora", "numero": "100", "complemento": null,
               "bairro": "Boa Vista", "cidade": "Recife", "uf": "PE"},
  "logo_arquivo_id": null,
  "motivo_rejeicao": "Documento ilegível. Envie a ata novamente.",
  "analises": [
    {"evento": "enviado", "motivo": null, "em": "2026-11-10T14:03:00Z"},
    {"evento": "rejeitado", "motivo": "Documento ilegível. Envie a ata novamente.", "em": "2026-11-11T09:30:00Z"}
  ]
}
```

- `motivo_rejeicao` só aparece em `rejeitado`; **a Administração consegue lê-lo** (US-203) e o painel o exibe (US-204). `analises` é o histórico de tentativas (US-204), em ordem cronológica.
- `PUT /condominio`: nome, CNPJ, endereço e logo editáveis; o CNPJ continua **único** (409 `cnpj_ja_cadastrado`). Mudar o CNPJ de um condomínio `ativo` gera auditoria `condominio.editar` com `antes`/`depois`.
- `reenvio`: só de `rejeitado` (senão 409). O motivo anterior fica no histórico. Dados e estrutura **continuam editáveis** antes do reenvio, pelo `PUT` e pelas rotas de estrutura.
- `GET /condominios/meus` mostra apenas os prédios do **próprio** vínculo. "Alternar" é chamar `selecionar-condominio` de novo (US-206: "tudo o que aparece pertence ao prédio escolhido").
- Documento anexado nunca é apagado do condomínio no MVP; só se acrescenta.

### 4.4 Ler a estrutura

`GET /condominio/estrutura` devolve a árvore Bloco → Andar → Unidade do condomínio do token. Administração vê tudo; Funcionário vê só nomes e identificação; Morador **não usa** esta rota (usa `/minhas-unidades`).

```json
{
  "blocos": [
    {"id": "UUID", "nome": "Bloco A", "ativo": true, "andares": [
      {"id": "UUID", "nome": "1º andar", "ordem": 1, "ativo": true, "unidades": [
        {"id": "UUID", "identificacao": "101", "ativo": true}
      ]}
    ]}
  ]
}
```

Para a Administração, cada unidade traz também `tem_proprietario` e `moradores_ativos`. Por padrão só aparecem itens ativos; `?incluir_inativos=true` mostra os desativados. A **edição** (renomear, adicionar, desativar) está em [plataforma.md](plataforma.md) seção 7.

## 5. Aprovação pelo ADM (US-203, Must, Sprint 1) e gestão de condomínios ativos (US-208)

Rotas sob `/plataforma/...`, só para `administrador_plataforma` (R9). O ADM **não** vê o dia a dia de nenhum condomínio (R8).

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /plataforma/condominios` | ADM | `status` (padrão `pendente`), `busca` (nome ou CNPJ), paginação | 200, fila |
| `GET /plataforma/condominios/{id}` | ADM | — | 200, detalhe com estrutura e documentos |
| `POST /plataforma/condominios/{id}/aprovacao` | ADM | `{}` | 200, objeto `ativo` |
| `POST /plataforma/condominios/{id}/rejeicao` | ADM | `{"motivo": "..."}` | 200, objeto `rejeitado` |
| `PUT /plataforma/condominios/{id}` | ADM (US-208, Could, Sprint 3) | `nome`, `cnpj`, `endereco`, `logo_arquivo_id` | 200, objeto |
| `POST /plataforma/condominios/{id}/desativacao` | ADM (US-208) | `{"motivo": "..."}` | 200, objeto `desativado` |
| `POST /plataforma/condominios/{id}/reativacao` | ADM (US-208) | `{}` | 200, objeto `ativo` |

Item da fila (a US-203 pede "CNPJ, documentos anexados e data de envio"):

```json
{
  "id": "UUID", "nome": "Residencial Aurora", "cnpj": "12345678000199", "status": "pendente",
  "enviado_em": "2026-11-10T14:03:00Z",
  "administracao": {"nome": "Condomínio Aurora Gestão Ltda", "email": "sindico@exemplo.com"},
  "documentos": [{"arquivo_id": "UUID", "nome_original": "ata-eleicao.pdf"}],
  "estrutura": {"blocos": 2, "andares": 10, "unidades": 38},
  "possivel_duplicidade": [{"id": "UUID", "nome": "Residencial Aurora II", "status": "ativo"}]
}
```

A fila vem do **mais antigo para o mais recente** (`enviado_em` crescente), para ninguém esperar sem fim. `possivel_duplicidade` lista condomínios que parecem o mesmo (heurística da pendência sobre CNPJ).

**Aprovar** (`pendente` → `ativo`), numa transação: muda o status e grava `aprovado_em`; **gera uma chave de acesso para cada unidade ativa** (seção 6.2); registra o evento `aprovado` em `condominio_analises`; enfileira o e-mail `condominio_aprovado` para a conta que enviou o cadastro ([plataforma.md](plataforma.md) seção 6); gera **um** evento `condominio.aprovar`, com `depois = {"status": "ativo", "chaves_geradas": N}`, sem os códigos. Se qualquer passo falhar, nada é gravado.

**Rejeitar** exige `motivo` de 1 a 500 caracteres (US-203: "rejeitar exige um motivo, que a Administração consegue ler"). Não envia e-mail (não está entre os eventos do US-803). Auditoria `condominio.rejeitar`.

**Desativar** e **reativar** são do US-208 (Could); o efeito é imediato porque o estado do condomínio é lido do banco a cada requisição (R6): a partir da desativação, todas as rotas de dia a dia do condomínio respondem 403.

Aprovar ou rejeitar algo que não esteja `pendente` retorna 409. O ADM é uma conta individual, por isso estas rotas **não recebem `responsavel_id`**: a auditoria já registra quem agiu. Para o ADM abrir os **documentos** do cadastro, a leitura de arquivos da TASK-26 precisa liberar o ADM nos arquivos de `condominio_documentos`, exceção estreita à R8 (pendências).

## 6. Proprietário e chaves de acesso (US-207, Must, Sprint 1)

### 6.1 Unidades e proprietário (Administração)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /unidades` | Administração | `bloco_id`, `andar_id`, `busca`, `sem_proprietario`, `ativo`, paginação | 200, lista |
| `GET /unidades/{id}` | Administração | — | 200, detalhe com proprietário, chave vigente e moradores |
| `PUT /unidades/{id}/proprietario` | Administração | JSON abaixo | 200, proprietário |

```json
{
  "nome": "Maria Souza",
  "documento": "12345678909",
  "emails": ["maria@exemplo.com", "maria.trabalho@exemplo.com"],
  "whatsapps": ["81988887777"],
  "telefone": "8133334444",
  "foto_arquivo_id": null
}
```

`nome` e `documento` (CPF ou CNPJ, dígitos validados) obrigatórios. `emails` e `whatsapps` com até 2 itens cada (a spec tem "e-mail, e-mail 2, WhatsApp, WhatsApp 2"); e-mails em minúsculas; `telefone` e WhatsApps só com dígitos. Um proprietário por unidade (`UNIQUE (unidade_id)`), então `PUT` cria ou substitui. O WhatsApp é **apenas dado de contato**: o sistema não envia mensagens por WhatsApp (fora do MVP). Auditoria `proprietario.editar`, com o documento mascarado.

`GET /unidades/{id}`:

```json
{
  "id": "UUID", "identificacao": "101", "bloco": "Bloco A", "andar": "1º andar", "ativo": true,
  "proprietario": {"nome": "Maria Souza", "documento": "12345678909", "emails": ["..."], "whatsapps": ["..."], "telefone": "...", "foto_arquivo_id": null},
  "chave": {"codigo": "K7M2P-9QXW4", "criada_em": "2026-11-12T10:00:00Z"},
  "moradores": [{"id": "UUID", "nome": "Ana Martins", "parentesco": "Filha", "status": "ativo", "vinculado_em": "2026-11-13T08:00:00Z"}]
}
```

`chave` é `null` se não há chave vigente. **O código da chave só aparece para a Administração**, nunca para o Morador (matriz: "nunca devolvida a ele").

### 6.2 Chaves de acesso

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /unidades/{id}/chave` | Administração | — | 200, `{"codigo", "criada_em"}`; 404 se não há chave vigente |
| `POST /unidades/{id}/chave` | Administração | `{}` | 201, chave nova; 409 se já há uma vigente |
| `POST /unidades/{id}/chave/regeneracao` | Administração | `{}` | 200, chave nova; a anterior fica **inválida na hora** |
| `POST /unidades/{id}/chave/revogacao` | Administração | `{}` | 200, `{"revogada_em": "..."}`; a unidade fica sem chave |

Regras:

- **Formato:** 10 caracteres de um alfabeto de 32 símbolos sem ambiguidade (sem `0 O 1 I L`), gerado com `secrets` e exibido em dois grupos (`K7M2P-9QXW4`). São 50 bits, suficientes porque o limite de tentativas (seção 7.1) impede força bruta. Na entrada, o servidor ignora hífen, espaço e caixa.
- **Unicidade:** `UNIQUE (codigo)` (regra 4 do DER). Se o sorteio colidir, sorteia de novo; o service tenta até 5 vezes.
- **Uma vigente por unidade** (regra 5): `UNIQUE (unidade_id) WHERE revogada_em IS NULL`. Regenerar grava `revogada_em` na anterior e cria a nova **na mesma transação**, e a anterior para de valer imediatamente (US-207).
- Unidade desativada não tem chave (a desativação revoga a vigente, [plataforma.md](plataforma.md) seção 7).
- Auditoria: `chave.gerar`, `chave.regenerar`, `chave.revogar`, **sem o código** em `antes`/`depois` (só o ID da chave).
- Vincular com chave já usada por outro morador **não** invalida a chave: a mesma chave serve a todos os moradores da unidade até a Administração regenerá-la (US-305, "a Administração pode regenerar a chave em seguida").

## 7. Vínculo do morador com a unidade

### 7.1 Vincular-se com a chave (US-301, Must, Sprint 1)

`POST /vinculos/chave` — conta autenticada, sem `cid` exigido.

```json
{"chave": "K7M2P-9QXW4"}
```

O servidor procura a chave **vigente** (`revogada_em IS NULL`); a unidade e o condomínio saem dela. Se a chave é válida e o condomínio está `ativo`, numa transação:

1. Cria (se ainda não houver) o `vinculos_condominio` de perfil `morador` entre a conta e o condomínio.
2. Cria `moradores_unidade` com `status = 'ativo'` e `origem = 'chave'`.
3. Cria as **7 linhas de `permissoes_aba`** (a criação delas é papel do service, DER regra 20). Valores iniciais: ver seção 8.
4. Zera o contador de tentativas erradas.

Resposta 201: `{"unidade": {"id": "UUID", "identificacao": "Bloco A / 101"}, "condominio": {"id": "UUID", "nome": "Residencial Aurora"}}`. **Não devolve token**: a conta chama `selecionar-condominio` em seguida para passar a atuar nesse condomínio (um único passo de código, sem caso especial para quem já tinha outro `cid`).

| Situação | Resposta |
| --- | --- |
| Chave inexistente, **regenerada/revogada** ou de condomínio não `ativo` | 404 `not_found`, mensagem única: "Chave de acesso inválida ou já substituída. Peça uma nova à Administração." Conta como tentativa errada |
| Já vinculado a essa unidade | 409 `conflict`, `reason: "ja_vinculado"` |
| Excedeu as tentativas | **429 `too_many_attempts`**, com `Retry-After` |
| Formato inválido (menos de 10 caracteres úteis) | 422 |

**Limite de tentativas** (proposta): cada tentativa grava uma linha em `tentativas_chave_acesso` (`usuario_id`, `sucesso`, `criado_em`). **5 tentativas erradas seguidas em 15 minutos** bloqueiam novas tentativas dessa conta por 15 minutos, contando a partir da última; um acerto zera a contagem. Uma tentativa bloqueada não consulta a chave. Cada erro gera `seguranca.chave_invalida` na auditoria.

Um morador pode se vincular a **mais de uma unidade** (US-301), do mesmo condomínio ou de outros. O vínculo dá acesso **só àquela unidade** (R10).

**Aprovação do vínculo.** A matriz fala em "solicitar", "aprovar" e "rejeitar" vínculo, mas a US-301 diz que a chave válida "vincula", e o DER só tem `ativo`/`desvinculado`. **Este contrato adota o vínculo imediato**: a chave é a autorização, e a Administração corrige depois por desvinculação. Se o grupo preferir aprovação, `moradores_unidade.status` ganha `pendente` e entra a rota de aprovação (pendências).

### 7.2 Minhas unidades e o proprietário (US-302, Must, Sprint 1)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /minhas-unidades` | Morador `[Unidades]` | paginação | 200, lista das unidades com a aba `unidades` habilitada |
| `GET /minhas-unidades/{unidade_id}` | Morador `[Unidades]` | — | 200, unidade com proprietário |

```json
{
  "id": "UUID", "identificacao": "Bloco A / 101", "condominio": {"id": "UUID", "nome": "Residencial Aurora"},
  "proprietario": {"nome": "Maria Souza", "emails": ["maria@exemplo.com"], "whatsapps": ["81988887777"], "telefone": "8133334444", "foto_arquivo_id": null}
}
```

- A lista inclui só as unidades **vinculadas e ativas** do Morador (404 nas outras) e só aquelas em que a aba `unidades` está habilitada para ele. As demais unidades continuam visíveis em `GET /auth/me`, que alimenta o seletor de unidade das outras telas.
- **O `documento` (CPF/CNPJ) do proprietário nunca vai para o Morador** (proposta; ver pendências). Nenhum dado do proprietário de outra unidade é devolvido.
- Sem unidade vinculada, a lista vem vazia (`items: []`), e é o front que mostra a orientação de usar a chave de acesso (US-302).

### 7.3 Convidar e cadastrar outros moradores (US-303, Should, Sprint 3)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `POST /unidades/{unidade_id}/convites` | Morador `[Usuários]` | `{"email", "parentesco", "permissoes_iniciais": {"visitantes": true, "...": false}}` | 201, convite |
| `POST /convites/aceitar` | Conta autenticada | `{"token": "..."}` | 201, vínculo (mesmo formato de 7.1) |

O convite vai por e-mail com um token de uso único e validade (`convites_morador`, DER). Aceitar cria o vínculo e as 7 permissões iniciais a partir de `permissoes_iniciais`, que o convidador define na criação e pode alterar depois (seção 8). `parentesco` é o grau com o proprietário. O e-mail do convite ainda não está na lista de eventos do US-803 (pendências).

### 7.4 Desvincular (US-305, Should, Sprint 3)

`POST /unidades/{unidade_id}/moradores/{morador_unidade_id}/desvinculacao` — Administração, ou Morador com `[Usuários]` na mesma unidade. Corpo da Administração: `{"responsavel_id": "UUID"}`.

- Marca `status = 'desvinculado'`, `desvinculado_em` e `desvinculado_por_usuario_id`. O que o morador **já registrou** continua na unidade (encomendas, reservas, ocorrências ficam ligados à unidade).
- Se era o último vínculo ativo da conta no condomínio, o `vinculos_condominio` também fica `ativo = false`. O acesso cai **na hora** (R6).
- O Morador **não pode desvincular a si mesmo** (proposta; sair da unidade não é um caso das stories).
- Auditoria `vinculo.desfazer`. Depois, a Administração pode regenerar a chave (seção 6.2).

## 8. Permissões por aba (US-304, Must, Sprint 1; Gabriel)

Referência para o front. A regra completa está na seção 8 da matriz. As abas são `unidades`, `visitantes`, `veiculos`, `reservas`, `encomendas`, `ocorrencias` e `usuarios`.

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /unidades/{unidade_id}/moradores` | Morador `[Usuários]`, Administração | paginação | 200, moradores da unidade com permissões |
| `PUT /unidades/{unidade_id}/moradores/{morador_unidade_id}/permissoes` | Morador `[Usuários]` | `{"abas": {"visitantes": true, "veiculos": false, "...": true}}` | 200, permissões |

- O corpo traz as **7 abas** (aceita um subconjunto, que altera só as informadas). `true` é Com Acesso e `false` é Sem Acesso. A Administração **não** altera permissões (matriz).
- **Trava:** retirar `usuarios` de quem é o último a tê-la na unidade retorna 409 (`reason: "ultimo_usuarios"`).
- A mudança vale na **requisição seguinte** (R6) e gera `permissao_aba.alterar` (quem mudou, para quem, de quê para quê).
- **Permissões iniciais** (proposta da matriz, a confirmar com o Paulo): o primeiro morador da unidade nasce com tudo; os seguintes, com tudo **menos** `usuarios`.

## 9. Casos obrigatórios de teste

- **Contas:** e-mail e telefone duplicados retornam 409; senha fraca retorna 422; documento com dígito verificador errado retorna 422; a senha nunca aparece em resposta nem em log; a resposta do cadastro autentica a conta.
- **Login:** mensagem igual para e-mail inexistente e senha errada; conta inativa não entra; `selecionar-condominio` com condomínio sem vínculo retorna 404; Administração entra em condomínio `pendente`, morador não.
- **Assistente:** árvore inválida em qualquer ponto não grava **nada** (inclusive `condominios`); nome duplicado no andar retorna 422 com `details` apontando o campo; CNPJ duplicado retorna 409; o vínculo `administracao` do criador é criado; nenhuma chave é gerada antes da aprovação.
- **Estados:** todas as transições da seção 4.1 passam e **todas as outras** retornam 409; `pendente`, `rejeitado` e `desativado` recebem 403 nas rotas de dia a dia; a Administração lê o `motivo_rejeicao`; `reenvio` limpa o motivo e mantém o histórico.
- **Aprovação:** gera exatamente uma chave por unidade ativa, todas únicas; falha no meio desfaz tudo; enfileira o e-mail `condominio_aprovado`; ADM não acessa encomendas, visitantes, ocorrências, reservas nem avisos de condomínio algum (matriz, seção 11, item 8).
- **Chaves:** regenerar invalida a anterior na hora (a anterior retorna 404 no vínculo); o código nunca aparece em resposta ao Morador, nem em `antes`/`depois` da auditoria; duas gerações simultâneas para a mesma unidade resultam em **uma** chave vigente.
- **Vínculo:** 5 erros seguidos retornam 429 e a quinta tentativa certa dentro do bloqueio também é recusada; vincular a duas unidades funciona; vincular duas vezes à mesma retorna 409; chave de condomínio `desativado` retorna 404; as 7 permissões são criadas.
- **Desvínculo:** o acesso cai na requisição seguinte com o mesmo token; o histórico da unidade permanece; o morador não desvincula a si mesmo.
- **Permissões:** retirar `usuarios` do último retorna 409; mudança vale na requisição seguinte; Administração recebe 403 ao alterar permissões.
- **Isolamento:** a Administração do condomínio A não lê nem edita unidade, chave, proprietário ou fila do condomínio B (404); o Morador de uma unidade recebe 404 na unidade vizinha.

## 10. Pendências e responsáveis

| Tema | Decisão ou alinhamento necessário | Quem |
| --- | --- | --- |
| `usuarios.tipo_cadastro` | Coluna existente e preenchida pelos cadastros de morador/Administração (TASK-31). O futuro `POST /condominios` deve exigir `administracao`. | Davi e Paulo |
| CNPJ duplicado | A regra 6 do DER é `UNIQUE (cnpj)` total, mas a US-203 pede que o CNPJ já cadastrado seja "sinalizado como possível duplicidade" na fila. Com o `UNIQUE`, o segundo cadastro nem chega à fila. **Proposta:** manter o `UNIQUE` (409 no cadastro) e fazer `possivel_duplicidade` apontar para condomínios de **mesmo nome e cidade** ou **mesmo CEP e número**, sinalizando o caso de CNPJ digitado errado. Confirmar. | Paulo, Gabriel e Davi |
| Vínculo imediato × aprovado | A matriz e o DER (seção 7) preveem solicitar/aprovar; a US-301 vincula direto. Este contrato adota o imediato. | Paulo e Gabriel |
| Dados do proprietário para o Morador | A US-302 mostra o proprietário ao Morador, mas a decisão 5 do DER diz que são dados que só a Administração vê. **Proposta:** o Morador vê nome, foto, e-mails, WhatsApps e telefone, **sem o documento**. LGPD (US-1007). | Paulo e Gabriel |
| Permissões iniciais | Confirmar o padrão (primeiro morador com tudo, demais sem `usuarios`) | Paulo |
| Onboarding por convite do ADM | A especificação (4.4) cita um modelo B2B com status `convidado`, mas o DER e a TASK-78 têm só 4 status. **Proposta:** só autocadastro com aprovação no MVP. | Paulo |
| Primeiro ADM | O ADM não se autocadastra e o `administrador_plataforma` não tem rota. **Proposta:** script de linha de comando (`python -m app.cli criar-adm`), que também cria os dados de exemplo do ambiente de desenvolvimento. | Gabriel e Davi |
| Refresh token | Implementado na TASK-80/PR #11: access de 15 minutos e refresh de 7 dias, sem rotação. Revisar rotação ou revogação individual somente se o escopo exigir. | Gabriel |
| Limite de tentativas de login | Implementado na TASK-80/PR #11: padrão de 5 falhas, 15 minutos de bloqueio e 429; contador em memória de uma instância. | Gabriel |
| Rotas sem `cid` e fluxo de cadastro | A dependência de autorização precisa das variantes de [convencoes.md](convencoes.md) seção 2 e de liberar `pendente` e `rejeitado` | Gabriel |
| Leitura de documentos pelo ADM | A TASK-26 precisa liberar o ADM nos arquivos de `condominio_documentos` | Eduardo e Gabriel |
| Foto e documento no cadastro | Upload exige autenticação; foto da conta entra por `PUT /contas/me`, documento comprobatório no cadastro do prédio | Eduardo e Paulo |
| E-mail de convite | `convite_morador` não está entre os eventos do US-803 | Tude e Paulo |
| Limites do assistente | 20 blocos, 100 andares por bloco, 60 unidades por andar, 2000 no total; confirmar | Paulo e Guilherme |
| Formato das respostas | O front (Guilherme e Matheus) revisa nomes de campos e o formato dos erros com `details` | Guilherme e Matheus |

Nenhuma revisão do Gabriel, do front ou dos leads foi presumida. O "pronto quando" da TASK-78 é o contrato revisado pelo Gabriel e pelo front e presente no repositório.
