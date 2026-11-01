# Acesso autenticado no frontend — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o acesso funcional e a estrutura inicial por perfil das TASK-15/TASK-31.

**Architecture:** Serviço de sessão independente de React, com Axios e persistência por aba. Um provider expõe identidade validada por `/auth/me`; rotas protegidas e telas usam o design system existente. O backend continua sendo a autoridade de acesso.

**Tech Stack:** React 19, TypeScript, React Router 7, Axios, Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-01-login-frontend-design.md`.

## Global Constraints

- Não alterar backend, banco, cadastro ou protótipo da portaria.
- Português; reutilizar componentes e estilos existentes.
- Nunca persistir senha nem versionar credenciais ou dados pessoais reais.
- Sessão em `sessionStorage`, conforme escolha do responsável.

## Review Focus

- Recarregar com token expirado deve renovar e validar `/auth/me` antes de mostrar dados.
- Vários condomínios exigem seleção, inclusive ao recarregar nessa etapa.
- Duas requisições com 401 não podem disparar duas renovações.
- Sair durante renovação não pode restaurar tokens antigos.
- Falha de rede deve permitir recuperação; 403 não dispara renovação infinita.

### Task 1: Serviço de sessão e HTTP

**Files:** criar `frontend/src/features/auth/{types,session,session.test}.ts`; alterar `frontend/package.json`.

**Interfaces:** `createSessionClient(baseURL, storage)` produz `login`, `selectCondominium`, `restore`, `logout`, `subscribe`, `getSnapshot` e `http`. `SessionSnapshot` distingue loading, anonymous, authenticated e error; contém `/auth/me`, vínculos e mensagem. `homePath(identity)` resolve apenas destinos internos conhecidos.

- [x] Escrever testes de HTTP real em servidor Node local: payload, Bearer, restauração, seleção, refresh concorrente, 401 definitivo, rede, 403 e logout durante refresh.
- [x] Executar os testes; falha pela ausência do serviço confirmada (RED).
- [x] Implementar serviço isolado, validação de armazenamento e renovação única com proteção contra respostas antigas.
- [x] Executar `npm test`; testes novos e os oito existentes aprovados.

### Task 2: Provider, login e navegação

**Files:** criar `frontend/src/features/auth/{context.ts,AuthProvider.tsx,LoginPage.tsx,SessionPages.tsx,WorkspacePage.tsx,Auth.module.css}`; alterar `frontend/src/{main.tsx,app/router.tsx,components/Operations.tsx}`.

**Interfaces:** provider consome o serviço da Task 1 e expõe snapshot/client pelo contexto. Guardas validam o perfil retornado por `/auth/me`. Layout recebe opcionalmente contexto real sem modificar os defaults da prévia pública.

- [x] Testar resolução dos destinos por perfil, sem vínculo, plataforma e condomínio indisponível; RED confirmado.
- [x] Implementar provider e formulário acessível; limpar senha após envio e tratar 401/429/rede.
- [x] Implementar seleção e guardas de rota; estados carregando, erro recuperável e acesso negado.
- [x] Implementar áreas iniciais e ações de sair/trocar condomínio; módulos futuros claramente indisponíveis.
- [x] Executar `npm run lint`, `npm test`, `npm run build`; sucesso.
- [x] Verificar login, seleção, recarga, logout e responsividade com fixtures fictícias e API de teste.

### Task 3: Revisão e entrega

**Files:** documentar operação e evidências em `docs/frontend/autenticacao.md`.

- [x] Revisar o diff com um revisor de contexto novo; sem achados relevantes.
- [ ] Registrar verificações e limites; manter TASK-31 parcial no Notion.
- [ ] Preparar commit e PR dedicado baseado em main, preservando arquivos locais de terceiros.
- [ ] Explicar com codewise a sessão, o fluxo HTTP e a separação entre navegação e autorização.
