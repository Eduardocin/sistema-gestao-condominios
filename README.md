# Gestão de Condomínios

[![Quality](https://github.com/Eduardocin/sistema-gestao-condominios/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/Eduardocin/sistema-gestao-condominios/actions/workflows/ci.yaml)

Projeto acadêmico da disciplina Integração e Evolução de Sistemas de Informação (IESI). A plataforma reunirá cadastros de condomínios, unidades e usuários, encomendas, visitantes, reservas, ocorrências, avisos e auditoria.

Esta entrega cria a fundação: API com health check, modelos estruturais e migração, frontend com indicador de conexão, ambiente local e verificações de qualidade. Autenticação e fluxos de negócio ficam para as próximas sprints.

**Primeira vez no projeto?** Siga o [Guia de primeira execução](#guia-de-primeira-execução) do início ao fim. Cada etapa termina com uma verificação; só avance quando ela passar. Se algo falhar, consulte [Solução de problemas](#solução-de-problemas).

## Stack e arquitetura

- Frontend: React 19, TypeScript, Vite 8, React Router 7 e Axios.
- Backend: Python 3.12/3.13, FastAPI, Pydantic v2, SQLAlchemy 2.x síncrono, Alembic, Uvicorn e psycopg 3.
- Banco: PostgreSQL 17 via Docker Compose, com volume persistente e health check.
- Qualidade: Pytest, Ruff, Mypy, ESLint 10, TypeScript e GitHub Actions.

Monorepo com **monólito modular**: React → HTTP/REST → FastAPI → services → repositories → SQLAlchemy → PostgreSQL. Docker Compose executa o ambiente completo com MinIO para arquivos; o modo de API/frontend locais continua disponível.

```text
├── frontend/
│   ├── public/
│   └── src/
│       ├── app/          # Rotas, 404 e estilos
│       ├── components/
│       ├── features/     # Inicialmente home e health
│       ├── hooks/
│       ├── services/     # Axios centralizado
│       ├── types/
│       ├── utils/
│       └── main.tsx
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/         # Configuração e erros
│   │   ├── db/           # Base, engine, sessões e registro de models
│   │   ├── modules/      # auth, usuarios, condominios, unidades,
│   │   │                # encomendas, visitantes, reservas,
│   │   │                # ocorrencias, avisos e auditoria
│   │   └── main.py
│   ├── alembic/versions/
│   ├── tests/
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── requirements-dev.lock
├── infra/
├── docs/
│   ├── api-contracts/
│   ├── decisions/
│   └── architecture.md
├── .github/workflows/ci.yaml
├── .env.example
└── compose.yaml
```

Consulte [arquitetura](docs/architecture.md), [ADRs](docs/decisions/) e [contrato HTTP](docs/api-contracts/health.md).

No modo local descrito no guia detalhado, três processos estarão em execução:

| Componente | Endereço | Onde roda |
| --- | --- | --- |
| PostgreSQL 17 | `127.0.0.1:5432` (configurável) | Container Docker |
| API FastAPI | <http://127.0.0.1:8000> | Terminal 1, com `.venv` |
| Frontend Vite | <http://127.0.0.1:5173> | Terminal 2, com Node |

---

## Execução com Docker — recomendada para o grupo

Na primeira execução, copie `.env.example` para `.env` (`Copy-Item` no PowerShell
ou `cp` no Linux/macOS). Se já possui `.env`, acrescente as variáveis de storage
do exemplo sem sobrescrever seu arquivo. Com Docker e Compose v2.24+ iniciados:

```sh
docker compose up --build
```

O comando prepara banco, MinIO, bucket privado, migrations ativas, API e frontend.
O primeiro build do MinIO compila uma revisão fixa do código oficial e pode
demorar alguns minutos. Não é necessário instalar Python ou Node no host.

Confira frontend em <http://127.0.0.1:5173>, health em
<http://127.0.0.1:8000/api/v1/health> e console MinIO em <http://127.0.0.1:9001>.
Credenciais locais estão no seu `.env`. Banco e arquivos têm volumes persistentes.
Portas, limites, testes e integração estão em [Armazenamento](docs/storage.md).
Rotas de arquivos ainda aguardam autorização central e a tabela da TASK-81.

## Guia de primeira execução

O restante deste guia descreve a alternativa com API e frontend no host.

Tempo estimado: 20 a 40 minutos, a maior parte em downloads. Os comandos estão separados por sistema:

- **Windows**: PowerShell 5.1 ou 7 (não use o `cmd.exe`). Os blocos marcados `powershell`.
- **Linux**: testado como referência em Ubuntu/Debian; em outras distribuições troque o gerenciador de pacotes.
- **macOS**: com [Homebrew](https://brew.sh/).

Blocos marcados `bash` valem para Linux e macOS. Quando um comando for igual nos três sistemas, aparece uma única vez.

### Etapa 0 — Instalar os pré-requisitos

| Ferramenta | Versão | Para quê |
| --- | --- | --- |
| Git | qualquer recente | Clonar e versionar |
| Python | 3.12 ou 3.13 (não 3.11, não 3.14) | Backend |
| Node.js + npm | 24 LTS (aceita 22.13+) | Frontend |
| Docker + Compose v2 | Docker Desktop ou Docker Engine | PostgreSQL |

Não é necessário instalar PostgreSQL na máquina.

**Windows** (PowerShell; feche e reabra o terminal depois de instalar):

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Docker.DockerDesktop
```

Abra o Docker Desktop uma vez, aceite os termos e confirme que ele usa **WSL 2** e **containers Linux**. Reinicie o computador se o instalador pedir.

**Linux (Ubuntu 24.04 / Debian 13)**:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
# Node 24 via nvm (evita versões antigas do apt)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 24
```

Instale o Docker Engine seguindo a [documentação oficial](https://docs.docker.com/engine/install/) da sua distribuição e permita uso sem `sudo`:

```bash
sudo usermod -aG docker "$USER"
newgrp docker   # ou encerre a sessão e entre de novo
```

**macOS**:

```bash
brew install git python@3.12 node@24
brew install --cask docker
brew link --overwrite node@24
```

Abra o app Docker uma vez para concluir a instalação.

#### ✅ Verificação da etapa 0

Windows:

```powershell
git --version
py -3.12 --version      # ou: py -3.13 --version
node --version
npm --version
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
```

Linux / macOS:

```bash
git --version
python3 --version       # no macOS com Homebrew: python3.12 --version
node --version
npm --version
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
```

Esperado: Python `3.12.x` ou `3.13.x`; Node `v24.x` (ou `v22.13+`); `docker compose version` mostrando `v2.x`; e `docker info` imprimindo um número de versão. Se `docker info` falhar, o Docker está instalado mas parado — veja [Docker não responde](#docker-não-responde).

### Etapa 1 — Clonar e configurar o `.env`

```bash
git clone <URL-DO-REPOSITÓRIO> "Gestão de Condomínios"
cd "Gestão de Condomínios"
```

> No Windows, prefira clonar **fora de pastas sincronizadas** (OneDrive, Google Drive, Dropbox), por exemplo em `C:\dev\`. A sincronização trava arquivos de `.venv` e `node_modules` e causa erros `EPERM`/`Access denied`. Veja [Pasta no OneDrive](#pasta-sincronizada-onedrive).

Crie o `.env` a partir do exemplo:

Windows:

```powershell
Copy-Item .env.example .env
```

Linux / macOS:

```bash
cp .env.example .env
```

Os valores do exemplo funcionam sem alteração na maioria das máquinas. Edite só se necessário:

| Variável | Uso |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Credenciais e banco locais, compartilhados entre Compose e API |
| `POSTGRES_HOST` | Host usado pela API; padrão `127.0.0.1` |
| `POSTGRES_PORT` | Porta na máquina; padrão `5432`. Troque para `55432` se a 5432 estiver ocupada |
| `DATABASE_URL` | Opcional; substitui os campos acima no backend. Dialeto `postgresql+psycopg://` |
| `APP_NAME`, `LOG_LEVEL` | Nome da API e nível de logging |
| `CORS_ORIGINS` | Array JSON de origens permitidas, com esquema e porta |
| `VITE_API_BASE_URL` | Endereço da API usado pelo navegador, incluindo `/api/v1` |

Regras importantes:

- API e Vite leem o `.env` da **raiz**. Variáveis já definidas no terminal têm precedência sobre o arquivo.
- Só variáveis com prefixo `VITE_` chegam ao navegador: **nunca** coloque segredos nelas.
- Depois de alterar o `.env`, **reinicie** API e Vite.
- `.env`, `.venv`, `node_modules`, builds e caches são ignorados pelo Git. Não versione credenciais.

#### ✅ Verificação da etapa 1

```bash
git status --short --ignored .env
```

Esperado: `!! .env` (o arquivo existe e está ignorado). Se aparecer `?? .env`, o `.gitignore` não foi aplicado — não faça commit e verifique se você está na raiz do repositório.

### Etapa 2 — Subir o PostgreSQL

Na raiz do repositório (igual em todos os sistemas):

```bash
docker compose up -d --wait db
```

O primeiro `up` baixa a imagem `postgres:17` (~150 MB). `--wait` só retorna quando o health check passa.

#### ✅ Verificação da etapa 2

```bash
docker compose ps
docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Esperado:

- `docker compose ps`: serviço `db` com status `Up ... (healthy)` e porta `127.0.0.1:5432->5432/tcp` (ou a porta do seu `.env`).
- `pg_isready`: `/var/run/postgresql:5432 - accepting connections`.

Se falhar: [porta ocupada](#porta-5432-ocupada), [variável `POSTGRES_PASSWORD`](#postgres_password-required) ou [Docker não responde](#docker-não-responde).

### Etapa 3 — Backend: ambiente virtual e dependências

Use sempre o executável Python da `.venv`. Isso dispensa ativar o ambiente e evita problemas de política de execução do PowerShell.

Windows:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -c requirements-dev.lock -e ".[dev]"
```

Linux:

```bash
cd backend
python3 -m venv .venv          # use python3.12 ou python3.13 se houver várias versões
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c requirements-dev.lock -e '.[dev]'
```

macOS:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c requirements-dev.lock -e '.[dev]'
```

`-c requirements-dev.lock` garante as mesmas versões usadas pelo time e pelo CI.

#### ✅ Verificação da etapa 3

Windows:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "from app.core.config import get_settings; print(get_settings().sqlalchemy_url.render_as_string(hide_password=True))"
```

Linux / macOS:

```bash
.venv/bin/python --version
.venv/bin/python -m pip check
.venv/bin/python -c "from app.core.config import get_settings; print(get_settings().sqlalchemy_url.render_as_string(hide_password=True))"
```

Esperado: versão `3.12.x`/`3.13.x`; `No broken requirements found.`; e uma URL como `postgresql+psycopg://condominios_dev:***@127.0.0.1:5432/condominios`. Confira se **porta e banco** batem com o `.env`. Se a URL mostrar valores diferentes, há uma variável de ambiente do terminal sobrescrevendo o arquivo — veja [configuração ignorada](#o-env-parece-ignorado).

### Etapa 4 — Aplicar a migração e testar a conexão

Ainda dentro de `backend`:

Windows:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -c "from app.db.session import get_engine; from sqlalchemy import text; c=get_engine().connect(); print(c.scalar(text('SELECT 1'))); c.close()"
```

Linux / macOS:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic current
.venv/bin/python -c "from app.db.session import get_engine; from sqlalchemy import text; c=get_engine().connect(); print(c.scalar(text('SELECT 1'))); c.close()"
```

#### ✅ Verificação da etapa 4

- `upgrade head` termina com `Running upgrade  -> 20261015_0001, ...` (ou sem saída, se já aplicada).
- `alembic current` imprime `20261015_0001 (head)`.
- O teste de conexão imprime `1`.

Para ver as tabelas criadas:

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

Esperado: `alembic_version` e as tabelas de usuários, condomínios, unidades e vínculos.

Se falhar: [conexão recusada](#connection-refused-no-alembic-ou-na-api) ou [autenticação](#password-authentication-failed).

### Etapa 5 — Iniciar a API (terminal 1)

Dentro de `backend`; deixe este terminal aberto:

Windows:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Linux / macOS:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

O log deve mostrar `Uvicorn running on http://127.0.0.1:8000` e `API iniciada`.

#### ✅ Verificação da etapa 5

Em **outro** terminal:

Windows:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Linux / macOS:

```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

Esperado: `status : ok` (PowerShell) ou `{"status":"ok"}`. Abra também <http://127.0.0.1:8000/docs> para ver o Swagger.

O health verifica apenas a API, sem consultar o banco. A conexão com o banco foi verificada na etapa 4.

### Etapa 6 — Instalar e iniciar o frontend (terminal 2)

A partir da raiz:

```bash
cd frontend
npm ci
npm run dev
```

`npm ci` instala exatamente o que está no `package-lock.json`. Não use `npm install` na primeira execução, pois ele pode alterar o lockfile.

#### ✅ Verificação da etapa 6

- O terminal mostra `Local: http://127.0.0.1:5173/`.
- Abra <http://127.0.0.1:5173>: o card “Ambiente de desenvolvimento” deve mostrar **“API acessível”** com indicador verde.
- Acesse <http://127.0.0.1:5173/rota-inexistente>: deve aparecer a página 404 com link para o início.

Se aparecer “API indisponível”, veja [frontend não acessa a API](#frontend-mostra-api-indisponível).

### Etapa 7 — Rodar as verificações de qualidade

Confirma que seu ambiente produz os mesmos resultados do CI.

Backend (dentro de `backend`), Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Backend, Linux / macOS:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy
```

Frontend (dentro de `frontend`):

```bash
npm run lint
npm run build
```

#### ✅ Verificação da etapa 7

- Pytest: todos passam; **4 testes `postgres` aparecem como `skipped`** sem `TEST_DATABASE_URL`. Isso é esperado — para executá-los, veja [Testes com PostgreSQL](#testes-com-postgresql).
- Ruff: `All checks passed!` e `... files already formatted`.
- Mypy: `Success: no issues found`.
- ESLint sem saída de erros; build termina com `✓ built in ...`.

### Checklist final

| # | Verificação | Resultado esperado |
| --- | --- | --- |
| 0 | Versões das ferramentas | Python 3.12/3.13, Node 24 ou 22.13+, Compose v2 |
| 1 | `git status --short --ignored .env` | `!! .env` |
| 2 | `docker compose ps` | `db` `(healthy)` |
| 3 | `pip check` | `No broken requirements found.` |
| 4 | `alembic current` | `20261015_0001 (head)` |
| 5 | `GET /api/v1/health` | `{"status":"ok"}` |
| 6 | Página em `:5173` | “API acessível” |
| 7 | Pytest, Ruff, Mypy, ESLint, build | Tudo verde (4 skips sem banco de testes) |

Pronto: o ambiente está configurado.

---

## Uso diário

Depois da primeira execução, para voltar a trabalhar:

```bash
docker compose start db          # ou: docker compose up -d --wait db
```

Terminal 1 (`backend`): `alembic upgrade head` (caso alguém tenha adicionado migrações) e o comando do Uvicorn da etapa 5.
Terminal 2 (`frontend`): `npm ci` (se o `package-lock.json` mudou) e `npm run dev`.

Depois de um `git pull`, reinstale dependências se `requirements-dev.lock`, `pyproject.toml` ou `package-lock.json` mudaram.

Para encerrar: `Ctrl+C` nos dois terminais e `docker compose stop db`. O volume `postgres_data` preserva os dados.

Comandos úteis do banco:

```bash
docker compose logs db
docker compose stop db
docker compose start db
```

---

## Solução de problemas

Organizado por etapa. Procure pela mensagem de erro (Ctrl+F) que aparece no terminal.

### Pré-requisitos e terminal

#### `python` abre a Microsoft Store ou não é reconhecido (Windows)

O Windows tem atalhos que imitam o `python`. Use o launcher `py -3.12` (instalado junto com o Python). Para desativar os atalhos: *Configurações → Aplicativos → Configurações avançadas → Aliases de execução de aplicativo* e desligue `python.exe` e `python3.exe`.

#### `py` não encontra a versão: `No suitable Python runtime found`

A versão pedida não está instalada. Rode `py --list` para ver as disponíveis e instale 3.12 ou 3.13 (etapa 0).

#### `ERROR: Package 'gestao-condominios-api' requires a different Python`

A `.venv` foi criada com Python antigo (3.11 ou menos). Apague-a e recrie com a versão certa:

```powershell
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
```

```bash
rm -rf .venv && python3.12 -m venv .venv
```

#### `The virtual environment was not created successfully because ensurepip is not available` (Linux)

Falta o pacote de venv: `sudo apt install python3-venv` (ou `python3.12-venv`). Apague a `.venv` incompleta e recrie.

#### `... cannot be loaded because running scripts is disabled on this system` (PowerShell)

Acontece ao rodar `Activate.ps1`. O guia não exige ativação: use `.\.venv\Scripts\python.exe` diretamente. Se quiser ativar mesmo assim: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

#### `node` ou `npm` com versão errada

Feche e reabra o terminal após instalar. Com nvm, rode `nvm use` dentro de `frontend` (lê o `.nvmrc`). No Windows, verifique se não há um Node antigo antes no `PATH` com `where.exe node`.

#### Caminho com espaços ou acentos

O nome da pasta tem espaço e acentos. Sempre use aspas: `cd "Gestão de Condomínios"`. Se alguma ferramenta falhar só por causa do caminho, clone em uma pasta sem acentos (ex.: `C:\dev\gestao-condominios`).

#### Pasta sincronizada (OneDrive)

Sintomas: `EPERM: operation not permitted`, `Access is denied`, `npm ci` falha ao remover `node_modules`, arquivos “em uso”, lentidão extrema. Soluções, em ordem de preferência:

1. Clonar o repositório fora do OneDrive (ex.: `C:\dev\`).
2. Pausar a sincronização do OneDrive durante instalações.
3. Marcar a pasta como “Sempre manter neste dispositivo”.

### Docker e PostgreSQL

#### Docker não responde

Mensagens típicas: `Cannot connect to the Docker daemon`, `error during connect: ... dockerDesktopLinuxEngine: The system cannot find the file specified`, `docker info` falhando.

- **Windows/macOS**: abra o Docker Desktop e espere o status *Engine running*. No Windows, confirme WSL 2 com `wsl --status`; se faltar, `wsl --install` e reinicie.
- **Linux**: `sudo systemctl start docker` (e `sudo systemctl enable docker` para iniciar no boot). Se aparecer `permission denied ... docker.sock`, faltou entrar no grupo `docker` (etapa 0) — encerre a sessão e entre de novo.

#### `POSTGRES_PASSWORD` required

Mensagem: `required variable POSTGRES_PASSWORD is missing a value: Copie .env.example para .env antes de iniciar`. O `.env` não existe na raiz ou você está em outra pasta. Volte à etapa 1 e rode o `docker compose` **na raiz**.

#### Porta 5432 ocupada

Mensagem: `Bind for 127.0.0.1:5432 failed: port is already allocated` ou `... address already in use`. Geralmente há um PostgreSQL instalado na máquina ou outro container.

Descubra quem usa a porta:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen | Select-Object OwningProcess
Get-Process -Id <PID>
```

```bash
sudo lsof -iTCP:5432 -sTCP:LISTEN
```

Solução recomendada (não mexe no outro serviço): no `.env`, defina `POSTGRES_PORT=55432` e rode `docker compose up -d --wait db` de novo. Não altere a porta interna do container, e reinicie a API depois.

#### `password authentication failed`

Mensagem: `FATAL: password authentication failed for user "..."`. Causas:

1. **Você alterou usuário/senha no `.env` depois do primeiro `up`.** As variáveis `POSTGRES_*` só valem na criação do volume. Volte os valores originais **ou**, se o banco local não tiver nada importante, recrie o volume (⚠️ apaga todos os dados locais):

   ```bash
   docker compose down -v
   docker compose up -d --wait db
   ```

   Depois, refaça a etapa 4.
2. **A API está conectando em outro PostgreSQL** (o da máquina, na 5432). Confira a porta da URL impressa na verificação da etapa 3.

#### `container ... is unhealthy` ou `--wait` não termina

Veja o motivo com `docker compose logs db`. Se houver `database files are incompatible with server`, o volume foi criado por outra versão principal do PostgreSQL; não apague sem antes salvar dados importantes.

### Backend

#### `connection refused` no Alembic ou na API

Mensagem: `psycopg.OperationalError: connection failed: ... Connection refused`. Verifique, nesta ordem:

1. `docker compose ps` mostra `db` `(healthy)`? Senão, `docker compose up -d --wait db`.
2. A porta da URL (etapa 3) é a mesma publicada em `docker compose ps`?
3. Existe `DATABASE_URL` no `.env` ou no terminal apontando para outro lugar?

#### O `.env` parece ignorado

Variáveis definidas no terminal vencem o arquivo. Verifique e remova:

```powershell
Get-ChildItem Env: | Where-Object Name -Match 'POSTGRES|DATABASE_URL|CORS|VITE'
Remove-Item Env:DATABASE_URL
```

```bash
env | grep -E 'POSTGRES|DATABASE_URL|CORS|VITE'
unset DATABASE_URL
```

Confirme também que o arquivo se chama exatamente `.env` (o Windows pode salvar como `.env.txt`; verifique com `Get-ChildItem -Force`).

#### `ModuleNotFoundError: No module named 'app'` ou `No module named 'fastapi'`

- Rode os comandos **dentro de `backend`**.
- Use o Python da `.venv` (`.\.venv\Scripts\python.exe` ou `.venv/bin/python`), não o do sistema.
- Se a `.venv` estiver incompleta, repita a instalação da etapa 3.

#### `CORS_ORIGINS` inválido

Mensagem: `SettingsError: error parsing value for field "cors_origins"`. O valor precisa ser um **array JSON** com aspas duplas, sem espaços extras:

```text
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

#### Porta 8000 ocupada

Mensagem: `[Errno 98] Address already in use` (Linux/macOS), `[Errno 48]` (macOS) ou `[WinError 10048]` (Windows). Provavelmente outra instância da API ficou aberta: feche o terminal antigo ou encerre o processo (use os comandos de [porta 5432](#porta-5432-ocupada) trocando para 8000). Para usar outra porta, rode o Uvicorn com `--port 8001` **e** ajuste `VITE_API_BASE_URL=http://localhost:8001/api/v1`, reiniciando o Vite.

#### Erros do Alembic

| Mensagem | Causa e solução |
| --- | --- |
| `Can't locate revision identified by '...'` | O banco tem uma migração que não existe na sua branch. Atualize a branch (`git pull`); em banco local descartável, recrie o volume. |
| `Multiple head revisions are present` | Duas migrações com o mesmo pai, comum após merges. Crie uma migração de merge (`alembic merge heads -m "merge"`) e combine com o time. |
| `Target database is not up to date` | Rode `alembic upgrade head` antes de `revision --autogenerate`. |
| `alembic check` acusa novas operações | Models alterados sem migração. Gere e revise uma revisão. |

### Frontend

#### `npm ci` falha com `EBADENGINE`

Node fora da faixa `^22.13.0 || >=24.0.0`. Atualize para Node 24 (etapa 0) ou rode `nvm use`.

#### `npm ci` falha com `EPERM`, `EBUSY` ou `operation not permitted` (Windows)

Algum processo segura arquivos em `node_modules` (normalmente o Vite em execução, o editor ou o OneDrive). Pare o `npm run dev` (`Ctrl+C`), feche terminais antigos, pause o OneDrive e rode `npm ci` novamente.

#### `npm ci` reclama que o lockfile está fora de sincronia

Mensagem: `` `npm ci` can only install packages when your package.json and package-lock.json are in sync``. Alguém alterou o `package.json` sem atualizar o lock. Faça `git pull`; se persistir, avise o time — quem alterou deve rodar `npm install` e versionar o lockfile.

#### `Port 5173 is already in use`

O Vite usa porta fixa (`strictPort`) para manter o CORS previsível. Encerre o outro processo (provavelmente um `npm run dev` esquecido). Se precisar trocar a porta, adicione a nova origem em `CORS_ORIGINS` e reinicie a API.

#### Frontend mostra “API indisponível”

1. A API está rodando? Teste o health da etapa 5.
2. Abra o DevTools do navegador (F12) → **Console** e **Network**:
   - `ERR_CONNECTION_REFUSED`: API parada ou porta errada em `VITE_API_BASE_URL`.
   - `blocked by CORS policy`: a origem da página não está em `CORS_ORIGINS`. A origem precisa ser idêntica, incluindo `localhost` × `127.0.0.1` e a porta. Ajuste o `.env` e **reinicie a API**.
   - `timeout of 5000ms exceeded`: API travada ou em depuração; veja o terminal da API.
3. Alterou `VITE_API_BASE_URL`? **Reinicie o Vite**: o valor é lido só na inicialização.

#### `npm run preview` não acessa a API

O preview usa a porta 4173, que não está em `CORS_ORIGINS` por padrão. Adicione `"http://127.0.0.1:4173"` temporariamente e reinicie a API.

### Recomeçar do zero

Se o ambiente ficou inconsistente, apague apenas artefatos locais (⚠️ o último comando apaga os dados do banco local):

```powershell
Remove-Item -Recurse -Force backend\.venv, frontend\node_modules
docker compose down -v
```

```bash
rm -rf backend/.venv frontend/node_modules
docker compose down -v
```

Depois, refaça o guia a partir da etapa 2. O `.env` é preservado.

---

## Migrações durante o desenvolvimento

Dentro de `backend`, substituindo `python` pelo executável da `.venv`:

```bash
python -m alembic current
python -m alembic revision --autogenerate -m "descricao_da_alteracao"
python -m alembic upgrade head
python -m alembic check
```

Importe novos models em `app/db/models.py` antes de gerar a revisão. Revise o script e inclua-o no mesmo PR da alteração. Não use `Base.metadata.create_all()` na aplicação. O CI verifica upgrade, downgrade e novo upgrade em banco descartável.

## Testes com PostgreSQL

Sem `TEST_DATABASE_URL`, quatro testes PostgreSQL são explicitamente pulados. Para executá-los, crie um banco de testes dedicado (nunca use o banco de desenvolvimento):

```bash
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" condominios_test'
```

Windows / PowerShell (dentro de `backend`; ajuste usuário, senha e porta conforme o `.env`):

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://condominios_dev:local_dev_only@127.0.0.1:5432/condominios_test'
$env:TEST_DATABASE_URL = $env:DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:DATABASE_URL, Env:TEST_DATABASE_URL
```

Linux / macOS:

```bash
export DATABASE_URL='postgresql+psycopg://condominios_dev:local_dev_only@127.0.0.1:5432/condominios_test'
export TEST_DATABASE_URL="$DATABASE_URL"
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest -q
unset DATABASE_URL TEST_DATABASE_URL
```

Esperado: todos os testes passam, sem skips. Os testes revertem as transações ao final de cada caso. **Remova as variáveis ao terminar**, senão a API passará a usar o banco de testes. O CI fornece PostgreSQL limpo automaticamente.

Para aplicar formatação no backend: `python -m ruff format .`. No frontend, `npm run typecheck` verifica só os tipos (o `build` já inclui essa etapa).

## Dependências e colaboração

- `frontend/package-lock.json`: instalar com `npm ci`; atualizar intencionalmente com `npm install`.
- `backend/requirements-dev.lock`: versões exatas usadas como constraints; instalar com `-c requirements-dev.lock`. Atualizar em ambiente virtual limpo e validar Python 3.12/3.13 no CI. Não contém paths locais ou credenciais.
- PostgreSQL fixa a versão principal 17 e recebe patches da tag oficial; upgrades de versão principal precisam de planejamento do volume.
- Dividir trabalho por módulo e coordenar mudanças de contratos e migrações. Resolver explicitamente múltiplos heads Alembic.
- Não versionar `.env`, dados, tokens ou credenciais reais.

### Fluxo de branches e pull requests

- Nada entra na `main` por push direto, só por pull request com **1 aprovação** e **CI verde** (regra de proteção configurada no GitHub).
- Crie uma branch a partir da `main` atualizada com o padrão `<tipo>/<US-id>-<descricao-curta>`, com a descrição em minúsculas e hífens. Exemplos: `feat/US-1001-login-jwt`, `fix/US-2003-conflito-reserva`, `docs/US-1006-der`. Sem story ligada (setup, infra), omita o ID: `chore/ci-mypy`.
- Tipos: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`. Os mesmos prefixos valem para os commits (Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- PRs pequenos, preenchendo o template (o que mudou, story ligada, como testar). Antes de pedir revisão, atualize a branch com a `main` e rode os comandos da [etapa 7](#etapa-7--rodar-as-verificações-de-qualidade).
- Apague a branch depois do merge.

O workflow `.github/workflows/ci.yaml` valida backend (Python 3.12 e 3.13, com PostgreSQL limpo) e frontend em pushes e PRs.

## Próxima sprint

Priorizar autenticação real, autorização por perfil/vínculo e testes negativos de acesso entre condomínios. Em seguida implementar cadastro e ativação de condomínios, unidades e usuários, confirmando a necessidade de múltiplos perfis/unidades no mesmo condomínio. Só então expor operações protegidas e avançar nos fluxos operacionais.

## Referências técnicas

[Vite](https://vite.dev/guide/), [FastAPI / Settings](https://fastapi.tiangolo.com/advanced/settings/), [SQLAlchemy / PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html), [Docker Compose](https://docs.docker.com/compose/), [Alembic](https://alembic.sqlalchemy.org/) e [GitHub Actions / Python](https://github.com/actions/setup-python).
