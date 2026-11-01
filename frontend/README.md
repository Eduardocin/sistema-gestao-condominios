# Frontend

React/TypeScript com Vite. Use Node `^22.13.0 || >=24.0.0`; o CI e o Docker usam Node 24.

## Executar

Na raiz, copie `.env.example` para `.env` e preencha os valores locais conforme o README principal. Nunca versione esse arquivo. Para o ambiente completo:

```sh
docker compose up --build
```

Para executar somente o frontend, com a API disponível separadamente:

```sh
cd frontend
npm ci
npm run dev
```

`VITE_API_BASE_URL` define a URL pública da API, por padrão `http://localhost:8000/api/v1`. Depois de alterar variáveis de ambiente, reinicie o Vite. A origem do frontend deve constar em `CORS_ORIGINS` do backend. Em produção, use HTTPS.

## Validar

```sh
npm run lint
npm test
npm run build
```

O build inclui a checagem de tipos. Os testes Node de autenticação abrem um servidor HTTP temporário na interface de loopback; o ambiente de teste precisa permitir essa conexão. O lint usa ESLint; ainda não existe um comando de formatação automática.

## Criar uma tela

Agrupe a tela e seu CSS Module em `src/features/<modulo>/`. Reutilize os componentes de `src/components` e tokens em `src/styles/tokens.css`. Registre a rota em `src/app/router.tsx`.

Uma tela autenticada deve ficar dentro de `RequireSession`, importado de `src/features/auth/SessionPages.tsx`:

```tsx
{ path: '/app/exemplo', element: <RequireSession><MinhaTela /></RequireSession> }
```

Dentro da tela, `useAuth()` expõe `snapshot.identity` (dados validados por `/auth/me`) e `client.http` (Axios autenticado). Use esse cliente para chamadas protegidas; `services/http.ts` continua público, para o healthcheck. Para restringir por perfil, verifique o contexto antes de renderizar, como em `WorkspacePage.tsx`; a proteção da API continua obrigatória. A navegação inicial usa `homePath` em `navigation.ts`.

Não envie `condominium_id` nas operações comuns: o backend obtém o contexto do JWT. A seleção explícita em `/auth/selecionar-condominio` é a exceção documentada no contrato. Nunca use o protótipo público da portaria como fonte de dados reais.

Detalhes de sessão, rotas, limites e roteiro de validação: [autenticação](../docs/frontend/autenticacao.md).
