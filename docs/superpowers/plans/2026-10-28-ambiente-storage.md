# Ambiente e armazenamento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans para executar as tarefas nesta sessão, em ordem.

**Goal:** entregar o ambiente da TASK-2 e a base integrável da TASK-26.

**Architecture:** Compose com PostgreSQL, API, frontend e MinIO compilado de fonte fixa. O módulo storage contém tipos, validação, serviço e adaptador S3; recebe autorização explícita do chamador e não expõe HTTP. Metadados têm contrato e rascunho Alembic para Davi.

**Tech Stack:** Python 3.12/3.13, FastAPI, MinIO Python SDK, Pillow, PostgreSQL 17, Docker Compose, React/Vite.

**Spec:** `docs/superpowers/specs/2026-10-28-ambiente-storage-design.md`, aprovado pelo usuário em 28/10/2026.

## Global Constraints

- Preservar WIP da portaria e AGENTS.md; aproveitar Dockerfiles/Compose/Vite pertinentes.
- Banco/autorização continuam com Davi/Gabriel. Sem rotas ou credenciais fictícias.
- Imagens JPG/PNG/WebP até 5 MiB; MP4 até 50 MiB apenas em ocorrências; PDF até 5 MiB em suporte.
- Bucket privado, chave gerada no servidor, assinatura de 60 segundos com teto 300.
- Não alterar .env real nem dados/containers de outros projetos.
- Não fechar os cards antes de cumprir as dependências e validação humana.

## Review Focus

- URL pública assinada deve funcionar fora da rede Docker; host não pode ser reescrito depois de assinar.
- Arquivo do mesmo condomínio ainda exige autorização sobre o recurso.
- Nome, MIME e tamanho fornecidos não provam o conteúdo; limitar leitura e validar bytes.
- Reiniciar preserva volumes e inicialização do bucket não torna conteúdo público.
- Falhas do S3 não devem vazar credenciais, URL assinada ou detalhes internos nas exceções do serviço.

### Task 1: ambiente reproduzível (TASK-2)

**Files:** `compose.yaml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore` de ambos, `frontend/vite.config.ts`, `.env.example`, `infra/minio/Dockerfile`, `README.md`.

**Interfaces:** storage no host configurado em STORAGE_ENDPOINT; assinatura em STORAGE_PUBLIC_ENDPOINT; bucket STORAGE_BUCKET, inicializado pelo módulo CLI da Task 2. A API espera o serviço storage-init terminar. O MinIO fornece `/minio/health/live`.

- [ ] Preservar baseline/WIP; atualizar base e usar branch `codex/ambiente-storage`.
- [ ] Confirmar ausência atual de storage em `docker compose --env-file .env.example config --services`.
- [ ] Construir MinIO de revisão oficial fixa e incluir atribuição/licença. Integrar serviços, volumes e portas configuráveis; antecipar o contrato do CLI da Task 2.
- [ ] Verificar build/configuração e health real em projeto de teste dedicado, depois da Task 2.

### Task 2: serviço e integração S3 (TASK-26)

**Files:** `backend/app/modules/storage/{__init__,types,validation,service,s3,bootstrap}.py`, `backend/app/core/config.py`, `backend/pyproject.toml`, `backend/requirements-dev.lock`, `backend/tests/test_storage.py`, `backend/tests/test_storage_s3.py`.

**Interfaces:** `StorageContext(condominio_id, usuario_id)`, `FileMetadata`, `StorageService.upload(ctx, module, filename, content_type, stream) -> FileMetadata`, `download_url(ctx, file) -> str`, `remove(ctx, file) -> None`. Construtor recebe adaptador e política obrigatória `authorize(ctx, module, action, file_or_none) -> None`; política e metadados são internos/trusted. `S3Adapter` faz put/sign/remove e inicializa bucket privado. `python -m app.modules.storage.bootstrap` prepara o bucket de forma idempotente.

- [ ] Escrever testes antes do serviço: upload cria chave sem nome original; lê até limite + 1; extensão/MIME/bytes inválidos e imagem truncada são recusados antes de enviar; MP4 em módulo errado é recusado.
- [ ] Testar contexto cruzado e política negada para leitura/remoção/upload, inclusive no mesmo condomínio; nenhum acesso ao adaptador em negativa.
- [ ] Executar teste e observar falha por módulo ausente.
- [ ] Implementar tipos, serviço, validação e erros em português; assinar pelo endpoint público com região fixa sem consulta de rede.
- [ ] Testar erro de infraestrutura com mensagem pública genérica e prazo de URL validado.
- [ ] Integrar MinIO real: upload de PNG fictício, download assinado por endpoint público, GET anônimo recusado, remoção; bucket continua privado após repetir inicialização; repetir depois de reiniciar serviços.
- [ ] Executar testes de serviço e S3 até ficarem verdes.

### Task 3: contrato de metadados, documentação e validação

**Files:** `backend/alembic/drafts/arquivos_storage.py`, `backend/tests/test_storage_migration_draft.py`, `docs/storage.md`, `docs/api-contracts/convencoes.md`, `.github/workflows/ci.yaml` e plano de execução.

**Interfaces:** tabela arquivos conforme DER, `(id, condominio_id)` único, tamanho positivo, FK usuário/condomínio. Rascunho fora da cadeia ativa; não registrar model ativo. Consumidores persistem metadados na sua transação e compensam upload em falha.

- [ ] Escrever teste PostgreSQL do rascunho (upgrade/downgrade, FK, tamanho e chave única) e confirmar falha sem arquivo.
- [ ] Implementar rascunho com predecessor pendente, validar com Alembic Operations em schema dedicado.
- [ ] Documentar serviço, autorização obrigatória, persistência futura, compensação e comandos Docker; identificar pendências explicitamente.
- [ ] Atualizar CI para executar integração real S3 usando a mesma imagem construída, banco dedicado e checagens existentes.
- [ ] Backend: Ruff lint/format, Mypy, pytest completo em banco e S3 dedicados; migrações ativas upgrade/check/downgrade/upgrade.
- [ ] Frontend: lint, testes e build. Confirmar persistência de banco e objeto após reinício do projeto Docker de teste.
- [ ] Revisão independente da alteração, correções verificadas, commits escopados e Codewise.
