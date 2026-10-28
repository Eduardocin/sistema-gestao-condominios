# Plataforma — proposta de contrato REST e serviços transversais (TASK-11)

Status: rascunho para revisão no portão dos leads. Endpoints e funções abaixo **não estão implementados**. Cobre avisos, comunicados do ADM, chamados de suporte, consulta de auditoria, funcionários e responsáveis da Administração, edição da estrutura do prédio e os dois serviços que os outros módulos chamam: **auditoria** e **e-mail assíncrono**.

Convenções comuns (envelope de erro, paginação, ações explícitas, `responsavel_id`, fuso): [convencoes.md](convencoes.md). Modelo de dados: [modelo-de-dados.md](../modelo-de-dados.md), seções 3.2 e 3.5. Permissões: [matriz](../permissoes-e-multitenant.md), seções 7, 9 e 10.

Histórias cobertas: US-801 a US-804, US-901 a US-903, US-1004, US-209, US-210, US-205, US-206 (a parte de leitura da estrutura fica no [núcleo](nucleo.md)).

## Visão geral

| Seção | Conteúdo | Perfis |
| --- | --- | --- |
| 1 | Avisos do condomínio | Administração escreve; Morador e Funcionário leem |
| 2 | Comunicados da plataforma | ADM escreve; Administração lê |
| 3 | Chamados de suporte | Administração abre; ADM atende |
| 4 | Auditoria: serviço `registrar_acao`, catálogo de ações e consulta | Todos os módulos chamam; só o ADM consulta |
| 5 | Funcionários, responsáveis e conta compartilhada | Administração |
| 6 | E-mail assíncrono | Interno; ADM acompanha os envios |
| 7 | Edição da estrutura do prédio | Administração |

## 1. Avisos do condomínio (US-801, US-802)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /avisos` | Morador e Funcionário: só vigentes. Administração: todos | `situacao` (só Administração: `vigentes`, `agendados`, `encerrados`, `todos`; padrão `vigentes`), paginação | 200, lista |
| `GET /avisos/{id}` | Mesmo escopo | — | 200, objeto |
| `POST /avisos` | Administração | JSON abaixo | 201, objeto |
| `PUT /avisos/{id}` | Administração | JSON abaixo | 200, objeto |
| `POST /avisos/{id}/encerramento` | Administração | `{"responsavel_id": "UUID"}` | 200, objeto |

```json
{
  "titulo": "Falta de água programada",
  "texto": "Haverá interrupção do abastecimento no dia 20, das 9h às 14h.",
  "importante": true,
  "inicio_em": "2026-11-18T09:00:00-03:00",
  "fim_em": "2026-11-20T14:00:00-03:00",
  "responsavel_id": "UUID"
}
```

`titulo` de 1 a 120 caracteres, `texto` de 1 a 2000, `fim_em` > `inicio_em` (regra 17 do DER). A US fala em "data de início e data de fim"; o contrato guarda **timestamps**, e o front converte as datas escolhidas (início às 00:00, fim às 23:59 no fuso do condomínio). `responsavel_id` é obrigatório em `POST`, `PUT` e `encerramento` ("a publicação registra o responsável").

Objeto de aviso:

```json
{
  "id": "UUID",
  "titulo": "Falta de água programada",
  "texto": "...",
  "importante": true,
  "inicio_em": "2026-11-18T12:00:00Z",
  "fim_em": "2026-11-20T17:00:00Z",
  "encerrado_em": null,
  "situacao": "vigente",
  "unidade": null,
  "publicado_por": {"id": "UUID", "nome": "Carlos (síndico)"}
}
```

`situacao` é derivada, nesta precedência: `encerrado` (tem `encerrado_em`), `expirado` (`fim_em` já passou), `agendado` (`inicio_em` no futuro) e `vigente`. `publicado_por` só aparece para a Administração.

Regras:

- **Vigente** é `inicio_em <= agora < fim_em` e `encerrado_em` nulo. Aviso expirado "some sozinho" porque a consulta filtra por data, sem nenhum job.
- Ordenação do hub: **importantes primeiro**, depois `inicio_em` decrescente. O hub do Funcionário usa a mesma rota e o mesmo componente (US-802).
- **Avisos por unidade.** O DER tem `avisos.unidade_id` para avisar uma unidade de reserva cancelada (US-605, US-602). Esses avisos **são criados só pelo servidor**, pela função interna abaixo, e o corpo de `POST /avisos` rejeita `unidade_id`. O Morador vê os avisos gerais e os das **suas** unidades; o Funcionário só os gerais. A Administração vê todos, com o campo `unidade` preenchido nos automáticos; esses não podem ser editados (`PUT` retorna 409, `reason: "aviso_automatico"`).
- `PUT` e `encerramento` só valem para aviso não encerrado e não expirado (senão 409, `reason: "aviso_encerrado"`). Encerrar não apaga: grava `encerrado_em`.
- Auditoria: `aviso.publicar`, `aviso.editar` e `aviso.encerrar`.

**Função interna** usada por [convivencia.md](convivencia.md) (cancelamento de reserva e bloqueio de data):

```python
def publicar_para_unidade(
    session: Session, *, ctx: ContextoRequisicao, unidade_id: UUID,
    titulo: str, texto: str, responsavel_id: UUID, importante: bool = True,
    dias_de_exibicao: int = 7,
) -> UUID: ...
```

Cria o aviso na **mesma transação** do chamador (sem `commit`). Vigência: do momento atual até `dias_de_exibicao` dias depois (proposta: 7).

## 2. Comunicados da plataforma (US-804, Should, Sprint 3)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `POST /plataforma/comunicados` | ADM | `{"titulo": "...", "texto": "..."}` | 201, objeto |
| `GET /plataforma/comunicados` | ADM | paginação | 200, lista, com `total_destinatarios` |
| `GET /plataforma/comunicados/{id}` | ADM | — | 200, objeto com a lista de condomínios destinatários |
| `GET /comunicados` | Administração | paginação | 200, lista dos comunicados **enviados ao seu condomínio** |

`titulo` de 1 a 120 caracteres, `texto` de 1 a 4000. O comunicado "vai para todas as Administrações de uma vez" e "aparece no hub da Administração".

**Destinatários.** O DER ainda não representa os destinos (seção 7 do `modelo-de-dados.md`), e a matriz limita a Administração aos comunicados "que lhe foram enviados". **Proposta:** uma tabela `comunicado_destinatarios (comunicado_id, condominio_id)`, preenchida **no momento do envio** com todos os condomínios `ativo` naquele instante. Isso registra o envio (critério de aceite), impede que um condomínio criado depois receba comunicados antigos e responde à restrição da matriz sem ambiguidade. O `GET /comunicados` filtra por essa tabela, pelo `condominio_id` do token.

A matriz dá ao ADM "V C D" em comunicados, mas `comunicados` não tem coluna de desativação. Esta proposta **não cria `D`** no MVP (ver pendências). Auditoria: `comunicado.enviar`. Sem e-mail: o US-803 só cobre quatro eventos.

## 3. Chamados de suporte (US-901, US-902, Should, Sprint 3)

Status: `aberto`, `em_atendimento`, `encerrado`.

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `POST /chamados` | Administração | `{"titulo": "...", "descricao": "...", "anexos": ["UUID"]}` | 201, chamado |
| `GET /chamados` | Administração (só do seu condomínio) | `status`, paginação | 200, lista |
| `GET /chamados/{id}` | Administração (só do seu condomínio) | — | 200, chamado com mensagens |
| `POST /chamados/{id}/mensagens` | Administração | `{"texto": "..."}` | 201, mensagem |
| `GET /plataforma/chamados` | ADM | `status`, `condominio_id`, `de`, `ate`, `busca`, paginação | 200, fila |
| `GET /plataforma/chamados/{id}` | ADM | — | 200, chamado com mensagens |
| `POST /plataforma/chamados/{id}/mensagens` | ADM | `{"texto": "..."}` | 201, mensagem |
| `POST /plataforma/chamados/{id}/encerramento` | ADM | `{}` | 200, chamado |

`titulo` de 1 a 120 caracteres, `descricao` de 1 a 4000, até 5 anexos (o DER liga os anexos ao chamado, não à mensagem). Mensagem de 1 a 4000 caracteres.

```json
{
  "id": "UUID",
  "titulo": "Não consigo cadastrar a estrutura",
  "descricao": "...",
  "status": "em_atendimento",
  "condominio": {"id": "UUID", "nome": "Residencial Aurora"},
  "aberto_por": {"id": "UUID", "nome": "Carlos (síndico)"},
  "atendido_por": {"id": "UUID", "nome": "Equipe da plataforma"},
  "criado_em": "2026-11-10T14:03:00Z",
  "encerrado_em": null,
  "anexos": ["UUID"],
  "mensagens": [
    {"id": "UUID", "autor": {"tipo": "administracao", "nome": "Carlos (síndico)"}, "texto": "...", "em": "2026-11-10T14:05:00Z"}
  ]
}
```

Transições:

| De | Para | Quem e como |
| --- | --- | --- |
| (novo) | `aberto` | Administração abre |
| `aberto` | `em_atendimento` | Primeira mensagem do ADM; grava `atendido_por_usuario_id`. Auditoria `chamado.atender` |
| `aberto` ou `em_atendimento` | `encerrado` | ADM, por `encerramento`; grava `encerrado_em`. Auditoria `chamado.encerrar` |

Mensagem em chamado `encerrado` retorna 409 (`reason: "chamado_encerrado"`); a Administração abre outro chamado. O histórico de atendimento nunca é alterado. A Administração só vê chamados do **próprio** condomínio (404 nos demais). O ADM vê todos (escopo de plataforma). A fila padrão do ADM lista os não encerrados do **mais antigo para o mais recente** (quem espera há mais tempo primeiro); com `status=encerrado`, do mais recente para o mais antigo. O campo `condominio` só aparece nas rotas do ADM.

## 4. Auditoria (US-1004, US-903)

### 4.1 O serviço único que os módulos chamam

A US-1004 exige "um mecanismo único que os outros módulos chamam". Interface proposta, no módulo `auditoria`:

```python
@dataclass(frozen=True)
class ResponsavelRef:
    tipo: Literal["administracao", "funcionario"]
    id: UUID

def registrar_acao(
    session: Session,
    *,
    ctx: ContextoRequisicao,            # usuario_id, condominio_id, perfil, ip: vêm da autorização central
    acao: str,                          # "grupo.verbo", do catálogo da seção 4.2
    recurso_tipo: str,                  # "reserva", "condominio", "unidade"...
    recurso_id: UUID | None,
    responsavel: ResponsavelRef | None = None,
    antes: Mapping[str, Any] | None = None,
    depois: Mapping[str, Any] | None = None,
) -> None: ...

def registrar_evento_seguranca(
    *, acao: str, usuario_id: UUID | None, condominio_id: UUID | None,
    ip: str | None, recurso_tipo: str | None = None, recurso_id: UUID | None = None,
    detalhe: Mapping[str, Any] | None = None,
) -> None: ...
```

Regras de uso:

1. **Mesma transação.** `registrar_acao` faz `session.add` + `flush`, **sem `commit`** (quem commita é o service, como em `architecture.md`). A ação e o evento são gravados juntos ou nenhum dos dois. Esquecer a chamada é o erro mais provável, por isso o checklist da matriz (seção 13) já pede a chamada em toda ação crítica.
2. **Eventos de segurança em transação própria.** `login falho`, `acesso negado (403)` e `404 cross-tenant` acontecem **em requisições que falham** e fazem rollback; se usassem a sessão da requisição, o evento sumiria junto. `registrar_evento_seguranca` abre uma sessão curta e independente, faz o commit dela e nunca propaga erro para a requisição (falha de auditoria de segurança vai para o log, não derruba a resposta de 403).
3. **Responsável.** Nas ações da Administração, `responsavel` é obrigatório e o serviço **valida** que o ID pertence ao condomínio do contexto e está ativo, copiando o **nome** para `responsavel_nome` (o nome fica gravado mesmo que a lista mude depois). Para ações do Funcionário, `ResponsavelRef(tipo="funcionario")`. A conta autenticada (`usuario_id`) é gravada sempre.
4. **`antes` e `depois` guardam só o que mudou**, como dicionários simples. O serviço **remove ou mascara** campos sensíveis antes de gravar: `senha`, `senha_hash`, `token`, `token_hash`, `codigo` (chave de acesso; grava-se o ID da chave, nunca o código) e `documento` (CPF/CNPJ aparece mascarado, `***.456.789-**`). A lista de campos sensíveis é uma constante testada.
5. `ip` e `criado_em` vêm do servidor. Nada disso é aceito do cliente.
6. **Um evento por ação lógica.** Aprovar um condomínio gera **um** evento `condominio.aprovar` (com `depois: {"chaves_geradas": 38}`), não 38. Em operações em lote, como o bloqueio de data que cancela reservas, cada reserva cancelada tem o seu `reserva.cancelar` mais o `area.bloquear`; isso está dito em [convivencia.md](convivencia.md).
7. A tabela é só de inserção: não existe `UPDATE` nem `DELETE` nem rota para eles, e o trigger do DER (regra 21) recusa os dois no banco.

### 4.2 Catálogo de ações e quem chama

Formato `grupo.verbo`, em minúsculas. Cobre a lista da seção 10 da matriz, e é a tabela para combinar com todos os donos de módulo (último item do "O que fazer" da TASK-11).

| Dono | Ações |
| --- | --- |
| Gabriel (acesso e autorização) | `permissao_aba.alterar`, `seguranca.login_falho`, `seguranca.acesso_negado`, `seguranca.acesso_cross_tenant` |
| Paulo (condomínio, chaves, vínculos) | `condominio.enviar` *(proposta: cadastro inicial)*, `condominio.reenviar`, `condominio.aprovar`, `condominio.rejeitar` (com motivo), `condominio.desativar`, `condominio.reativar`, `condominio.editar`, `chave.gerar`, `chave.regenerar`, `chave.revogar`, `seguranca.chave_invalida` *(proposta: tentativas erradas, US-301)*, `vinculo.aprovar`, `vinculo.rejeitar`, `vinculo.desfazer`, `proprietario.editar` |
| Vitor (convivência) | `reserva.cancelar`, `area.bloquear`, `ocorrencia.resolver`, `ocorrencia.reabrir` |
| Eduardo (portaria) | `encomenda.entregar`, `encomenda.confirmar` |
| Tude (plataforma e pessoas) | `estrutura.editar`, `funcionario.cadastrar`, `funcionario.editar`, `funcionario.desativar`, `responsaveis.alterar`, `conta_compartilhada.trocar_acesso`, `aviso.publicar`, `aviso.editar`, `aviso.encerrar`, `comunicado.enviar`, `chamado.atender`, `chamado.encerrar` |

`area.bloquear`, `ocorrencia.reabrir`, `aviso.encerrar` e as duas `seguranca.*` marcadas como proposta não estão literalmente na matriz, mas decorrem dos itens "bloquear data", "alterar status de ocorrência" e "publicar ou editar aviso". Confirmar na revisão.

### 4.3 Consulta (US-903)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /plataforma/auditoria` | ADM | `condominio_id`, `de`, `ate` (datas, fuso do condomínio), `acao` (valor exato ou prefixo `reserva.`), `usuario_id`, `recurso_tipo`, `recurso_id`, paginação | 200, lista |

```json
{
  "id": 1021,
  "criado_em": "2026-11-10T14:03:00Z",
  "acao": "condominio.aprovar",
  "condominio": {"id": "UUID", "nome": "Residencial Aurora"},
  "usuario": {"id": "UUID", "nome": "Equipe da plataforma"},
  "responsavel_nome": null,
  "perfil": "plataforma",
  "recurso_tipo": "condominio",
  "recurso_id": "UUID",
  "antes": {"status": "pendente"},
  "depois": {"status": "ativo", "chaves_geradas": 38},
  "ip": "203.0.113.10"
}
```

Ordem: `id` decrescente (o `id` é `bigint` de inserção). **A rota é só de leitura**: sem `PUT`, `PATCH` nem `DELETE`. Nenhum outro perfil acessa a auditoria (matriz); a única exceção proposta é o histórico de funcionários (seção 5). Registros sem condomínio (plataforma, login falho) têm `condominio: null`.

## 5. Funcionários, responsáveis e conta compartilhada (US-209, US-210)

### 5.1 Funcionários (nomes da portaria, sem login)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /funcionarios` | Funcionário: só nomes ativos (`id` e `nome`). Administração: todos | Administração: `ativo`, `busca`, paginação | 200, lista |
| `GET /funcionarios/{id}` | Administração | — | 200, objeto |
| `POST /funcionarios` | Administração | JSON abaixo | 201, objeto |
| `PUT /funcionarios/{id}` | Administração | JSON abaixo | 200, objeto |
| `POST /funcionarios/{id}/desligamento` | Administração | `{"responsavel_id": "UUID"}` | 200, objeto com `ativo = false` |
| `GET /funcionarios/{id}/historico` | Administração | paginação | 200, eventos de cadastro e alteração |

```json
{
  "nome": "João da Silva",
  "funcao": "porteiro",
  "telefone": "11987654321",
  "email": "joao@exemplo.com",
  "foto_arquivo_id": null,
  "responsavel_id": "UUID"
}
```

Obrigatórios: `nome` (1 a 120), `funcao` (`porteiro` ou `seguranca`, CHECK do DER), `telefone` (só dígitos, 10 ou 11) e `email` (minúsculas). `foto_arquivo_id` é opcional (US-209). `responsavel_id` é obrigatório em escrita e desligamento. Não gera login: o acesso à portaria é pela conta compartilhada (5.3).

- **Desligado** deixa de aparecer em `GET /funcionarios` do Funcionário e da lista padrão da Administração (`ativo=true`), mas continua nos registros antigos (encomendas, visitas, auditoria). Grava `ativo = false` e `desligado_em`. Desligar de novo retorna 409.
- Os formulários da portaria (`portaria.md`) já consomem `GET /portaria/funcionarios`; esta rota é a origem da mesma lista. Eduardo e Tude decidem se `/portaria/funcionarios` vira apelido de `/funcionarios` ou se uma das duas some.
- **Histórico.** A US-209 pede "histórico de quem cadastrou ou alterou". O histórico vem de `registros_auditoria` (`funcionario.cadastrar`, `.editar`, `.desativar`) filtrado por `recurso_id`, devolvendo só `acao`, `criado_em`, `responsavel_nome` e `usuario` (sem `antes`/`depois`). Como a matriz nega a auditoria à Administração, esta rota é **uma exceção explícita** a aprovar pelo Gabriel (pendências).
- Auditoria: `funcionario.cadastrar`, `funcionario.editar`, `funcionario.desativar`.

### 5.2 Responsáveis pela Administração (US-210, Should, Sprint 3)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /responsaveis-administracao` | Administração | `ativo` (padrão `true`) | 200, lista (`id`, `nome`, `ativo`) |
| `POST /responsaveis-administracao` | Administração | `{"nome": "Carlos (síndico)"}` | 201, objeto |
| `PUT /responsaveis-administracao/{id}` | Administração | `{"nome": "..."}` | 200, objeto |
| `POST /responsaveis-administracao/{id}/desativacao` | Administração | `{}` | 200, objeto |

Nome de 1 a 100 caracteres, único entre os ativos do condomínio ignorando maiúsculas (proposta). Essa lista alimenta o campo `responsavel_id` de **todas** as ações da Administração.

Há um ciclo a evitar: a lista começa vazia e as ações exigem um responsável da lista. Por isso **gerir a própria lista é a única ação da Administração que não recebe `responsavel_id`**; a alteração é auditada (`responsaveis.alterar`) só com a conta autenticada. O front deve orientar a cadastrar ao menos um responsável antes da primeira ação que exija `responsavel_id`, inclusive para corrigir a estrutura durante o cadastro do condomínio; enquanto a lista estiver vazia, essas ações retornam 422 (`validation_error`).

### 5.3 Conta compartilhada de Funcionários (US-210)

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /conta-funcionarios` | Administração | — | 200, `{"login": "...", "atualizada_em": "..." }` ou 404 se não existe |
| `PUT /conta-funcionarios` | Administração | `{"login": "...", "senha": "...", "responsavel_id": "UUID"}` | 200, mesmo formato |

`PUT` cria a conta se não existir e a troca se existir. A conta é um `usuario` comum com um `vinculos_condominio` de perfil `funcionario` (decisão 3 do DER). **A senha nunca volta numa resposta.** Trocar login ou senha **incrementa `sessao_versao`**, derrubando as sessões ativas da conta imediatamente (`sv` do token, matriz seção 4). Auditoria: `conta_compartilhada.trocar_acesso`, sem a senha em `antes`/`depois`. O `login` é um e-mail, assumido pelo DER; se a equipe decidir por nome de usuário, só o formato do campo muda.

## 6. E-mail assíncrono (US-803, Should, Sprint 3)

### 6.1 Eventos cobertos

| `evento` | Disparado por | Destinatário |
| --- | --- | --- |
| `recuperacao_senha` | Gabriel (US-102) | O e-mail da conta que pediu |
| `condominio_aprovado` | Paulo (US-203) | A conta da Administração que enviou o cadastro |
| `encomenda_registrada` | Eduardo (US-401) | O usuário do destinatário da encomenda |
| `reserva_cancelada` | Vitor (US-605, US-602) | O morador que fez a reserva |

Só e-mail. Não há WhatsApp, SMS nem push no MVP (decisão do escopo).

### 6.2 Interface para os módulos

```python
class EventoEmail(StrEnum):
    RECUPERACAO_SENHA = "recuperacao_senha"
    CONDOMINIO_APROVADO = "condominio_aprovado"
    ENCOMENDA_REGISTRADA = "encomenda_registrada"
    RESERVA_CANCELADA = "reserva_cancelada"

def enfileirar_email(
    session: Session, *, evento: EventoEmail, destinatario: str,
    condominio_id: UUID | None, recurso_tipo: str, recurso_id: UUID,
) -> UUID: ...   # devolve envios_email.id; sem commit
```

Como funciona, em quatro passos:

1. O módulo chama `enfileirar_email` **dentro da transação da operação principal**. A linha entra em `envios_email` com `status = 'pendente'`. Se a operação falhar e der rollback, o e-mail some junto; se der certo, o e-mail está garantido na fila (padrão "outbox").
2. Depois do `commit`, a rota agenda o envio com `BackgroundTasks` do FastAPI; o envio roda **depois de a resposta sair**, sem esperar o SMTP para responder. A tarefa usa uma sessão própria do banco, não a sessão encerrada da requisição. Não há Redis nem Celery (decisão do ADR 0001).
3. A tarefa monta o corpo **a partir do banco** (pelo `recurso_tipo` e `recurso_id`), envia por SMTP e marca `enviado` e `enviado_em`. Em erro, incrementa `tentativas`, grava `ultimo_erro` (sem dados sensíveis) e tenta de novo até 3 vezes, com intervalos curtos (proposta: 30 s e 2 min); esgotadas, `status = 'falhou'`. **A falha do e-mail nunca desfaz nem bloqueia a operação principal** (critério de aceite).
4. Quem acompanha e reenvia é o ADM (6.3).

O destinatário vem do banco, nunca de um campo livre do cliente. O corpo do e-mail não inclui segredos além do necessário ao evento (o link de recuperação de senha é o único).

**Pontos de atenção:**

- **Recuperação de senha não se reenvia.** O link contém um token que só existe em texto no instante do envio (o banco guarda `token_hash`). Um reenvio manual exigiria gerar outro token; por isso `reenvio` de `recuperacao_senha` retorna 409 (`reason: "reenvio_nao_permitido"`) e a pessoa pede de novo. Como o corpo é montado na hora do envio e não no `enfileirar_email`, o token **não é gravado** em `envios_email`; ele é gerado pelo service de recuperação e entregue à tarefa em memória.
- **Envios interrompidos ao reiniciar a API.** Para o MVP, a API roda em **uma instância com um worker**. Antes de aceitar novas requisições, a inicialização muda **todos** os envios ainda `pendente` para `falhou`, com `ultimo_erro = "envio_interrompido_por_reinicio"`, preservando `tentativas`. Inclui envios recentes: não há corte de 5 minutos, pois a tarefa do processo anterior já não existe. O ADM pode reenviar esses registros pela rota da seção 6.3, exceto `recuperacao_senha`: nesse caso o token em memória foi perdido, e a pessoa faz uma nova solicitação pelo fluxo normal. O token em texto nunca vai para o banco ou para o log. Se a atualização inicial falhar, a API não começa a atender; o erro fica no log para correção. Esta estratégia de inicialização precisa ser revista antes de usar múltiplos workers ou réplicas, para não marcar como interrompido um envio de outro processo ativo.
- **Limite do envio por SMTP.** Se o SMTP aceitar a mensagem e a API cair antes de gravar `enviado`, um reenvio manual pode duplicá-la. O MVP não promete entrega exatamente uma vez.

### 6.3 Acompanhamento e reenvio

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `GET /plataforma/envios-email` | ADM | `status`, `evento`, `condominio_id`, `de`, `ate`, paginação | 200, lista |
| `POST /plataforma/envios-email/{id}/reenvio` | ADM | `{}` | 202, envio com `status = 'pendente'` |

Item: `id`, `evento`, `destinatario` (mascarado: `a***@exemplo.com`), `status`, `tentativas`, `ultimo_erro`, `criado_em`, `enviado_em`. Só `falhou` pode ser reenviado (senão 409), incluindo os interrompidos que a inicialização marcou dessa forma. `recuperacao_senha` sempre retorna 409 (`reason: "reenvio_nao_permitido"`), mesmo em `falhou`. O reenvio muda o status para `pendente`, zera `tentativas` e limpa `ultimo_erro` na mesma transação; só depois do commit agenda a tarefa. Essa mudança é condicional ao status ainda ser `falhou`, para dois pedidos de reenvio não agendarem a mesma mensagem: um recebe 202 e o outro 409.

A matriz não tem linha para esses envios, e o DER guarda só o destino, não o recurso. Ambos estão nas pendências.

### 6.4 Configuração (proposta para o Davi)

Variáveis no `.env.example`: `EMAIL_BACKEND` (`smtp` ou `console`), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`. Em desenvolvimento e nos testes, `console` escreve o e-mail no log em vez de enviar; um serviço Mailpit no `compose.yaml` seria opcional. Nada de credencial real no repositório.

## 7. Edição da estrutura do prédio (US-205, Should, Sprint 3)

A **leitura** da árvore (`GET /condominio/estrutura`) e o cadastro inicial pelo assistente estão no [núcleo](nucleo.md). Aqui, a edição depois do cadastro:

| Método e rota | Permissão | Entrada | Sucesso |
| --- | --- | --- | --- |
| `POST /estrutura/blocos` | Administração | `{"nome": "Bloco C", "responsavel_id": "UUID"}` | 201, bloco |
| `PUT /estrutura/blocos/{id}` | Administração | `{"nome": "...", "responsavel_id": "UUID"}` | 200, bloco |
| `POST /estrutura/blocos/{id}/andares` | Administração | `{"nome": "3º andar", "ordem": 3, "responsavel_id": "UUID"}` | 201, andar |
| `PUT /estrutura/andares/{id}` | Administração | `{"nome": "...", "ordem": 3, "responsavel_id": "UUID"}` | 200, andar |
| `POST /estrutura/andares/{id}/unidades` | Administração | `{"identificacao": "301", "responsavel_id": "UUID"}` | 201, unidade |
| `PUT /estrutura/unidades/{id}` | Administração | `{"identificacao": "...", "responsavel_id": "UUID"}` | 200, unidade |
| `POST /estrutura/{tipo}/{id}/desativacao` | Administração | `{"responsavel_id": "UUID"}` (com `tipo` = `blocos`, `andares` ou `unidades`) | 200, item com `ativo = false` |
| `POST /estrutura/{tipo}/{id}/reativacao` | Administração | `{"responsavel_id": "UUID"}` | 200, item com `ativo = true` |

Regras:

- **Responsável obrigatório nas oito operações de escrita acima.** `responsavel_id` identifica um responsável ativo da Administração no condomínio do contexto. Ausente ou inválido no formato: 422; inexistente, inativo ou de outro condomínio: 404 genérico. O service valida antes de alterar a estrutura e passa `ResponsavelRef(tipo="administracao", id=responsavel_id)` para `registrar_acao`, na mesma transação. A auditoria preserva o nome e a identidade da conta autenticada. O responsável deve estar cadastrado pela seção 5.2 também quando a estrutura for corrigida em condomínio pendente ou rejeitado; a gestão dessa lista precisa estar liberada no mesmo fluxo de cadastro.
- Nomes únicos: bloco no condomínio, andar no bloco, unidade no andar (regra 18 do DER). Repetir retorna 409 (`reason: "nome_duplicado"`). Nome de 1 a 50 caracteres. "101" pode existir em blocos diferentes.
- **Desativar unidade:** retorna 409 (`reason: "unidade_com_vinculo_ativo"`) se houver morador vinculado ativo (matriz: "não remove unidade com vínculo"). Sem vínculo ativo, a unidade é desativada, **nunca apagada**, e seus registros antigos (encomendas, reservas, ocorrências) continuam. A chave de acesso vigente da unidade é **revogada** na mesma transação, para ninguém se vincular a uma unidade desativada.
- **Desativar andar ou bloco:** só se todas as suas unidades já estiverem desativadas (409, `reason: "estrutura_com_unidades_ativas"`).
- **Unidade nova em condomínio `ativo`** recebe uma chave de acesso gerada na hora, pelo serviço de chaves do núcleo.
- Uma alteração por requisição gera **um** evento `estrutura.editar`, com `antes` e `depois` só dos campos mudados.
- **Estado do condomínio.** A regra R7 diz que em `pendente` e `rejeitado` a Administração só vê e corrige o cadastro. Corrigir o cadastro inclui a estrutura (US-204), então estas rotas valem em `pendente`, `rejeitado` e `ativo`, e retornam 403 em `desativado`. A dependência de autorização precisa tratar essas rotas como "fluxo de cadastro" (pendências).
- Funcionário lê a estrutura só com a identificação das unidades; Morador não usa estas rotas (matriz).

Edição dos dados do condomínio (nome, CNPJ, endereço, logo, US-206) e a lista "alternar entre prédios" estão no [núcleo](nucleo.md), seção 4, porque são do mesmo recurso do cadastro.

## 8. Casos obrigatórios de teste

- **Auditoria:** cada ação do catálogo gera exatamente um evento com `usuario_id`, perfil, condomínio, ação, recurso, `antes`/`depois`, IP e hora do servidor; ação feita pela Administração sem `responsavel_id` falha com 422 e **não** grava nada; `responsavel_id` de outro condomínio falha com 404; falha da transação da operação não deixa evento órfão (rollback); um 403 gera `seguranca.acesso_negado` mesmo com o rollback da requisição; `senha_hash`, `token_hash` e código de chave **nunca** aparecem em `antes`/`depois`; `UPDATE` e `DELETE` em `registros_auditoria` falham no banco.
- **Avisos:** só vigentes aparecem; aviso importante vem antes; expirado some sem job; aviso de unidade não aparece para outra unidade nem para o Funcionário; `unidade_id` no corpo do `POST` é rejeitado; editar aviso automático retorna 409.
- **Comunicados:** o condomínio criado depois do envio **não** vê o comunicado antigo; Administração de outro condomínio não vê.
- **Chamados:** Administração de outro condomínio recebe 404; mensagem em chamado encerrado retorna 409; a primeira resposta do ADM move para `em_atendimento` uma única vez.
- **Funcionários:** desligado some da lista do Funcionário e permanece em registros antigos; Funcionário não acessa `POST /funcionarios`.
- **Conta compartilhada:** trocar a senha derruba a sessão ativa (a requisição seguinte com o token antigo retorna 401); a senha não aparece em nenhuma resposta nem no log.
- **E-mail:** com o SMTP falhando, a operação principal termina com sucesso e o envio fica `falhou`; rollback da operação não deixa e-mail na fila; simular reinício com envios `pendente` recentes e antigos, todos devem ficar `falhou` com `envio_interrompido_por_reinicio`, sem perder o contador de tentativas; um envio já `enviado` permanece intacto; a inicialização roda antes de aceitar requisições e falha se não conseguir atualizar os interrompidos; o ADM consegue reenviar um interrompido comum; dois reenvios simultâneos produzem um 202, um 409 e uma única tarefa agendada; `recuperacao_senha` interrompida não é reenviável e exige nova solicitação; token em texto não aparece no banco nem no log; o corpo nunca contém dados de outro condomínio.
- **Estrutura:** parametrizar as oito operações: sem `responsavel_id` ou com formato inválido retorna 422; responsável inexistente, inativo ou de outro condomínio retorna 404, sem alteração nem auditoria de sucesso; com responsável válido a operação e um evento `estrutura.editar` são gravados juntos; falha da auditoria reverte a alteração; em condomínio pendente ou rejeitado, é possível cadastrar o responsável antes de corrigir a estrutura; nome duplicado retorna 409; desativar unidade com morador ativo retorna 409; chave revogada ao desativar; Funcionário e Morador recebem 403 nas escritas.

## 9. Pendências e responsáveis

| Tema | Decisão ou alinhamento necessário | Quem |
| --- | --- | --- |
| Destinatários dos comunicados | Aprovar `comunicado_destinatarios` (seção 2). Fecha a pendência da seção 7 do DER. | Davi e Tude |
| `D` em comunicados | A matriz dá "D" ao ADM, mas `comunicados` não tem coluna de desativação. Sem coluna, sem a ação; com coluna (`desativado_em`), `POST .../desativacao`. | Gabriel e Davi |
| Colunas de `envios_email` | Falta guardar **o que** foi enviado: **proposta** de `recurso_tipo` e `recurso_id`, para montar o corpo no reenvio e achar o envio pelo recurso. | Davi e Tude |
| Matriz: envios de e-mail | Nova linha "Envios de e-mail": ADM `V E (P)`. A matriz não tem esse módulo. | Gabriel |
| Histórico de funcionários | Exceção à regra "auditoria só do ADM" (seção 5.1) | Gabriel |
| Rotas de cadastro em condomínio não ativo | A dependência de autorização deve liberar as rotas de estrutura, cadastro e gestão dos responsáveis (para fornecer `responsavel_id`) em `pendente` e `rejeitado` (R7) | Gabriel |
| `/portaria/funcionarios` | Manter ou unificar com `/funcionarios` | Eduardo e Tude |
| Login da conta compartilhada | E-mail (assumido) ou nome de usuário | Gabriel e Paulo |
| Recuperação de envios interrompidos | Implementar a inicialização da seção 6.2: marcar pendentes como falhos antes de atender, com reenvio manual dos eventos comuns. Recuperação de senha exige nova solicitação. MVP com uma instância e um worker. | Tude e Gabriel |
| Servidor SMTP | Provedor para produção/demo e variáveis no `.env.example` | Davi |
| Integração com os donos de módulo | Cada dono confirma as ações do catálogo da seção 4.2 e chama `registrar_acao`; combinar numa reunião curta | Todos |
| TASK-11 em andamento | O card está `Em andamento` com Tude. Este documento é uma proposta de base: Tude compara com o que já escreveu e decide o que adotar. | Tude |

Nenhuma aprovação de outro integrante ou dos leads foi presumida. O "pronto quando" da TASK-11 é o contrato aprovado e a interface da auditoria combinada com o grupo.
