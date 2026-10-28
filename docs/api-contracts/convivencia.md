# Convivência — proposta de contrato REST (TASK-10)

Status: rascunho para revisão no portão dos leads. Endpoints abaixo **não estão implementados**. Cobre áreas comuns, bloqueios, reservas, ocorrências e as consultas e cadastros do Morador (visitantes e veículos), mais a leitura de encomendas que a US-402 atribui ao mesmo módulo.

Convenções comuns (envelope de erro, paginação, ações explícitas, `responsavel_id`, arquivos, fuso): [convencoes.md](convencoes.md). Modelo de dados: [modelo-de-dados.md](../modelo-de-dados.md), seção 3.4 (convivência) e seção 4 (regras 1, 2, 3, 9 e 12 a 16). Permissões: [matriz](../permissoes-e-multitenant.md), seções 7 e 8.

Histórias cobertas: US-601 a US-605, US-701 a US-704, US-402, US-501, US-502.

## 1. Regras que valem para o módulo todo

- `condominio_id` vem do token (R1). A unidade vem do vínculo do Morador (R10): toda rota do Morador que recebe `unidade_id` confere que ele tem vínculo ativo com a unidade **e** a aba correspondente habilitada. Unidade de outro morador retorna 404; aba sem acesso retorna 403.
- A Administração enxerga o condomínio inteiro. O **Funcionário não acessa** reservas, áreas, bloqueios nem ocorrências (matriz). Ele só consulta veículos (seção 6).
- A agenda do Morador mostra `livre`, `ocupado` ou `da_minha_unidade`. **A API nunca devolve a identificação de outra unidade** em nenhuma resposta ao Morador.
- Nada é apagado. Área é desativada, reserva é cancelada, ocorrência é resolvida, visitante é cancelado, veículo é removido (desativado).
- Ação crítica da Administração (cancelar reserva, bloquear data, alterar status de ocorrência) exige `responsavel_id` e gera um evento de auditoria (`registrar_acao`, [plataforma.md](plataforma.md) seção 4).

## 2. Áreas comuns

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /areas-comuns` | Morador `[Reserva de Áreas]`: só ativas. Administração: todas, filtro `ativa` | `page`, `page_size`, `ativa` (só Administração) | 200, lista |
| `GET /areas-comuns/{id}` | Mesmo escopo | — | 200, objeto |
| `POST /areas-comuns` | Administração | JSON abaixo | 201, objeto |
| `PUT /areas-comuns/{id}` | Administração | JSON abaixo (substitui os campos editáveis) | 200, objeto |
| `POST /areas-comuns/{id}/desativacao` | Administração | `{}` | 200, objeto com `ativa = false` |
| `POST /areas-comuns/{id}/reativacao` | Administração | `{}` | 200, objeto com `ativa = true` |

Escrita:

```json
{
  "nome": "Salão de festas",
  "foto_arquivo_id": "UUID",
  "regras": "Máximo de 40 pessoas. Silêncio após as 22h.",
  "abre_as": "08:00",
  "fecha_as": "22:00",
  "capacidade": 40
}
```

Regras: `nome` de 1 a 100 caracteres, único entre as áreas do condomínio ignorando maiúsculas (proposta). `abre_as` e `fecha_as` em **hora cheia**, com `fecha_as` > `abre_as` (regra 16 do DER) e janela de pelo menos 1 hora: a grade é de 1 hora, e horas quebradas criariam um último slot parcial. `capacidade` > 0. `foto_arquivo_id` obrigatório, porque a US-603 mostra nome **e foto** da área. `regras` de até 2000 caracteres.

Objeto de área:

```json
{
  "id": "UUID",
  "nome": "Salão de festas",
  "foto_arquivo_id": "UUID",
  "regras": "Máximo de 40 pessoas. Silêncio após as 22h.",
  "abre_as": "08:00",
  "fecha_as": "22:00",
  "capacidade": 40,
  "ativa": true
}
```

Área **desativada** não aceita novas reservas e some das consultas do Morador (404 em qualquer rota dele). As reservas **já feitas** continuam ativas; a Administração cancela uma a uma, se quiser, pela seção 4. Alterar `abre_as` ou `fecha_as` não mexe em reservas existentes: se uma reserva ficar fora do novo horário, o `PUT` responde 409 (`reason: "reservas_fora_do_horario"`) e a Administração decide entre cancelar as reservas ou manter o horário.

## 3. Bloqueio de datas (US-602, Should, Sprint 3)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /areas-comuns/{id}/bloqueios` | Administração | `data_de`, `data_ate`, paginação | 200, lista |
| `GET /areas-comuns/{id}/bloqueios/previa` | Administração | Query `data_inicio`, `data_fim` | 200, reservas que seriam afetadas |
| `POST /areas-comuns/{id}/bloqueios` | Administração | JSON abaixo | 201, bloqueio |

```json
{
  "data_inicio": "2026-12-10",
  "data_fim": "2026-12-12",
  "motivo": "Manutenção do piso",
  "responsavel_id": "UUID",
  "confirmar_cancelamentos": false
}
```

`data_fim` >= `data_inicio` (regra 15; um único dia repete a mesma data). Datas inclusivas, no fuso do condomínio. `motivo` de 1 a 300 caracteres.

**Fluxo com reservas existentes**, que é a parte delicada da US-602:

1. O front chama a `previa`. Resposta: `{"reservas_afetadas": [{"id": "UUID", "unidade": {"id": "UUID", "identificacao": "Bloco A / 101"}, "data": "2026-12-10", "hora_inicio": "18:00"}], "total": 1}`. A Administração vê as unidades, por isso a identificação pode aparecer aqui.
2. Sem reservas afetadas, o `POST` cria o bloqueio direto.
3. Com reservas afetadas e `confirmar_cancelamentos = false`, o `POST` responde **409** (`reason: "reservas_afetadas"`) e não grava nada.
4. Com `confirmar_cancelamentos = true`, **uma única transação** cria o bloqueio, cancela cada reserva afetada com o motivo "Bloqueio da área: {motivo}" (cancelamento pela Administração, seção 4), cria **um aviso por unidade afetada** ([plataforma.md](plataforma.md) seção 1, `publicar_para_unidade`) e enfileira o e-mail `reserva_cancelada` ([plataforma.md](plataforma.md) seção 6). Se qualquer passo falhar, nada é gravado.
5. Auditoria: um evento `area.bloquear` para o bloqueio, mais um `reserva.cancelar` para cada reserva cancelada.

Bloqueios sobrepostos para a mesma área são aceitos (não causam problema). A US pede que o bloqueio apareça "como indisponível" no calendário do Morador: o estado `bloqueado` da agenda (seção 4).

**Remover um bloqueio** (errou a data, a manutenção foi cancelada) não existe no DER: `bloqueios_area` não tem coluna de remoção. Ver pendências.

## 4. Reservas

### 4.1 Agenda e calendário (Morador)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /areas-comuns/{id}/agenda` | Morador `[Reserva de Áreas]` | `unidade_id` (obrigatório), `data` (obrigatório, `AAAA-MM-DD`) | 200, grade do dia |
| `GET /areas-comuns/{id}/calendario` | Morador `[Reserva de Áreas]` | `unidade_id` (obrigatório), `mes` (`AAAA-MM`) | 200, marcações do mês |

Grade do dia (alinhar o formato com o Matheus, que faz o front da US-603):

```json
{
  "area_id": "UUID",
  "unidade_id": "UUID",
  "data": "2026-11-14",
  "unidade_ja_reservou": false,
  "slots": [
    {"hora_inicio": "08:00", "hora_fim": "09:00", "estado": "livre"},
    {"hora_inicio": "09:00", "hora_fim": "10:00", "estado": "da_minha_unidade", "reserva_id": "UUID"},
    {"hora_inicio": "10:00", "hora_fim": "11:00", "estado": "ocupado"},
    {"hora_inicio": "11:00", "hora_fim": "12:00", "estado": "bloqueado"},
    {"hora_inicio": "07:00", "hora_fim": "08:00", "estado": "passado"}
  ]
}
```

| `estado` | Significado | Cor na US-603 |
| --- | --- | --- |
| `livre` | Pode reservar | Branco |
| `da_minha_unidade` | Reserva ativa da unidade informada (traz `reserva_id`) | Verde |
| `ocupado` | Reserva ativa de **outra** unidade, sem dizer qual | Vermelho |
| `bloqueado` | Dentro de um bloqueio da Administração; o dia inteiro fica assim | Cinza (proposta) |
| `passado` | Horário que já passou (hoje ou datas anteriores) | Cinza (proposta) |

Há um slot por hora de `abre_as` até `fecha_as`: nunca aparecem horários fora do funcionamento ("não podem ser escolhidos"). `unidade_ja_reservou = true` quando a unidade já tem reserva ativa nessa área e dia; o front pode desabilitar os slots `livre` e explicar a regra, mas **o servidor continua validando** (seção 4.2).

Calendário do mês, para destacar dias: `{"mes": "2026-11", "dias": [{"data": "2026-11-14", "bloqueado": false, "tem_reserva_da_minha_unidade": true}]}`, com os dias em que algo acontece (bloqueio ou reserva da unidade). O dia atual é destacado pelo front. O calendário é uma **proposta** e pode ser descartado se a grade do dia bastar.

### 4.2 Criar reserva e a regra de conflito

`POST /reservas` — Morador `[Reserva de Áreas]`, 201 com a reserva.

```json
{"unidade_id": "UUID", "area_id": "UUID", "data": "2026-11-14", "hora_inicio": "18:00"}
```

Não existe `hora_fim`: a reserva é sempre um slot de 1 hora (decisão 1 do DER).

**Ordem de validação** (a primeira falha encerra o pedido):

| # | Verificação | Falha |
| --- | --- | --- |
| 1 a 4 | Autorização central: token, condomínio ativo, perfil, unidade do Morador e aba | 401 / 403 / 404 |
| 5 | A área existe no condomínio e está **ativa** | 404 |
| 6 | `data` válida e `hora_inicio` em hora cheia | 422 |
| 7 | `abre_as <= hora_inicio` e `hora_inicio + 1h <= fecha_as` | 422 |
| 8 | A data e o horário não estão no passado, no fuso do condomínio | 422 |
| 9 | Nenhum bloqueio cobre a data | 409, `reason: "area_bloqueada"` |
| 10 | A unidade não tem outra reserva **ativa** nessa área e dia | 409, `reason: "reserva_duplicada_unidade"` |
| 11 | O horário não está ocupado por reserva ativa de outra unidade | 409, `reason: "horario_ocupado"` |

Mensagens (pt-BR, prontas para o front exibir): "Cada unidade pode reservar no máximo um horário por área por dia." (10) e "Este horário acabou de ser reservado por outra unidade. Escolha outro." (11). **A mensagem 11 nunca cita a outra unidade.**

**Concorrência (US-603: "dois pedidos simultâneos para o mesmo horário gravam só uma reserva").** As verificações 10 e 11 do service são para dar a mensagem certa, mas **quem garante a regra é o banco**, com os dois índices únicos parciais do DER:

```sql
CREATE UNIQUE INDEX uq_reservas_unidade_area_dia_ativa
  ON reservas (unidade_id, area_id, data) WHERE status = 'ativa';
CREATE UNIQUE INDEX uq_reservas_area_horario_ativa
  ON reservas (area_id, data, hora_inicio) WHERE status = 'ativa';
```

Roteiro do service: abrir transação, tentar o `INSERT` e capturar `IntegrityError`; pelo nome da constraint violada, devolver o 409 com o `reason` correto (`uq_reservas_unidade_area_dia_ativa` → `reserva_duplicada_unidade`, `uq_reservas_area_horario_ativa` → `horario_ocupado`). **Nunca** confiar só num `SELECT` antes do `INSERT`: dois pedidos simultâneos passam juntos pelo `SELECT`. Os nomes dos índices acima são proposta para a TASK-81 (Davi); o service depende deles.

Como os índices só valem para `status = 'ativa'`, cancelar uma reserva **libera o horário na hora** (US-604) e preserva o registro cancelado.

Objeto de reserva:

```json
{
  "id": "UUID",
  "area": {"id": "UUID", "nome": "Salão de festas"},
  "unidade": {"id": "UUID", "identificacao": "Bloco A / 101"},
  "data": "2026-11-14",
  "hora_inicio": "18:00",
  "hora_fim": "19:00",
  "status": "ativa",
  "reservada_por": {"id": "UUID", "nome": "Ana Martins"},
  "criada_em": "2026-11-10T14:03:00Z",
  "cancelamento": null
}
```

Depois de cancelada: `status = "cancelada"` e `cancelamento = {"em": "...", "por": "morador" | "administracao", "motivo": "... | null", "responsavel": {"id": "UUID", "nome": "..."} | null}`. O campo `responsavel` só aparece para a Administração. `reservada_por` aparece só nas respostas da própria unidade e da Administração.

### 4.3 Consultar e cancelar

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /reservas` | Morador `[Reserva de Áreas]` (da unidade informada); Administração (condomínio) | Morador: `unidade_id` obrigatório. Administração: `area_id`, `unidade_id`, `data_de`, `data_ate`, `status`. Ambos: paginação | 200, lista |
| `GET /reservas/{id}` | Mesmo escopo | — | 200, objeto |
| `POST /reservas/{id}/cancelamento` | Morador `[Reserva de Áreas]` ou Administração | Morador: `{}`. Administração: `{"motivo": "...", "responsavel_id": "UUID"}` | 200, objeto cancelado |

**Ordem da lista do Morador (US-604):** reservas **futuras primeiro**, da mais próxima para a mais distante, depois as passadas, da mais recente para a mais antiga. Futura quer dizer `data` + `hora_inicio` ainda por vir no fuso do condomínio. A lista da Administração (US-605) usa a ordem comum (data decrescente).

Regras do cancelamento:

- Só parte de `ativa`; repetir retorna 409. Reserva cujo horário já passou não se cancela (409, `reason: "reserva_encerrada"`).
- **Morador:** cancela reservas da própria unidade. O DER guarda o morador que reservou (`usuario_id`) e quem cancelou (`cancelada_por_usuario_id`); a matriz diz "cancela só a própria". Ver pendências: "própria" significa a da unidade ou a que o próprio morador fez?
- **Administração:** `motivo` obrigatório, de 1 a 300 caracteres, e `responsavel_id` obrigatório. Efeitos na mesma transação: grava `cancelada_responsavel_id`; cria **aviso para a unidade** com o motivo ([plataforma.md](plataforma.md) seção 1); enfileira o e-mail `reserva_cancelada` ao morador que reservou ([plataforma.md](plataforma.md) seção 6); registra o evento `reserva.cancelar`.
- Cancelamento pelo Morador não gera aviso nem e-mail, mas fica registrado nas colunas `cancelada_*` da reserva.

## 5. Ocorrências

**Estados.** A TASK-10 pede "Em aberto, Resolvida e Reaberta", mas o DER (regra 9) e a US-704 ("reabrir devolve o status para Em aberto") só têm dois estados: `em_aberto` e `resolvida`. **Reabertura é um evento do histórico** (`tipo = "reabertura"`), não um estado. Este contrato segue o DER.

Transições: `em_aberto → resolvida` (resolução, Administração) e `resolvida → em_aberto` (reabertura, Morador). Nenhuma outra. A cor (vermelho/verde) é decisão do front a partir do `status`; a API não devolve cor.

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `POST /ocorrencias` | Morador `[Ocorrências]` | JSON abaixo | 201, ocorrência |
| `GET /ocorrencias` | Morador `[Ocorrências]` (da unidade informada); Administração | Morador: `unidade_id` obrigatório. Administração: `unidade_id`, `de`, `ate`. Ambos: `status`, paginação | 200, lista |
| `GET /ocorrencias/{id}` | Mesmo escopo | — | 200, ocorrência com histórico |
| `POST /ocorrencias/{id}/respostas` | Administração | `{"texto": "...", "responsavel_id": "UUID"}` | 201, interação |
| `POST /ocorrencias/{id}/resolucao` | Administração | `{"texto": "... (opcional)", "responsavel_id": "UUID"}` | 200, ocorrência |
| `POST /ocorrencias/{id}/comentarios` | Morador `[Ocorrências]` (US-704, Could, Sprint 3) | `{"texto": "...", "anexos": ["UUID"]}` | 201, interação |
| `POST /ocorrencias/{id}/reabertura` | Morador `[Ocorrências]` (US-704) | `{"texto": "..."}` | 200, ocorrência |

Abertura (US-701):

```json
{
  "unidade_id": "UUID",
  "titulo": "Vazamento na garagem",
  "detalhe": "Há água escorrendo do teto da vaga 12 desde ontem.",
  "anexos": ["UUID", "UUID"]
}
```

`unidade_id`, `titulo` (1 a 120 caracteres) e `detalhe` (1 a 4000) são obrigatórios; `anexos` é opcional, com no máximo 5 IDs (proposta) de arquivos de imagem ou vídeo; tipo ou tamanho inválido é recusado pela TASK-26 antes de chegar aqui, e o servidor confere de novo. Data e hora são automáticas. Status inicial `em_aberto`. Quem abre fica registrado (`aberta_por_usuario_id`).

Objeto de ocorrência (detalhe):

```json
{
  "id": "UUID",
  "unidade": {"id": "UUID", "identificacao": "Bloco A / 101"},
  "titulo": "Vazamento na garagem",
  "detalhe": "Há água escorrendo do teto da vaga 12 desde ontem.",
  "status": "em_aberto",
  "aberta_por": {"id": "UUID", "nome": "Ana Martins"},
  "criada_em": "2026-11-10T14:03:00Z",
  "resolvida_em": null,
  "anexos": [{"arquivo_id": "UUID", "interacao_id": null}],
  "interacoes": [
    {
      "id": "UUID",
      "tipo": "resposta",
      "texto": "Equipe de manutenção acionada.",
      "autor": {"tipo": "administracao", "nome": "Carlos (síndico)"},
      "em": "2026-11-10T16:20:00Z",
      "anexos": []
    }
  ]
}
```

`interacoes[].tipo` é `resposta`, `comentario`, `resolucao` ou `reabertura`, em ordem cronológica. O `autor` da Administração vem da lista de responsáveis escolhida em `responsavel_id` (US-703: "responsável escolhido na lista da Administração"); o do Morador é o nome do usuário. O Morador vê data, texto e responsável de cada resposta (US-702). A **lista** devolve `id`, `titulo`, `status`, `unidade`, `criada_em`, `ultima_interacao_em` e `aguardando_administracao` (`true` quando a última interação é de um Morador ou ainda não há resposta).

Regras:

- Morador só vê ocorrências de unidades vinculadas a ele (404 nas outras). A Administração vê todas do condomínio. **Funcionário: 403.**
- **Resolução:** só de `em_aberto` (senão 409, `reason: "ocorrencia_ja_resolvida"`); grava `resolvida_em`, cria a interação `resolucao` e gera o evento de auditoria `ocorrencia.resolver`.
- **Reabertura:** só de `resolvida` (senão 409, `reason: "ocorrencia_nao_resolvida"`); `texto` obrigatório (o que voltou a acontecer), de 1 a 2000 caracteres. Volta a `em_aberto`, limpa `resolvida_em` (o histórico guarda quando foi resolvida), cria a interação `reabertura` e gera o evento `ocorrencia.reabrir`.
- **Como a Administração "é avisada" da reabertura (US-704):** não há tabela de notificações. Proposta: a ocorrência reaberta volta para a fila `status=em_aberto` com `aguardando_administracao = true`, e o painel da Administração (hub) destaca esses itens. Sem e-mail, porque o US-803 só cobre quatro eventos.
- O Morador comenta em qualquer estado (US-704: "enquanto a ocorrência existir"); comentar não muda o status.
- Nenhuma ocorrência é apagada, nem a resolvida (US-703).

## 6. Consultas e cadastros do Morador (encomendas, visitantes e veículos)

### 6.1 Encomendas (US-402)

A leitura da encomenda é do Vitor (US-402), mas o **recurso e os objetos** são os de `portaria.md` (Eduardo). Nada se redefine: o Morador usa `GET /encomendas` e `GET /encomendas/{id}` com a permissão `[Encomendas]`. Dois ajustes **propostos** em `portaria.md`:

1. Aceitar `unidade_id` como filtro e **exigi-lo quando quem chama é o Morador** (a US-402 abre com "seleciona a unidade"; sem o filtro, uma lista mista confunde). Funcionário e Administração continuam sem exigi-lo.
2. A lista do Morador ordena da encomenda mais recente para a mais antiga e traz foto, data e hora, descrição, quem recebeu (`recebimento.funcionario`) e status. É o que `portaria.md` já devolve.

### 6.2 Visitantes cadastrados pelo Morador (US-501)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /visitantes` | Morador `[Visitantes]` (unidade informada) | `unidade_id` obrigatório, `busca`, `situacao` (`vigentes`, `futuros`, `encerrados`, `cancelados`), paginação | 200, lista |
| `GET /visitantes/{id}` | Mesmo escopo | — | 200, objeto |
| `POST /visitantes` | Morador `[Visitantes]` | JSON abaixo | 201, objeto |
| `PUT /visitantes/{id}` | Morador `[Visitantes]` | JSON abaixo | 200, objeto |
| `POST /visitantes/{id}/cancelamento` | Morador `[Visitantes]` | `{}` | 200, objeto com `cancelado_em` |

```json
{
  "unidade_id": "UUID",
  "nome": "Carlos Souza",
  "cpf": "12345678909",
  "idade": 35,
  "observacoes": "Carro prata, placa ABC1D23",
  "entrada_prevista": "2026-11-14",
  "saida_prevista": "2026-11-15"
}
```

Obrigatórios: `unidade_id`, `nome` (nome completo, 3 a 120 caracteres), `entrada_prevista` e `saida_prevista`. Opcionais: `cpf` (só dígitos; se informado, os dígitos verificadores são validados), `idade` (0 a 120), `observacoes` (até 300). `saida_prevista` >= `entrada_prevista` (regra 12); as datas são **inclusivas** e valem no fuso do condomínio, como em `portaria.md`. O `cpf` nunca aparece na resposta ao Funcionário da portaria (`portaria.md` limita o que ele vê); o Morador vê o que cadastrou. O campo `avulso` fica `false` aqui; o cadastro avulso da portaria é a US-504 (Eduardo).

Esse cadastro **é** a autorização reutilizável por período que `portaria.md` consome (decisão de 22/10/2026): a portaria verifica a cada entrada se o cadastro não foi cancelado e se o período está vigente.

Regras de edição e cancelamento (US-501: "editado ou cancelado antes da entrada"):

- `PUT`: só enquanto **nenhuma visita foi registrada** para esse cadastro (senão 409, `reason: "visitante_ja_utilizado"`). Não troca de unidade.
- `POST .../cancelamento`: aceito enquanto não houver visita em andamento. Repetir retorna 409. A proposta de permitir cancelar **depois** da primeira entrada vai além do texto da US-501 e está nas pendências.
- O Morador só enxerga cadastros de unidades vinculadas a ele.

### 6.3 Veículos (US-502)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /veiculos` | Morador `[Veículos]` (unidade informada); Funcionário (condomínio); Administração (condomínio) | Morador: `unidade_id` obrigatório. Funcionário e Administração: `unidade_id`, `busca` (placa, marca, modelo). Ambos: paginação | 200, lista |
| `GET /veiculos/{id}` | Mesmo escopo | — | 200, objeto |
| `POST /veiculos` | Morador `[Veículos]` | JSON abaixo | 201, objeto |
| `PUT /veiculos/{id}` | Morador `[Veículos]` | JSON abaixo | 200, objeto |
| `POST /veiculos/{id}/remocao` | Morador `[Veículos]` | `{}` | 200, objeto com `ativo = false` |

```json
{"unidade_id": "UUID", "placa": "ABC1D23", "marca": "Fiat", "modelo": "Argo", "cor": "Prata"}
```

Todos obrigatórios. A **placa** é normalizada pelo servidor (maiúsculas, sem hífen nem espaço) e validada pelo formato brasileiro antigo ou Mercosul, `^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$` (regra 13 do DER). `marca`, `modelo` e `cor` de 1 a 40 caracteres.

- Placa repetida **na mesma unidade**, entre veículos ativos: 409 (`reason: "placa_ja_cadastrada_na_unidade"`), regra 14.
- Placa já cadastrada em **outra** unidade: **o cadastro é aceito** (regra 14: a story só pede aviso) e o Morador **não é informado** de que existe em outra unidade, para não vazar dados de terceiros. A Administração é avisada; a forma do aviso está nas pendências.
- `remocao` desativa (`ativo = false`, `removido_em` preenchido). A placa pode ser cadastrada de novo depois.
- Funcionário (portaria): consulta `GET /veiculos` do condomínio inteiro para conferência no portão, só leitura (matriz: Veículos Funcionário "V (C)"). Alinhar com a US-505 (Eduardo, Sprint 3).

## 7. Casos obrigatórios de teste

Além da matriz parametrizada e dos testes de isolamento (matriz, seção 11):

- Reserva: duas requisições **simultâneas** (threads ou `asyncio.gather` com sessões separadas) para o mesmo `area_id`, `data` e `hora_inicio` produzem **uma** reserva `ativa` e um 409 (`horario_ocupado`); duas simultâneas da mesma unidade, área e dia em horários diferentes produzem uma reserva e um 409 (`reserva_duplicada_unidade`).
- Reserva: horário fora do funcionamento, no passado, em área desativada (404) e dentro de bloqueio; cancelar e reservar o mesmo horário de novo funciona; cancelamento repetido retorna 409.
- A grade nunca devolve identificação de outra unidade (inspecionar o JSON inteiro, inclusive `reservada_por`).
- Bloqueio com reservas: sem `confirmar_cancelamentos` retorna 409 e **não grava nada**; com a confirmação, tudo é gravado na mesma transação e uma falha no meio desfaz tudo (simular erro no aviso).
- Cancelamento pela Administração sem `motivo` ou com `responsavel_id` de outro condomínio retorna 422 e 404.
- Ocorrência: Funcionário recebe 403; Morador de outra unidade recebe 404; resolver duas vezes retorna 409; reabrir uma `em_aberto` retorna 409; o histórico mantém resolução e reabertura em ordem; ninguém consegue apagar.
- Morador com aba Sem Acesso: 403 em reservas, ocorrências, visitantes e veículos, mesmo que a tela seja burlada.
- Visitante: edição depois de uma visita registrada retorna 409; CPF inválido retorna 422.
- Veículo: placa fora do formato retorna 422; repetida na unidade retorna 409; repetida em outra unidade cria o veículo **sem** revelar isso na resposta ao Morador.

## 8. Pendências e responsáveis

| Tema | Decisão ou alinhamento necessário | Quem |
| --- | --- | --- |
| Remover bloqueio | `bloqueios_area` não tem coluna de remoção, e a Administração vai errar datas. **Proposta:** adicionar `removido_em` e `removido_por_usuario_id`, com rota `POST /areas-comuns/{id}/bloqueios/{bloqueio_id}/remocao` e auditoria. Sem a coluna, o bloqueio errado é permanente. | Davi e Vitor |
| "Própria reserva" | A matriz diz "cancela só a própria"; a US-604 diz "reservas da unidade". **Proposta:** qualquer morador da unidade com a aba habilitada cancela reservas da unidade (a permissão já é por unidade). | Gabriel e Vitor |
| Nomes das constraints | Combinar os nomes dos índices da seção 4.2, dos quais o service depende para escolher o `reason` | Davi e Vitor |
| `reason` e `details` no envelope | Extensões aditivas de [convencoes.md](convencoes.md) seção 4 | Gabriel |
| Calendário e grade | Confirmar o formato da grade (estados `bloqueado` e `passado` incluídos) e se o `calendario` do mês é necessário | Matheus e Vitor |
| Fuso do condomínio | Hoje não há coluna; proposta: `America/Sao_Paulo` fixo no MVP | Davi e Gabriel |
| Antecedência da reserva | As stories não limitam quão à frente se reserva. Proposta: sem limite no MVP; revisar se houver abuso | Paulo (regra de negócio) |
| Aviso à Administração por placa duplicada | A US-502 pede "aviso à Administração", mas `avisos` é voltado a moradores e funcionários. **Proposta:** o relatório de veículos da Administração (US-506) marca placas repetidas entre unidades; sem notificação ativa. | Vitor, Tude e Paulo |
| Cancelar visitante depois da primeira entrada | Com a autorização reutilizável (22/10), o Morador precisa poder **revogar** um cadastro em curso. A US-501 só permite cancelar "antes da entrada". **Proposta:** permitir enquanto não houver visita em andamento. | Vitor e Eduardo |
| `unidade_id` em `GET /encomendas` | Ajuste em `portaria.md` (seção 6.1) | Eduardo e Vitor |
| Anexos de ocorrência | Tipos, tamanhos, quantidade (5) e leitura protegida de vídeo | Eduardo (TASK-26) e Vitor |
| Funcionário nas reservas e ocorrências | A matriz nega o acesso. Confirmar que o porteiro não precisa ver a agenda de áreas comuns | Gabriel |

Nenhuma aprovação de Davi, Matheus ou dos leads foi presumida neste documento. O "pronto quando" da TASK-10 é o contrato e a regra aprovados no portão dos leads.
