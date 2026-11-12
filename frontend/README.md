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
npm run format:check
npm test
npm run build
```

O build inclui a checagem de tipos. Os testes Node de autenticação abrem um servidor HTTP temporário na interface de loopback; o ambiente de teste precisa permitir essa conexão. O lint usa ESLint. `npm run format` aplica Prettier, e `npm run format:check` verifica o formato. A adoção é gradual: esses comandos abrangem o módulo `src/features/employees`, `RegistrationPage.tsx`, `employees.test.ts` e a configuração do formatador, preservando o formato legado. Para incluir outro arquivo, use `npx prettier --write src/features/modulo/Arquivo.tsx` e amplie os dois scripts no mesmo PR.

## Rotas disponíveis

| Rota | Uso |
| --- | --- |
| `/` | Apresentação pública |
| `/login` | Entrar na conta |
| `/cadastro` | Escolher tipo de conta |
| `/cadastro/morador` | Criar conta de morador com sessão automática |
| `/cadastro/administracao` | Criar conta da Administração com CPF ou CNPJ |
| `/selecionar-condominio` | Selecionar contexto autenticado |
| `/app` | Direcionar para a área permitida |
| `/app/administracao/funcionarios` | Administração de condomínio ativo: listar, cadastrar e desligar funcionários; cadastrar responsáveis |
| `/app/morador`, `/app/portaria`, `/app/administracao`, `/app/plataforma` | Visão geral de cada perfil |
| `/app/sem-condominio` | Conta autenticada sem condomínio disponível para operações |
| `/prototipos/portaria` | Demonstração pública com dados fictícios locais |
| `/status`, `/design-system` | Saúde do serviço e catálogo de componentes |

Cadastros usam `POST /contas/morador` ou `POST /contas/administracao`, com os campos dos contratos em [núcleo](../docs/api-contracts/nucleo.md). Por exemplo, use `Ana Exemplo`, `ana@example.com`, telefone fictício `11987654321` e uma senha de teste com letras e números. A conta criada entra automaticamente; ela precisa de vínculo com um condomínio para realizar operações. O cadastro de prédios e o vínculo de unidades pertencem a entregas posteriores.

Em Funcionários, comece cadastrando um responsável da Administração se a lista estiver vazia. Depois, cadastre um nome da equipe com função, contato e responsável; a pessoa não recebe login individual. A lista permite busca, paginação e consulta de desligados. O desligamento exige confirmação e responsável e preserva os registros anteriores. O frontend envia o JWT pelo `client.http`, sem IDs de condomínio no formulário.

## Criar uma tela

Agrupe a tela e seu CSS Module em `src/features/<modulo>/`. Reutilize os componentes de `src/components` e tokens em `src/styles/tokens.css`. Registre a rota em `src/app/router.tsx`.

Uma tela autenticada deve ficar dentro de `RequireSession`, importado de `src/features/auth/SessionPages.tsx`:

```tsx
{ path: '/app/administracao/funcionarios', element: <RequireSession><EmployeesPage /></RequireSession> }
```

Dentro da tela, `useAuth()` expõe `snapshot.identity` (dados validados por `/auth/me`) e `client.http` (Axios autenticado). Use esse cliente para chamadas protegidas; `services/http.ts` continua público, para o healthcheck. Para restringir por perfil, verifique o contexto antes de renderizar, como em `WorkspacePage.tsx`; a proteção da API continua obrigatória. A navegação inicial usa `homePath` em `navigation.ts`.

Não envie `condominium_id` nas operações comuns: o backend obtém o contexto do JWT. A seleção explícita em `/auth/selecionar-condominio` é a exceção documentada no contrato. Nunca use o protótipo público da portaria como fonte de dados reais.

Detalhes de sessão, rotas, limites e roteiro de validação: [autenticação](../docs/frontend/autenticacao.md).
