# Plano de testes e rastreabilidade — TASK-4

Status: **plano de testes entregue; TASK-4 concluída no Notion por decisão expressa do responsável pelo projeto em 01/11/2026**. Fonte: [TASK-4](https://app.notion.com/3f866650b896811ea0c1e75ca77ed874). Este documento define os testes; não declara que todas as stories foram implementadas, executadas ou aprovadas.

## Cobertura

- [Casos Must](casos-must.md): **31 casos, um por story Must, com 116 critérios da fonte vinculados**. Cada critério recebe identificação CA1, CA2 etc. dentro do caso.
- As 19 stories Should e 2 Could continuam no backlog de planejamento; entram neste arquivo quando forem priorizadas.
- Casos de referência têm passos, resultados esperados, tipo, responsáveis de referência e situação. O vínculo com testes existentes não significa cobertura integral da story.
- O [roteiro da portaria](../portaria/telas.md#roteiro-de-revisão) detalha a prévia navegável. Ele complementa os cenários abaixo e não comprova autorização nem persistência da API.

## Camadas e ferramentas

| Camada | Ferramenta | O que comprova | Limite |
| --- | --- | --- | --- |
| Regras e serviços Python | pytest | Validação, tokens, respostas e decisões isoladas | Mocks não comprovam banco, rede ou política de permissão real |
| API/contexto/PostgreSQL | pytest + FastAPI TestClient + PostgreSQL dedicado | Persistência, constraints e tentativas entre condomínios | O CRUD de itens é exclusivo dos testes; cada módulo real deve repetir os cenários |
| Storage | pytest + MinIO dedicado | Bucket privado, upload, URL assinada, recusa anônima e remoção | Não comprova endpoint autenticado nem vínculo do arquivo à unidade, ainda pendentes |
| Regras da prévia da portaria | Node test runner, `npm test` | Transições e validações de encomendas/visitantes em memória | Não navega no navegador nem chama a API |
| Interface | Roteiro manual no navegador | Formulários, mensagens, estados, teclado e tela estreita | Integração real só é aprovada com backend disponível |
| Qualidade e build | Ruff, Mypy, ESLint, TypeScript e Vite | Padrão, tipos e compilação | Não substitui testes de comportamento |
| Migrações | Alembic + PostgreSQL vazio | Upgrade, coerência com modelos, downgrade e novo upgrade | Rascunhos em `alembic/drafts/` não fazem parte da cadeia ativa |

Playwright/Cypress não são introduzidos nesta entrega; automatizar navegação pode ser decidido quando os fluxos autenticados existirem.

## Massa de teste

Usar somente exemplos fictícios e isolados:

- Condomínios A e B; unidades A/101, A/102 e B/201.
- Morador vinculado apenas a A/101; outro morador ativo da mesma unidade; morador de A/102; morador de B/201; conta sem vínculo.
- Contas de Funcionário, Administração e ADM, respeitando o modelo de contas compartilhadas. Funcionários/responsáveis selecionados nas operações são cadastros distintos da conta autenticada.
- Vínculo/conta/condomínio ativos e desativados; token inválido, expirado, sem condomínio e com versão de sessão antiga.
- Arquivos pequenos permitidos, conteúdo truncado, extensão/MIME incompatíveis e arquivo maior que o limite; nunca documentos reais.

As fixtures atuais criam dados transitórios. A massa completa dos módulos e o seed de demonstração ainda dependem das respectivas migrations; não apresentar esses dados como já disponíveis.

## Execução local — backend

Preparar o Python 3.13 e as dependências conforme o [README principal](../../README.md). Executar a suíte fora do banco de desenvolvimento. Um exemplo de PostgreSQL descartável, em porta própria:

```sh
docker run -d --name condominios-test-db -p 127.0.0.1:55436:5432 -e POSTGRES_USER=ci -e POSTGRES_PASSWORD=ci_local_only -e POSTGRES_DB=condominios_test postgres:17
docker exec condominios-test-db pg_isready -U ci -d condominios_test
```

Aguardar o segundo comando indicar que aceita conexões. Os valores são fictícios e exclusivos do teste; usar outra porta/nome se já estiverem ocupados. No PowerShell, antes de entrar em `backend/`:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://ci:ci_local_only@127.0.0.1:55436/condominios_test'
$env:TEST_DATABASE_URL = $env:DATABASE_URL
cd backend
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m alembic upgrade head
python -m alembic check
python -m pytest -q
```

Para conferir reversibilidade, usar **somente esse banco de teste dedicado**:

```sh
python -m alembic downgrade base
python -m alembic upgrade head
```

Não apontar esses comandos para dados reais ou para o banco usado pela equipe. O CI faz esse ciclo em um PostgreSQL limpo.

## Execução local — storage real

Na raiz, construir a mesma imagem usada pelo CI e iniciar um MinIO separado:

```sh
docker build -t condominios-minio-test infra/minio
docker run -d --name condominios-test-storage -p 127.0.0.1:59010:9000 -e MINIO_ROOT_USER=ci_storage_user -e MINIO_ROOT_PASSWORD=ci_storage_local_only condominios-minio-test
```

Aguardar o health em `http://127.0.0.1:59010/minio/health/live` retornar 200. No PowerShell da suíte:

```powershell
$env:TEST_STORAGE_ENDPOINT = 'http://127.0.0.1:59010'
$env:TEST_STORAGE_PUBLIC_ENDPOINT = 'http://127.0.0.1:59010'
$env:TEST_STORAGE_ACCESS_KEY = 'ci_storage_user'
$env:TEST_STORAGE_SECRET_KEY = 'ci_storage_local_only'
# Em backend/: apenas integração S3, ou suíte completa com TEST_DATABASE_URL definido.
python -m pytest -q -m storage
python -m pytest -q
```

O teste cria/remove somente um bucket aleatório `teste-*`. O primeiro build compila MinIO e pode demorar. Sem variáveis de PostgreSQL/MinIO, os respectivos testes ficam como skip: isso não comprova integração. Ao terminar, parar os dois containers de teste por nome; não remover volumes do ambiente da equipe.

## Execução local — frontend

Em `frontend/`, com Node 24 e dependências instaladas por `npm ci`:

```sh
npm run lint
npm test
npm run build
```

O build inclui typecheck. Os oito testes atuais estão em [model.test.ts](../../frontend/src/features/portaria/model.test.ts).

## Roteiros manuais disponíveis

Executar `npm run dev` em `frontend/` e usar exemplos fictícios. Os roteiros são instruções de execução; esta entrega documental não registra uma nova execução manual.

| ID | Preparação e passos | Resultado esperado | Situação de referência |
| --- | --- | --- | --- |
| M-01 — navegação pública | Abrir `/`, seguir links de acesso/cadastro, retornar e abrir `/status`; verificar teclado | Links chegam às rotas previstas, status apresenta resposta/erro e formulários provisórios continuam sem enviar dados | Executável; login integrado continua pendente |
| M-02 — recebimento | Em `/prototipos/portaria`, tentar receber sem foto; preencher unidade, destinatário, descrição e funcionário; anexar imagem válida | Erro mantém os outros campos; registro válido inicia Aguardando retirada com horário e foto na prévia | Executável na prévia; API/S3/SQL pendentes |
| M-03 — entrega/confirmação | Entregar a outro morador ativo da mesma unidade; tentar confirmar como pessoa diferente; confirmar como recebedor | Entregue, aguardando confirmação até a confirmação exclusiva do recebedor; histórico preservado e sem confirmação automática | Executável na prévia; identidade é controle de demonstração |
| M-04 — visitante com autorização | Buscar por unidade/nome, conferir identidade e autorização, registrar entrada e saída; entrar novamente no período; tentar duas entradas simultâneas | Horários e histórico preservados, autorização reutilizável e segunda entrada simultânea recusada | Executável na prévia |
| M-05 — contato externo | Testar autorização expirada/ausente; registrar Interfone/Telefone com Não autorizou ou Sem resposta; depois testar Autorizou com morador da unidade | Negativa/sem resposta ficam no histórico sem visita; autorização válida permite entrada | Executável na prévia; representação definitiva no DER pendente |
| M-06 — acessibilidade e celular | Repetir M-02/M-05 em 390 × 844, usar Tab e abrir/fechar formulário/diálogo | Sem perda de ações/campos; status legível; foco retorna ao conteúdo; tabelas preservam rolagem interna | Executável; registrar navegador e viewport |
| M-07 — aceite integrado | Executar o CT da story com conta real de teste e APIs do módulo; repetir com perfil/unidade/condomínio sem acesso | Resultado de cada CA confirmado na tela e na API, com persistência e recusa adequada | Bloqueado enquanto o módulo/autorizações não existirem |

## CI e evidências atuais

O [workflow](../../.github/workflows/ci.yaml) roda em push e PR: backend em Python 3.13 com PostgreSQL, frontend em Node 24 e integração S3 com MinIO. Inclui lint, formatação, tipos, migrações e build. A validação do Compose confere sua configuração; não representa, sozinha, uma execução completa em outra máquina.

Referências já observadas antes deste plano: [CI do PR #13](https://github.com/Eduardocin/sistema-gestao-condominios/actions/runs/41310987611), com backend/frontend/storage aprovados; no backend, 192 testes passaram e 1 teste de MinIO foi pulado para execução no job S3. Na validação isolada anterior, com os dois serviços disponíveis, 193 testes passaram. Esses resultados são da versão do PR #13, não execução de todos os casos deste plano.

Rascunhos e testes locais anteriores não versionados não fazem parte dessa contagem nem da entrega.

## Registro de resultados

Copiar a tabela abaixo para a issue/PR da implementação ou anexar ao card no Notion. Davi consolida a rastreabilidade; cada responsável de backend/frontend executa e mantém os testes do seu módulo. A divisão precisa ser confirmada com os leads; os nomes em Casos Must são referências do quadro, não novas atribuições.

| Campo | Preenchimento |
| --- | --- |
| Caso e critérios | CT-US-NNN, CA1/CA2 etc. e M-NN quando aplicável |
| Versão | SHA exato e PR |
| Executor e data | Pessoa que executou e data real |
| Ambiente | Banco/MinIO de teste, navegador/viewport ou job do CI |
| Resultado por critério | Aprovado, Falhou, Bloqueado ou Não executado |
| Evidência | Teste/função, log, captura ou link do CI sem credenciais/URLs assinadas |
| Pendência | Dependência ou decisão necessária, com referência ao card/issue |

A TASK-4 foi encerrada por decisão do responsável pelo projeto. A divisão da execução pode ser alinhada com Davi/leads a cada implementação. A entrega do plano não significa concluir as stories. Teste que falhou ou não foi executado não recebe marca de aprovado.
