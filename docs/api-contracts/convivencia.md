# Convivência — proposta de contrato REST (TASK-10)

Status: rascunho para revisão no portão dos leads. **Implementado (TASK-84):** áreas comuns (seção 2) e reservas (seção 4: agenda, calendário, criar, consultar e cancelar). **Implementado (TASK-63):** bloqueio de datas com cancelamento das reservas afetadas (seção 3), enfileiramento de `reserva_cancelada` no cancelamento pela Administração (seção 4.3), comentários e reabertura de ocorrências (seção 5) e relatório de encomendas (seção 6.1). **Implementado (TASK-48):** aviso à unidade no cancelamento administrativo, na mesma transação da reserva e da auditoria. **Implementado (TASK-40):** ocorrências (seção 5: abrir, consultar, responder e resolver). **Implementado (TASK-38):** visitantes (seção 6.2) e veículos (seção 6.3) do Morador, e o filtro `unidade_id` em `GET /encomendas` (seção 6.1, ainda opcional). **Implementado (US-506 simplificada):** relatórios administrativos de visitantes e veículos (seção 6.4), sem CSV. `reason` adicionais além dos do contrato: `nome_duplicado`, `foto_invalida`, `area_ja_desativada`, `area_ja_ativa`, `hora_invalida`, `fora_do_funcionamento`, `horario_passado`, `reserva_ja_cancelada`, `periodo_passado`. **Pendentes:** remover bloqueios lançados por engano (seção 3), o worker que envia os e-mails da fila (a fila `envios_email` já recebe `reserva_cancelada`) e tornar `unidade_id` obrigatório para o Morador em `GET /encomendas` (seção 6.1). Cobre áreas comuns, bloqueios, reservas, ocorrências e as consultas e cadastros do Morador (visitantes e veículos), mais a leitura de encomendas que a US-402 atribui ao mesmo módulo.

Convenções comuns (envelope de erro, paginação, ações explícitas, `responsavel_id`, arquivos, fuso): [convencoes.md](convencoes.md). Modelo de dados: [modelo-de-dados.md](../modelo-de-dados.md), seção 3.4 (convivência) e seção 4 (regras 1, 2, 3, 9 e 12 a 16). Permissões: [matriz](../permissoes-e-multitenant.md), seções 7 e 8.

Histórias cobertas: US-601 a US-605, US-701 a US-704, US-402, US-501, US-502 e US-506 simplificada.

## 1. Regras que valem para o módulo todo

- `condominio_id` vem do token (R1). A unidade vem do vínculo do Morador (R10): toda rota do Morador que recebe `unidade_id` confere que ele tem vínculo ativo com a unidade **e** a aba correspondente habilitada. Unidade de outro morador retorna 404; aba sem acesso retorna 403.
- A Administração enxerga o condomínio inteiro. O **Funcionário não acessa** reservas, áreas, bloqueios nem ocorrências (matriz). Ele só consulta veículos (seção 6).
- A agenda do Morador mostra `livre`, `ocupado` ou `da_minha_unidade`. **A API nunca devolve a identificação de outra unidade** em nenhuma resposta ao Morador.
- Nada é apagado. Área é desativada, reserva é cancelada, ocorrência é resolvida, visitante é cancelado, veículo é removido (desativado).
- Ação crítica da Administração (cancelar reserva, bloquear data, alterar status de ocorrência) exige `responsavel_id` e gera um evento de auditoria (`registrar_acao`, [plataforma.md](plataforma.md) seção 4).

## 2. Áreas comuns

O catálogo de áreas é compartilhado pelo condomínio: para listar, detalhar e baixar a foto,
o Morador precisa da aba Reservas Com Acesso em pelo menos uma unidade em que tenha vínculo
ativo no condomínio selecionado. A permissão é lida novamente a cada requisição. Isso não
libera operações em outra unidade: agenda, criação e cancelamento continuam conferindo a
aba na unidade específica. Fotos de áreas desativadas ficam disponíveis só à Administração.

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

**Remover um bloqueio** (errou a data, a manutenção foi cancelada) ainda não tem rota: `bloqueios_area` já tem `removido_em` e `removido_por_usuario_id` (o bloqueio removido deixa de valer e some da lista), mas a rota de remoção continua pendente.

Implementação (TASK-63):

- **Só a Administração** (403 para os demais perfis). `GET .../bloqueios` lista os bloqueios ativos da área do mais recente ao mais antigo (`data_de` e `data_ate` filtram os que tocam o período); `GET .../bloqueios/previa` exige `data_inicio` e `data_fim` (422 se invertidas).
- **`motivo` de 1 a 200 caracteres**, o tamanho da coluna do DER (o contrato falava em 300). O motivo gravado no cancelamento de cada reserva é "Bloqueio da área: {motivo}".
- **Período já encerrado** (`data_fim` anterior a hoje): 422 `periodo_passado`. Um bloqueio que termina hoje vale.
- **Reservas afetadas** são as `ativas` do período cujo horário **ainda não começou**; a que já começou não se cancela (`reserva_encerrada`) e fica de fora da prévia e do cancelamento. A resposta 201 traz `reservas_canceladas`.
- **Um aviso por unidade afetada**, com todas as reservas dela no texto (até 20; as demais viram "e mais N"), e **um e-mail `reserva_cancelada` por reserva**, para quem reservou, na fila `envios_email`.
- **Auditoria:** `area.bloquear` (com o número de reservas canceladas) e um `reserva.cancelar` por reserva. Tudo na mesma transação: uma falha em qualquer passo desfaz o bloqueio e os cancelamentos.
- **Concorrência.** O bloqueio trava a linha da área em modo exclusivo e a criação de reserva, em modo compartilhado. Uma reserva em andamento faz o bloqueio esperar (e entrar na prévia dele); um bloqueio em andamento faz a reserva esperar e depois receber 409 `area_bloqueada`. Reservas entre si não se atrapalham.

## 4. Reservas

### 4.1 Agenda e calendário (Morador)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /areas-comuns/{id}/agenda` | Morador `[Reserva de Áreas]` | `unidade_id` (obrigatório), `data` (obrigatório, `AAAA-MM-DD`) | 200, grade do dia |
| `GET /areas-comuns/{id}/calendario` | Morador `[Reserva de Áreas]` | `unidade_id` (obrigatório), `mes` (`AAAA-MM`), `incluir_disponibilidade` (opcional) | 200, marcações do mês |

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

O calendário mensal retorna os dias com bloqueio ou reserva da própria unidade em `dias`. Com `incluir_disponibilidade=true`, também retorna `dias_disponiveis`, uma lista de datas com pelo menos um horário futuro que a unidade pode reservar. A resposta respeita os bloqueios e o limite de uma reserva por unidade, área e dia. O calendário não identifica outras unidades ou moradores.

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
- **E-mail (TASK-63).** O `reserva_cancelada` entra em `envios_email` (`status = pendente`, `recurso_tipo = reserva`) na mesma transação do cancelamento, para o e-mail de quem fez a reserva (`usuario_id`), não do outro morador da unidade. Cancelamento recusado não enfileira nada.

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

`interacoes[].tipo` é `resposta`, `comentario`, `resolucao` ou `reabertura`, em ordem cronológica. O `autor` da Administração vem da lista de responsáveis escolhida em `responsavel_id` (US-703: "responsável escolhido na lista da Administração"); o do Morador é o nome do usuário. O Morador vê data, texto e responsável de cada resposta (US-702). A **lista** devolve `id`, `titulo`, `status`, `unidade`, `criada_em`, `ultima_interacao_em` e `aguardando_administracao` (`true` quando a última interação é de um Morador ou ainda não há resposta). Sem interação, `ultima_interacao_em` é `null`. No detalhe, `anexos` reúne os arquivos da ocorrência (com `interacao_id` quando vinculados a uma interação), e cada interação também lista os seus.

Regras:

- Morador só vê ocorrências de unidades vinculadas a ele (404 nas outras). A Administração vê todas do condomínio. **Funcionário: 403.**
- **Resolução:** só de `em_aberto` (senão 409, `reason: "ocorrencia_ja_resolvida"`); grava `resolvida_em`, cria a interação `resolucao` e gera o evento de auditoria `ocorrencia.resolver`.
- **Reabertura:** só de `resolvida` (senão 409, `reason: "ocorrencia_nao_resolvida"`); `texto` obrigatório (o que voltou a acontecer), de 1 a 2000 caracteres. Volta a `em_aberto`, limpa `resolvida_em` (o histórico guarda quando foi resolvida), cria a interação `reabertura` e gera o evento `ocorrencia.reabrir`.
- **Como a Administração "é avisada" da reabertura (US-704):** não há tabela de notificações. Proposta: a ocorrência reaberta volta para a fila `status=em_aberto` com `aguardando_administracao = true`, e o painel da Administração (hub) destaca esses itens. Sem e-mail, porque o US-803 só cobre quatro eventos.
- O Morador comenta em qualquer estado (US-704: "enquanto a ocorrência existir"); comentar não muda o status.
- Nenhuma ocorrência é apagada, nem a resolvida (US-703).

Implementação de comentários e reabertura (TASK-63, US-704):

- **Só o Morador** (403 para Funcionário, Administração e ADM), embora a matriz dê `editar` à Administração: responder e resolver continuam sendo dela. Unidade alheia: 404; aba Ocorrências Sem Acesso: 403.
- **Comentário** (201): `texto` de 1 a 2000 caracteres e até 5 `anexos`, com as mesmas regras da abertura (arquivo do condomínio, enviado pela conta, imagem ou MP4). Cada anexo fica ligado à interação (`interacao_id`). Um arquivo que já está na ocorrência não entra de novo (422).
- **Reabertura** (200): só de `resolvida` (senão 409 `ocorrencia_nao_resolvida`); a linha é travada, então duas reaberturas simultâneas geram uma. A ocorrência volta a `em_aberto`, `resolvida_em` volta a nulo, a interação `reabertura` guarda o texto e o evento `ocorrencia.reabrir` é auditado.
- **Fila da Administração.** Depois de um comentário ou de uma reabertura, a última interação é do Morador, então `aguardando_administracao` fica `true` na lista.

## 6. Consultas e cadastros do Morador (encomendas, visitantes e veículos)

### 6.1 Encomendas (US-402)

A leitura da encomenda é do Vitor (US-402), mas o **recurso e os objetos** são os de `portaria.md` (Eduardo). Nada se redefine: o Morador usa `GET /encomendas` e `GET /encomendas/{id}` com a permissão `[Encomendas]`. Dois ajustes **propostos** em `portaria.md`:

1. Aceitar `unidade_id` como filtro e **exigi-lo quando quem chama é o Morador** (a US-402 abre com "seleciona a unidade"; sem o filtro, uma lista mista confunde). Funcionário e Administração continuam sem exigi-lo.
2. A lista do Morador ordena da encomenda mais recente para a mais antiga e traz foto, data e hora, descrição, quem recebeu (`recebimento.funcionario`) e status. É o que `portaria.md` já devolve.

**Implementação (US-402).** `GET /encomendas` aceita `unidade_id` para todos os perfis. Para o Morador, unidade que não é dele dá 404 e aba Encomendas Sem Acesso dá 403; para Funcionário e Administração, unidade de outro condomínio dá 404. O filtro combina com `status` e `busca`. **Ainda opcional:** o front atual da lista do Morador chama sem `unidade_id`, e tornar o parâmetro obrigatório (422 para o Morador, como o item 1 propõe) quebraria essa tela; a mudança é de uma linha no service quando a tela passar a enviar a unidade.

**Período e relatório (US-404, proposta implementada na TASK-63).** A US-404 não tem texto detalhado no repositório, então o relatório segue a menor leitura útil e pode mudar quando a tela for desenhada (TASK-61):

- `GET /encomendas` aceita `data_de` e `data_ate` (datas inclusivas no fuso do condomínio, sobre `registrada_em`; 422 se invertidas) para todos os perfis.
- `GET /encomendas/relatorio` (só Administração; 403 para os demais) aceita `data_de`, `data_ate` e `unidade_id` e devolve `{"periodo": {"de", "ate"}, "totais": {...}, "por_unidade": [...]}`. Os totais e cada unidade trazem `registradas`, `aguardando_retirada`, `entregue_aguardando_confirmacao` e `retirada_confirmada`; `por_unidade` vem da unidade com mais encomendas para a com menos, sem paginação. Unidade de outro condomínio: 404.

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
- A busca por CPF do Morador considera apenas cadastros feitos por moradores. O histórico de visitantes avulsos continua disponível na busca por nome, com CPF omitido.
- Implementação TASK-38 (recorte de visitantes): a aba Visitantes é obrigatória. Qualquer morador ativo da unidade com a aba habilitada consulta, edita (antes da primeira visita) e cancela cadastros da unidade. O cadastro permanece no histórico depois de cancelado. O cancelamento após uma saída é permitido enquanto não houver visita aberta.

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

Todos os campos são obrigatórios na criação. Na edição, `unidade_id` é opcional e, quando enviada, deve corresponder à unidade do cadastro. A **placa** é normalizada pelo servidor (maiúsculas, sem hífen nem espaço) e validada pelo formato brasileiro antigo ou Mercosul, `^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$` (regra 13 do DER). `marca`, `modelo` e `cor` têm de 1 a 40 caracteres.

- Placa repetida **na mesma unidade**, entre veículos ativos: 409 (`reason: "placa_ja_cadastrada_na_unidade"`), regra 14.
- A unidade pode ter até **cinco veículos ativos**. O sexto retorna 409 (`reason: "limite_veiculos"`). Remover um veículo libera uma vaga.
- O cadastro aceita placa repetida em outra unidade. A consulta administrativa retorna `placa_duplicada` quando há outra unidade ativa do mesmo condomínio com a mesma placa ativa. O campo é exclusivo da Administração.
- `remocao` desativa (`ativo = false`, `removido_em` preenchido). A placa pode ser cadastrada de novo depois.
- Funcionário (portaria): consulta `GET /veiculos` do condomínio para conferência no portão, com acesso de leitura (US-505).

### 6.4 Relatórios administrativos (US-506 simplificada, TASK-52)

**Implementado somente este recorte da TASK-52.** Rotas completas:

| Método e rota | Permissão | Resultado |
| --- | --- | --- |
| `GET /api/v1/relatorios/visitantes` | Administração de condomínio ativo + `visitantes:ver` | Uma linha por entrada efetiva registrada |
| `GET /api/v1/relatorios/veiculos` | Administração de condomínio ativo + `veiculos:ver` | Uma linha por cadastro de veículo, inclusive removido |

Morador, Funcionário e ADM da plataforma recebem 403. Sem autenticação: 401.
O condomínio é exclusivamente o do contexto autenticado. Não há filtro livre por
`condominio_id`, nem novas permissões. As consultas operacionais da Portaria permanecem
nas rotas existentes. Não se exige `responsavel_id` nem se cria evento de auditoria de
sucesso por listagem; as negações continuam no mecanismo central de segurança.

Parâmetros comuns de query, todos opcionais:

| Campo | Regra |
| --- | --- |
| `unidade_id` | UUID; sem ele, todas as unidades do condomínio. Aceita unidade inativa. Unidade inexistente ou alheia: mesmo 404 genérico |
| `de`, `ate` | Datas `AAAA-MM-DD` inclusivas em `America/Sao_Paulo`; cada limite pode ser informado sozinho. Período invertido: 422 |
| `page` | Inteiro >= 1, padrão 1; o deslocamento `(page - 1) * page_size` deve caber no `bigint` do PostgreSQL (máximo `2^63 - 1`); acima: 422 |
| `page_size` | Inteiro de 1 a 100, padrão 20 |

Os limites são início de `de` (inclusivo) e início do dia seguinte a `ate` (exclusivo),
calculados no fuso do projeto, inclusive nas transições históricas de horário de verão.
`9999-12-31` é recusada em ambos os limites com 422 para evitar overflow;
`0001-01-01` e `9999-12-30` são aceitas. Parâmetros inválidos ou extras retornam
422 `validation_error`, no envelope comum.

Ambas as respostas usam `{items,total,page,page_size}`. O total respeita todos os filtros;
filtros, contagem e paginação são executados no PostgreSQL. A ordem é data/hora
decrescente (`entrada_em` ou `criado_em`), com desempate por UUID crescente. Página além
do fim devolve `items: []` e mantém o total filtrado.

**Campos dos visitantes:** `id` da visita; `visitante: {id,nome}`;
`unidade: {id,identificacao,bloco,andar}`; `avulso`; `status` (`em_andamento` ou `encerrada`);
`entrada: {em,funcionario:{id,nome}}`; `saida` no mesmo formato ou `null` em visita aberta.
`bloco` e `andar` são nomes, ou `null` quando não disponíveis. Os instantes são ISO 8601
com fuso. Não se expõem CPF, idade, observações, contato, autorização ou evidência bruta.

O período dos visitantes filtra **somente `entrada_em`**, nunca a autorização prevista
ou o contato da Portaria. A saída aparece mesmo após o período consultado. Inclui
avulsos, visitas repetidas do mesmo visitante, cadastros cancelados, unidades inativas
e funcionários posteriormente desligados. Contatos negados, sem resposta e cadastros
sem entrada efetiva não geram linhas. IDs e instantes vêm do registro histórico;
nomes e identificação da unidade vêm dos cadastros atuais. Não existem snapshots
desses nomes no registro de visita; não há reconstrução de nomes anteriores.

**Campos dos veículos:** `id`; `unidade: {id,identificacao,bloco,andar}`; `placa`, `marca`,
`modelo`, `cor`; `ativo`; `criado_em`; `removido_em` (ou `null`); `placa_duplicada` (booleano).
O período filtra **somente `criado_em`**, a data de cadastro. Dados e situação são os
atualmente registrados, inclusive remoção posterior ao período e unidade inativa.
Não há reconstrução de versões anteriores dos dados do veículo.

`placa_duplicada` indica se **hoje a placa possui cadastros ativos em pelo menos duas
unidades ativas distintas do mesmo condomínio**. O cálculo não inclui removidos,
unidades inativas ou outros condomínios, e independe dos filtros de unidade/período.
O indicador também aparece nas linhas históricas da placa: elas não contam como
cadastros ativos e só exibem `true` se existirem duas unidades ativas com a placa ativa.
Remover um dos dois cadastros ou desativar uma das unidades faz o indicador voltar
a `false`, a menos que ainda restem outras duas unidades qualificadas.

Limites intencionais: sem CSV, Excel, PDF, gráficos ou estatísticas; o relatório de
veículos **não representa circulação**, pois não existem registros de entrada/saída
de veículos. Suporte, comunicados e e-mails não integram esta entrega.

Integração futura: o PR #30 altera a busca de CPF de visitantes avulsos, testes e este
contrato; o PR #31 sobrepõe repositories, services, schemas, routers operacionais e
documentação de visitantes/veículos. Os relatórios ficam em arquivos próprios e
reutilizam `RepositorioVisitas.detalhada()`; a consulta de veículos é específica para
históricos e duplicidade atual, seguindo as mesmas regras de ativos da operacional.
Esta entrega não altera endpoints/services/repositories operacionais. A simulação da
revisão integrada não encontrou conflito textual com o PR #30; o PR #31 requer resolução
explícita nos arquivos operacionais, registro de routers e documentação. Nenhuma dessas
branches foi incorporada; a conciliação permanece uma etapa própria.

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
- Veículo: placa fora do formato retorna 422, placa repetida na unidade retorna 409 e placa repetida em outra unidade é aceita, com indicação exclusiva na consulta da Administração. Se dois cadastros disputarem a quinta vaga, apenas um é aceito.

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
| Relatório da Administração | US-506 simplificada implementada na seção 6.4, com indicação de placas duplicadas e sem CSV. A TASK-52 completa permanece fora deste recorte. | Tude e Paulo |
| Cancelar visitante depois da primeira entrada | Com a autorização reutilizável (22/10), o Morador precisa poder **revogar** um cadastro em curso. A US-501 só permite cancelar "antes da entrada". **Proposta:** permitir enquanto não houver visita em andamento. | Vitor e Eduardo |
| `unidade_id` em `GET /encomendas` | Ajuste em `portaria.md` (seção 6.1) | Eduardo e Vitor |
| Anexos de ocorrência | Tipos, tamanhos, quantidade (5) e leitura protegida de vídeo | Eduardo (TASK-26) e Vitor |
| Funcionário nas reservas e ocorrências | A matriz nega o acesso. Confirmar que o porteiro não precisa ver a agenda de áreas comuns | Gabriel |

Nenhuma aprovação de Davi, Matheus ou dos leads foi presumida neste documento. O "pronto quando" da TASK-10 é o contrato e a regra aprovados no portão dos leads.
