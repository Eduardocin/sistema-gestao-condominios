# Modelo de dados (DER lógico)

Status: **v1 para revisão no portão dos leads** (TASK-3, US-1006). Base para a TASK-81 (migrations, constraints e índices).

Fontes: as 52 user stories do Notion, a [matriz de permissões](permissoes-e-multitenant.md) (em especial a seção 12), o [ADR 0002](decisions/0002-isolamento-condominios.md) e a migração `20261015_0001`. Onde este documento muda o que a 0001 criou, isso está na [seção 5](#5-o-que-muda-em-relação-à-migração-0001).

Os diagramas estão em Mermaid: o GitHub os desenha direto nesta página, e o texto é a fonte que se edita.

## 1. Convenções

- Tabelas e colunas em português, `snake_case`, tabelas no plural (como já está no repositório).
- `id uuid` gerado pela aplicação em toda tabela. `criado_em timestamptz default now()` onde a data importa. **Datas de registro não são editáveis**: a aplicação não expõe esses campos para escrita.
- **`condominio_id` obrigatório em toda tabela de negócio**, com FK para `condominios` e índice (R2 da matriz). As únicas exceções são o que pertence à conta ou à plataforma, e não a um condomínio: `usuarios`, `tokens_recuperacao_senha`, `tentativas_chave_acesso` e `comunicados`. Em `registros_auditoria`, `envios_email` e `arquivos` o `condominio_id` existe, mas pode ser nulo quando o registro é da plataforma ou da conta.
- Tabela que aponta para unidade (ou para outro registro do condomínio) usa **FK composta** `(x_id, condominio_id)`, como `vinculos_condominio` já faz. Assim o banco recusa uma unidade de outro condomínio. Para isso, cada tabela referenciada tem `UNIQUE (id, condominio_id)`.
- Status e enums são `varchar` com `CHECK` (padrão da 0001), não tipos `ENUM` do PostgreSQL, porque são mais fáceis de alterar numa migração.
- Nada é apagado de verdade: registros são **desativados** (`ativo = false`, `desativado_em`) ou mudam de status. FKs usam `ON DELETE RESTRICT`.
- Arquivos (fotos, anexos, documentos) ficam no storage. O banco guarda só os metadados em `arquivos` (US-1003).
- CPF, CNPJ, telefone e placa são guardados **só com dígitos/letras, sem máscara**. A máscara é coisa da tela (US-1007).

## 2. Visão geral

| Domínio | Tabelas | Dono do módulo |
| --- | --- | --- |
| Contas e acesso | `usuarios`, `tokens_recuperacao_senha`, `tentativas_chave_acesso` | Gabriel |
| Condomínio e cadastro | `condominios`, `condominio_analises`, `condominio_documentos` | Paulo |
| Estrutura | `blocos`, `andares`, `unidades`, `proprietarios_unidade`, `chaves_acesso` | Paulo / Tude (edição) |
| Vínculos e permissões | `vinculos_condominio`, `moradores_unidade`, `permissoes_aba`, `convites_morador` | Paulo / Gabriel |
| Pessoas sem login | `funcionarios`, `responsaveis_administracao` | Tude |
| Portaria | `encomendas`, `visitantes`, `registros_visita`, `veiculos` | Eduardo / Vitor |
| Convivência | `areas_comuns`, `bloqueios_area`, `reservas`, `ocorrencias`, `ocorrencia_interacoes`, `ocorrencia_anexos`, `avisos` | Vitor / Tude |
| Plataforma | `comunicados`, `chamados`, `chamado_mensagens`, `chamado_anexos`, `registros_auditoria`, `envios_email` | Tude |
| Transversal | `arquivos` | Eduardo |

São 35 tabelas: as 4 da 0001 continuam (com mudanças, seção 5) e 31 são novas.

## 3. Diagramas

Para não poluir os diagramas, `criado_em` só aparece onde tem regra própria, e as FKs para `arquivos` aparecem só como coluna.

### 3.1 Contas, condomínio e estrutura

```mermaid
erDiagram
    usuarios ||--o{ vinculos_condominio : "tem"
    condominios ||--o{ vinculos_condominio : "tem"
    condominios ||--o{ condominio_analises : "histórico"
    condominios ||--o{ condominio_documentos : "anexa"
    condominios ||--o{ blocos : "tem"
    blocos ||--o{ andares : "tem"
    andares ||--o{ unidades : "tem"
    unidades ||--o| proprietarios_unidade : "tem"
    unidades ||--o{ chaves_acesso : "gera"
    usuarios ||--o{ tokens_recuperacao_senha : "pede"

    usuarios {
        uuid id PK
        varchar nome
        varchar email UK "minúsculas"
        varchar telefone UK "só dígitos, opcional"
        varchar cpf UK "11 dígitos, obrigatório em novos cadastros"
        varchar status_conta "pendente, ativo, rejeitado, suspenso"
        varchar senha_hash "argon2 ou bcrypt"
        int sessao_versao "claim sv do token"
        uuid foto_arquivo_id FK
        bool administrador_plataforma
        bool ativo
        timestamptz email_confirmado_em
        timestamptz consentimento_dados_em "US-1007"
    }
    tokens_recuperacao_senha {
        uuid id PK
        uuid usuario_id FK
        varchar token_hash UK
        timestamptz expira_em
        timestamptz usado_em "uso único"
    }
    condominios {
        uuid id PK
        varchar nome
        varchar cnpj UK "14 dígitos"
        varchar status "pendente, ativo, rejeitado, desativado"
        varchar motivo_rejeicao
        varchar cep
        varchar logradouro
        varchar numero
        varchar complemento
        varchar bairro
        varchar cidade
        char uf
        uuid logo_arquivo_id FK
        uuid criado_por_usuario_id FK
        timestamptz enviado_em
        timestamptz aprovado_em
    }
    condominio_analises {
        uuid id PK
        uuid condominio_id FK
        varchar evento "enviado, reenviado, aprovado, rejeitado, desativado, reativado"
        varchar motivo
        uuid usuario_id FK "quem agiu"
        timestamptz criado_em
    }
    condominio_documentos {
        uuid condominio_id PK
        uuid arquivo_id PK
    }
    blocos {
        uuid id PK
        uuid condominio_id FK
        varchar nome "UK por condomínio"
        bool ativo
    }
    andares {
        uuid id PK
        uuid condominio_id FK
        uuid bloco_id FK
        varchar nome "UK por bloco"
        smallint ordem
        bool ativo
    }
    unidades {
        uuid id PK
        uuid condominio_id FK
        uuid andar_id FK
        varchar identificacao "UK por andar"
        bool ativo
    }
    proprietarios_unidade {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK "UK, 1 por unidade"
        varchar nome
        varchar documento "CPF ou CNPJ"
        text_array emails
        text_array whatsapps
        varchar telefone
        uuid foto_arquivo_id FK
    }
    chaves_acesso {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        varchar codigo UK
        timestamptz criada_em
        timestamptz revogada_em "null = vigente"
    }
```

### 3.2 Vínculos, permissões e pessoas sem login

```mermaid
erDiagram
    usuarios ||--o{ vinculos_condominio : "tem"
    usuarios ||--o{ moradores_unidade : "morador em"
    unidades ||--o{ moradores_unidade : "tem"
    usuarios ||--o{ solicitacoes_vinculo_unidade : "solicita"
    unidades ||--o{ solicitacoes_vinculo_unidade : "recebe"
    moradores_unidade ||--|{ permissoes_aba : "7 abas"
    unidades ||--o{ convites_morador : "convida"
    usuarios ||--o{ tentativas_chave_acesso : "tenta"
    condominios ||--o{ funcionarios : "lista"
    condominios ||--o{ responsaveis_administracao : "lista"

    vinculos_condominio {
        uuid id PK
        uuid usuario_id FK
        uuid condominio_id FK
        varchar perfil "administracao, funcionario, morador"
        bool ativo
    }
    moradores_unidade {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        uuid usuario_id FK
        varchar status "ativo, desvinculado"
        varchar origem "chave, convite, cadastro"
        varchar parentesco "com o proprietário"
        timestamptz vinculado_em
        timestamptz desvinculado_em
        uuid desvinculado_por_usuario_id FK
    }
    solicitacoes_vinculo_unidade {
        uuid id PK
        uuid usuario_id FK
        uuid condominio_id FK
        uuid unidade_id FK
        varchar status "pendente, aprovado, rejeitado"
        bool responsavel_principal
        varchar motivo_rejeicao
        timestamptz solicitado_em
        timestamptz decidido_em
        uuid decidido_por_usuario_id FK
    }
    permissoes_aba {
        uuid morador_unidade_id PK
        uuid condominio_id FK
        varchar aba PK "unidades, visitantes, veiculos, reservas, encomendas, ocorrencias, usuarios"
        bool com_acesso
        uuid alterado_por_usuario_id FK
        timestamptz alterado_em
    }
    convites_morador {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        varchar email
        varchar parentesco
        jsonb permissoes_iniciais
        varchar token_hash UK
        uuid convidado_por_usuario_id FK
        timestamptz expira_em
        timestamptz aceito_em
    }
    tentativas_chave_acesso {
        uuid id PK
        uuid usuario_id FK
        bool sucesso
        timestamptz criado_em
    }
    funcionarios {
        uuid id PK
        uuid condominio_id FK
        varchar nome
        varchar funcao "porteiro, seguranca"
        varchar telefone
        varchar email
        uuid foto_arquivo_id FK
        bool ativo "desligado some da lista"
        timestamptz desligado_em
    }
    responsaveis_administracao {
        uuid id PK
        uuid condominio_id FK
        varchar nome
        bool ativo
    }
```

### 3.3 Portaria

```mermaid
erDiagram
    unidades ||--o{ encomendas : "recebe"
    funcionarios ||--o{ encomendas : "recebeu"
    unidades ||--o{ visitantes : "espera"
    visitantes ||--o{ registros_visita : "entra e sai"
    unidades ||--o{ veiculos : "tem"

    encomendas {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        uuid destinatario_morador_unidade_id FK
        varchar descricao
        uuid foto_nota_arquivo_id FK "obrigatória"
        uuid recebido_por_funcionario_id FK
        varchar status "aguardando_retirada, entregue_aguardando_confirmacao, retirada_confirmada"
        timestamptz registrada_em
        timestamptz entregue_em
        uuid recebedor_morador_unidade_id FK
        uuid entregue_por_funcionario_id FK
        timestamptz confirmada_em
        uuid confirmado_por_usuario_id FK
    }
    visitantes {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        varchar nome
        varchar cpf "opcional, só dígitos"
        smallint idade
        varchar observacoes
        date entrada_prevista
        date saida_prevista
        bool avulso "cadastrado na portaria"
        uuid cadastrado_por_usuario_id FK
        timestamptz cancelado_em
    }
    registros_visita {
        uuid id PK
        uuid condominio_id FK
        uuid visitante_id FK
        timestamptz entrada_em
        timestamptz saida_em "null = ainda dentro"
        uuid entrada_por_funcionario_id FK
        uuid saida_por_funcionario_id FK
    }
    veiculos {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        varchar placa "maiúsculas, sem hífen"
        varchar marca
        varchar modelo
        varchar cor
        bool ativo
        timestamptz removido_em
    }
```

### 3.4 Convivência

```mermaid
erDiagram
    areas_comuns ||--o{ reservas : "tem"
    areas_comuns ||--o{ bloqueios_area : "tem"
    unidades ||--o{ reservas : "faz"
    unidades ||--o{ ocorrencias : "abre"
    ocorrencias ||--o{ ocorrencia_interacoes : "histórico"
    ocorrencias ||--o{ ocorrencia_anexos : "anexa"
    condominios ||--o{ avisos : "publica"

    areas_comuns {
        uuid id PK
        uuid condominio_id FK
        varchar nome
        uuid foto_arquivo_id FK
        text regras
        time abre_as
        time fecha_as
        smallint capacidade
        bool ativa
    }
    bloqueios_area {
        uuid id PK
        uuid condominio_id FK
        uuid area_id FK
        date data_inicio
        date data_fim
        varchar motivo
        uuid responsavel_id FK
    }
    reservas {
        uuid id PK
        uuid condominio_id FK
        uuid area_id FK
        uuid unidade_id FK
        uuid usuario_id FK "morador que reservou"
        date data
        time hora_inicio "hora cheia, slot de 1h"
        varchar status "ativa, cancelada"
        timestamptz cancelada_em
        uuid cancelada_por_usuario_id FK
        uuid cancelada_responsavel_id FK "quando é a Administração"
        varchar motivo_cancelamento
    }
    ocorrencias {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK
        uuid aberta_por_usuario_id FK
        varchar titulo
        text detalhe
        varchar status "em_aberto, resolvida"
        timestamptz criado_em
        timestamptz resolvida_em
    }
    ocorrencia_interacoes {
        uuid id PK
        uuid condominio_id FK
        uuid ocorrencia_id FK
        varchar tipo "resposta, comentario, resolucao, reabertura"
        text texto
        uuid usuario_id FK
        uuid responsavel_id FK "quando é a Administração"
        timestamptz criado_em
    }
    ocorrencia_anexos {
        uuid ocorrencia_id PK
        uuid condominio_id FK
        uuid arquivo_id PK
        uuid interacao_id FK "null = anexo da abertura"
    }
    avisos {
        uuid id PK
        uuid condominio_id FK
        uuid unidade_id FK "null = para todos"
        varchar titulo
        text texto
        bool importante
        timestamptz inicio_em
        timestamptz fim_em
        timestamptz encerrado_em
        uuid responsavel_id FK
    }
```

### 3.5 Plataforma e transversais

```mermaid
erDiagram
    condominios ||--o{ chamados : "abre"
    chamados ||--o{ chamado_mensagens : "histórico"
    chamados ||--o{ chamado_anexos : "anexa"
    usuarios ||--o{ comunicados : "envia"
    condominios |o--o{ registros_auditoria : "escopo"
    condominios |o--o{ arquivos : "escopo"

    comunicados {
        uuid id PK
        varchar titulo
        text texto
        uuid enviado_por_usuario_id FK "ADM"
        timestamptz criado_em
    }
    chamados {
        uuid id PK
        uuid condominio_id FK
        varchar titulo
        text descricao
        varchar status "aberto, em_atendimento, encerrado"
        uuid aberto_por_usuario_id FK
        uuid atendido_por_usuario_id FK "ADM"
        timestamptz criado_em
        timestamptz encerrado_em
    }
    chamado_mensagens {
        uuid id PK
        uuid condominio_id FK
        uuid chamado_id FK
        uuid autor_usuario_id FK
        text texto
        timestamptz criado_em
    }
    chamado_anexos {
        uuid chamado_id PK
        uuid condominio_id FK
        uuid arquivo_id PK
    }
    registros_auditoria {
        bigint id PK "identity, ordem de inserção"
        uuid condominio_id FK "null = plataforma"
        uuid usuario_id FK "null = login falho"
        varchar responsavel_nome "contas compartilhadas"
        varchar perfil
        varchar acao "ex.: condominio.aprovar"
        varchar recurso_tipo
        uuid recurso_id
        jsonb antes
        jsonb depois
        inet ip
        timestamptz criado_em
    }
    envios_email {
        uuid id PK
        uuid condominio_id FK "opcional"
        varchar destinatario
        varchar evento "recuperacao_senha, condominio_aprovado, encomenda_registrada, reserva_cancelada"
        varchar status "pendente, enviado, falhou"
        smallint tentativas
        text ultimo_erro
        timestamptz criado_em
        timestamptz enviado_em
    }
    arquivos {
        uuid id PK
        uuid condominio_id FK "null = conta ou plataforma"
        varchar chave_storage UK "caminho no bucket"
        varchar nome_original
        varchar tipo_mime
        bigint tamanho_bytes
        uuid enviado_por_usuario_id FK
        timestamptz criado_em
    }
```

## 4. Regras garantidas pelo próprio banco

Estas são as restrições que a TASK-81 transforma em constraints. As marcadas com ★ são critério de aceite de alguma story.

| # | Regra | Como | Origem |
| --- | --- | --- | --- |
| 1 ★ | Uma reserva **ativa** por unidade, área e dia | `UNIQUE (unidade_id, area_id, data) WHERE status = 'ativa'` (índice parcial) | US-1006, US-603 |
| 2 ★ | Dois pedidos simultâneos para o mesmo horário gravam só um | `UNIQUE (area_id, data, hora_inicio) WHERE status = 'ativa'` | US-603 |
| 3 | Reserva em hora cheia | `CHECK (date_part('minute', hora_inicio) = 0 AND date_part('second', hora_inicio) = 0)` | US-603 |
| 4 ★ | Chave de acesso única | `UNIQUE (codigo)` em `chaves_acesso` | US-1006, US-207 |
| 5 | Só uma chave vigente por unidade | `UNIQUE (unidade_id) WHERE revogada_em IS NULL` | US-207 |
| 6 ★ | CNPJ único | `UNIQUE (cnpj)` em `condominios`; `UNIQUE (documento)` em `usuarios` | US-201, US-206 |
| 7 | Status do condomínio válido | `CHECK (status IN ('pendente','ativo','rejeitado','desativado'))` e `CHECK (status <> 'rejeitado' OR motivo_rejeicao IS NOT NULL)` | US-203 |
| 8 | Encomenda coerente | Três estados e ramos explícitos de completude; entrega e confirmação têm datas e responsáveis separados (SQL abaixo) | US-401, US-403; alinhamento TASK-12 |
| 9 | Ocorrência coerente | `CHECK (status IN ('em_aberto','resolvida'))` | US-701, US-703 |
| 10 | Saída só depois da entrada | `CHECK (saida_em IS NULL OR saida_em >= entrada_em)` em `registros_visita` | US-503 |
| 11 | Uma visita em aberto por visitante | `UNIQUE (visitante_id) WHERE saida_em IS NULL` | US-503 |
| 12 | Período do visitante válido | `CHECK (saida_prevista >= entrada_prevista)` | US-501 |
| 13 | Placa no formato brasileiro (antigo ou Mercosul) | `CHECK (placa ~ '^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$')` | US-502 |
| 14 | Placa não se repete na mesma unidade | `UNIQUE (unidade_id, placa) WHERE ativo`. Entre unidades **pode** repetir: a story pede só um aviso à Administração | US-502 |
| 15 | Bloqueio com intervalo válido | `CHECK (data_fim >= data_inicio)` | US-602 |
| 16 | Área com horário válido | `CHECK (fecha_as > abre_as)` e `CHECK (capacidade > 0)` | US-601 |
| 17 | Aviso com período válido | `CHECK (fim_em > inicio_em)` | US-801 |
| 18 | Estrutura sem nomes repetidos | `UNIQUE (condominio_id, nome)` em blocos, `UNIQUE (bloco_id, nome)` em andares, `UNIQUE (andar_id, identificacao)` em unidades | US-202, US-205 |
| 19 | Morador não se vincula duas vezes à mesma unidade | `UNIQUE (unidade_id, usuario_id) WHERE status = 'ativo'` | US-301 |
| 20 | Só as 7 abas válidas, uma linha por aba e morador | `CHECK (aba IN (...7 abas...))` e PK `(morador_unidade_id, aba)`. Criar as 7 linhas ao vincular é papel do service | US-304 |
| 21 ★ | Auditoria só aceita inserção | trigger `BEFORE UPDATE OR DELETE` que lança erro em `registros_auditoria` | US-1004, US-903 |
| 22 | Isolamento entre condomínios | FK composta `(x_id, condominio_id)` em toda referência a bloco, andar, unidade, morador da unidade, área, visitante, ocorrência, interação, chamado, funcionário e responsável | US-1001 |
| 23 | Token de recuperação e convite não se repetem | `UNIQUE (token_hash)`. O uso único (`usado_em`/`aceito_em` gravado uma vez) é garantido no service com `UPDATE ... WHERE usado_em IS NULL` | US-102, US-303 |

Regras que **não** dá para garantir no banco e ficam no service (com teste): limite de tentativas de chave (US-301, usa `tentativas_chave_acesso`), horário dentro do funcionamento da área e fora de bloqueio (US-603), última pessoa com a aba Usuários (matriz, seção 8), encomenda só para unidade ativa, e o filtro por `condominio_id` em toda consulta (R3).

### Encomendas: entrega e confirmação

Alinhamento da portaria definido em 22/10/2026: a portaria registra a entrega física e o morador que recebeu confirma depois, pela própria conta. Os estados são `aguardando_retirada → entregue_aguardando_confirmacao → retirada_confirmada`. A pendência não se encerra automaticamente e a conta de Funcionários não confirma pelo morador.

`destinatario_morador_unidade_id` e `recebedor_morador_unidade_id` referenciam `moradores_unidade`, com FK composta pelo condomínio. O service valida que os dois vínculos pertencem à unidade da encomenda e estão ativos no momento da respectiva operação. Outro morador ativo da mesma unidade pode receber. Para confirmar, o usuário do contexto deve ser o usuário do vínculo recebedor; registrar essa identidade em `confirmado_por_usuario_id`. A autorização central aplica a aba Encomendas e o vínculo ativo.

`status`, `unidade_id`, `destinatario_morador_unidade_id`, `foto_nota_arquivo_id`, `recebido_por_funcionario_id` e `registrada_em` são `NOT NULL`. Além das FKs, a TASK-81 deve aplicar as constraints abaixo:

```sql
CHECK (
  (status = 'aguardando_retirada'
    AND entregue_em IS NULL
    AND recebedor_morador_unidade_id IS NULL
    AND entregue_por_funcionario_id IS NULL
    AND confirmada_em IS NULL
    AND confirmado_por_usuario_id IS NULL)
  OR
  (status = 'entregue_aguardando_confirmacao'
    AND entregue_em IS NOT NULL
    AND recebedor_morador_unidade_id IS NOT NULL
    AND entregue_por_funcionario_id IS NOT NULL
    AND confirmada_em IS NULL
    AND confirmado_por_usuario_id IS NULL)
  OR
  (status = 'retirada_confirmada'
    AND entregue_em IS NOT NULL
    AND recebedor_morador_unidade_id IS NOT NULL
    AND entregue_por_funcionario_id IS NOT NULL
    AND confirmada_em IS NOT NULL
    AND confirmado_por_usuario_id IS NOT NULL)
),
CHECK (entregue_em IS NULL OR entregue_em >= registrada_em),
CHECK (confirmada_em IS NULL OR confirmada_em >= entregue_em)
```

A igualdade anterior entre o status e o AND de data/nome aceitava dados parciais quando o status era aguardando. Os ramos acima exigem todos os dados da etapa, ou nenhum deles, conforme o estado. As referências e os horários de recebimento/entrega não são apagados pela confirmação; o servidor gera as datas e a auditoria registra a conta autenticada e o funcionário selecionado.

### Índices para as consultas mais usadas

Além do índice em `condominio_id` de cada tabela:

- `encomendas (condominio_id, status, registrada_em DESC)` e `(unidade_id, registrada_em DESC)`: lista do morador e relatório (US-402, US-404).
- `reservas (area_id, data)`: grade do dia (US-603).
- `ocorrencias (condominio_id, status, criado_em DESC)`: fila da Administração (US-703).
- `visitantes (condominio_id, nome)` e `veiculos (condominio_id, placa)`: busca na portaria (US-503, US-505).
- `avisos (condominio_id, inicio_em, fim_em)`: avisos vigentes (US-802).
- `registros_auditoria (condominio_id, criado_em DESC)`: consulta do ADM com filtros (US-903).
- `envios_email (status) WHERE status <> 'enviado'`: fila de reenvio (US-803).

## 5. O que muda em relação à migração 0001

A 0001 já foi aplicada por todo mundo, então **não será editada**: as mudanças entram numa migração nova.

| Tabela | Mudança | Por quê |
| --- | --- | --- |
| `usuarios` | + `telefone`, `documento`, `senha_hash`, `sessao_versao`, `foto_arquivo_id`, `email_confirmado_em`, `consentimento_dados_em` | Login (US-101), conta da Administração com CPF/CNPJ (US-201), derrubar sessões (US-210), LGPD (US-1007) |
| `condominios` | + `status`, `motivo_rejeicao`, `solicitante_id`, `token_status_solicitacao_hash`; `ativo` permanece por compatibilidade | Wizard e fila de aprovação (TASK-28/29) |
| `chaves_acesso_condominio` | Hash único, condomínio, validade, consumo e revogação | Liberação de cadastro por chave (TASK-29) |
| `solicitacoes_vinculo_unidade` | Morador, condomínio, unidade, status da decisão e responsável principal; chave parcial impede pedidos abertos duplicados e mais de um principal aprovado por unidade | Aprovação do vínculo Morador–Unidade (TASK-30) |
| `unidades` | + `andar_id` (FK composta), `ativo`; o `UNIQUE (condominio_id, identificacao)` vira `UNIQUE (andar_id, identificacao)` | Estrutura bloco/andar (US-202) e o "101" que se repete em blocos diferentes |
| `vinculos_condominio` | a coluna `unidade_id` deixa de ser usada e sai numa migração seguinte | Um morador pode ter várias unidades (US-301), cada uma com suas permissões (US-304). A unidade passa para `moradores_unidade` |

O `vinculos_condominio` continua sendo **"esta conta atua neste condomínio com este perfil"**, e é o que o login usa (matriz, seção 4). Para o Morador, as unidades ficam em `moradores_unidade`. Isso muda a consequência registrada no ADR 0002, e por isso está no [ADR 0003](decisions/0003-moradores-em-varias-unidades.md).

## 6. Decisões tomadas aqui (confirmar na revisão)

1. **Reserva é por slot de 1 hora** (`data` + `hora_inicio`), e não por intervalo livre. Segue a grade de 1 hora da US-603 e deixa as regras 1 e 2 simples de garantir.
2. **Visitante e visita são tabelas separadas.** Mantida a autorização reutilizável durante o período cadastrado (US-501), conforme alinhamento da TASK-12 em 22/10/2026. O porteiro pode registrar mais de uma entrada nesse período, sempre com uma visita diferente e com saída da anterior já registrada. O cadastro pertence à unidade indicada. Validar a autorização a cada entrada: cadastro não cancelado, período vigente, vínculo/permissão do morador autorizador e contexto do condomínio. As datas `entrada_prevista` e `saida_prevista` abrangem os dias informados no fuso do condomínio, inclusive o último dia; fora desse período, consultar o morador por interfone ou telefone antes de liberar nova entrada. Não há consumo de uso único.
3. **Funcionários e responsáveis da Administração não são usuários** (matriz, seção 2). A conta compartilhada de cada perfil é um `usuario` comum com um `vinculo_condominio`.
4. **Auditoria com `bigint` em vez de `uuid`**, para a ordem de inserção ser natural e a tabela crescer sem custo.
5. **`proprietarios_unidade` separado de `unidades`**, porque tem muitos campos, foto e dados pessoais que só a Administração vê.
6. **Aviso pode ter `unidade_id`**: é como a Administração avisa uma unidade de reserva cancelada (US-605, US-602) sem criar uma tabela de notificações.
7. **Chaves de acesso guardadas somente como hash**, mostradas em texto claro uma única vez na emissão. A regeneração revoga a anterior; cada chave expira e só pode ser consumida uma vez.

7. **Encomendas com confirmação posterior pelo recebedor.** Mantidos os três estados descritos na seção 4, com referências para destinatário/recebedor e eventos separados. A matriz de permissões deve permitir somente ao recebedor autenticado confirmar.

## 7. Pontos em aberto

- **Destinatários dos comunicados:** a matriz restringe a leitura da Administração aos comunicados enviados ao seu condomínio, mas a entidade `comunicados` ainda não representa esses destinos. Definir a associação aos destinatários antes das migrations e APIs; não interpretar a ausência dessa relação como acesso global.
- **Solicitação e aprovação de vínculo:** `moradores_unidade` apresenta somente `ativo`/`desvinculado`, enquanto a matriz prevê solicitar, aprovar e rejeitar. Definir estados adicionais ou entidade de solicitação antes da implementação, sem conceder acesso a solicitações pendentes.

- **Conflito entre a TASK-81 e as stories:** a task de migrations fala em "constraint única de reserva: (área, data) por condomínio", o que deixaria uma única reserva por área por dia no prédio inteiro. A US-603 e a US-1006 dizem **uma por unidade, área e dia**, com grade de horários. Este DER segue as stories (regras 1 e 2). Ajustar o texto da TASK-81.
- **Login da conta compartilhada de Funcionários** (US-210 fala em "usuário e senha"): é um e-mail/telefone como as outras contas, ou um nome de usuário próprio? Este DER assume e-mail.
- **Permissões iniciais do morador:** a regra proposta na matriz (primeiro morador com tudo, os seguintes sem a aba Usuários) ainda depende do Paulo.
- **Documento comprobatório da conta da Administração** (US-201, opcional): este DER guarda os documentos por condomínio, em `condominio_documentos`, porque é isso que o ADM analisa na fila (US-203). Confirmar com o Paulo se o documento da US-201 é o mesmo.
- **Comunicados lidos:** a US-804 não pede controle de leitura, então não há tabela para isso.
- **Contatos da portaria sem entrada:** definir com Eduardo/Vitor a representação de negativas e ausência de resposta (entidade própria ou evento de auditoria consultável), preservando canal, morador consultado, funcionário e horário sem criar uma visita. O registro já aparece na prévia da TASK-12; esta revisão do DER ainda não cria uma tabela para ele.

## 8. Revisão por módulo

Pronto quando cada dono confirmar as suas tabelas e os leads aprovarem no portão da Sprint 0.

- [ ] Gabriel: isolamento (convenções e regra 22), `usuarios`, vínculos e `permissoes_aba`
- [ ] Paulo: condomínio, cadastro, estrutura, chaves e `moradores_unidade`
- [ ] Vitor: áreas, reservas e ocorrências
- [ ] Tude: funcionários, responsáveis, avisos, chamados, comunicados, auditoria e e-mail
- [ ] Eduardo: encomendas, visitantes, veículos e `arquivos`
