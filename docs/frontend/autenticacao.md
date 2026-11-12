# Acesso autenticado — recorte das TASK-15 e TASK-31

## Entregue

- Login com e-mail/senha no contrato existente do backend.
- Cadastro separado de Morador e Administração, com validação e sessão automática.
- Gestão de funcionários pela Administração: lista, busca, paginação, cadastro e desligamento.
- Cadastro dos responsáveis necessários às ações da conta compartilhada.
- Seleção de condomínio para múltiplos vínculos e troca posterior.
- Validação por `/auth/me` antes de mostrar a área interna, inclusive ao recarregar.
- Sessão por aba em `sessionStorage`, sem guardar senha.
- Cliente Axios autenticado com Bearer, renovação compartilhada e uma repetição por requisição.
- Áreas iniciais de Morador, Portaria, Administração, Plataforma e conta sem condomínio disponível.
- Mensagens para credenciais incorretas, limite de tentativas, sessão expirada, acesso negado e falha temporária.

## Fluxo e responsabilidades

`LoginPage` envia as credenciais por `SessionClient.login`. O serviço guarda tokens e a lista de vínculos, consulta `/auth/me` e publica um `SessionSnapshot`. O `AuthProvider` acompanha mudanças por `useSyncExternalStore` e compartilha o serviço pelo contexto React. `RequireSession` bloqueia renderização até a validação; `WorkspacePage` confere o destino do perfil.

O perfil e o condomínio exibidos vêm de `/auth/me`, nunca da decodificação do JWT ou da lista salva no navegador. A lista salva serve para oferecer a seleção; o backend revalida o vínculo ao selecionar. A interface não implementa autorização central nem substitui os controles da API.

Em um 401 protegido, o serviço chama `/auth/refresh` com o refresh token e repete a requisição uma única vez. Chamadas concorrentes aguardam a mesma Promise de renovação. Um contador de geração (`epoch`) descarta respostas anteriores ao logout ou à troca de condomínio. Um 403 é devolvido ao chamador sem renovação; a restauração mostra acesso negado quando `/auth/me` nega o contexto.

Rede indisponível ou erro temporário durante a restauração mantém tokens e permite tentar novamente. Refresh rejeitado encerra a sessão e pede novo login. O cliente público de healthcheck não recebe Bearer.

## Rotas

| Rota | Comportamento |
| --- | --- |
| `/login` | Formulário real; sessão válida segue para sua área |
| `/cadastro` | Escolha entre conta de Morador e Administração |
| `/cadastro/morador`, `/cadastro/administracao` | Cadastro real integrado à API |
| `/selecionar-condominio` | Seleção autenticada entre vínculos |
| `/app` | Resolve o destino pelo contexto validado |
| `/app/morador` | Visão geral e unidades retornadas pela API |
| `/app/portaria` | Visão geral do funcionário |
| `/app/administracao` | Visão geral da administração |
| `/app/administracao/funcionarios` | Gestão da equipe e cadastro de responsáveis |
| `/app/plataforma` | Visão geral do administrador da plataforma |
| `/app/sem-condominio` | Conta autenticada sem condomínio disponível para operações |
| `/acesso-negado` | Mensagem de restrição e retorno à própria área |

Cadastro e funcionários têm integração real. Os demais serviços ainda não implementados
aparecem como indisponíveis. `/prototipos/portaria` continua sendo demonstração pública
com dados fictícios em memória, sem integração operacional.

## Limites da sessão

- `sessionStorage` mantém a sessão ao recarregar e normalmente a encerra ao fechar a aba; restauração de abas pelo navegador pode preservá-la. A API determina a validade efetiva dos tokens.
- Tokens são acessíveis a JavaScript: a aplicação deve preservar as proteções contra XSS. Cookies HttpOnly exigiriam mudanças no contrato e não integram este recorte.
- Sair limpa esta aba; não há endpoint de revogação remota no contrato atual.
- Se o navegador bloquear o storage, a sessão funciona em memória e se perde ao recarregar.
- A sessão reconhece os quatro estados do condomínio: pendente, ativo, rejeitado e desativado, conforme o contrato ampliado no PR #17. Somente ativo abre as áreas operacionais; o fluxo de correção cadastral permanece fora deste recorte.
- Recuperação de senha, wizard do condomínio, vínculo com unidades, edição/histórico de
  funcionários e tela de permissões por aba pertencem a entregas posteriores.
- A base de rotas/sessão e o recorte de cadastro/lista/cadastro/desligamento de funcionários
  atendem às TASK-15 e TASK-31. Prettier tem adoção gradual conforme o README do frontend.

## Evidências de validação

Em 12/11/2026, a conclusão das TASK-15/26/31 passou por lint, Prettier, 26 testes
frontend e build com typecheck. A API integrada passou por Ruff, Mypy, Alembic check
e 411 testes com PostgreSQL 17 e MinIO reais, sem skips. No navegador foram exercitados
cadastro de morador com sessão automática, senha com letras acentuadas, login da
Administração, estado vazio, cadastro de responsável, cadastro e desligamento de
funcionário e consulta dos desligados. No celular, os formulários se reorganizam e
a tabela tem rolagem horizontal dentro do painel, sem alargar a página. Os testes
visuais usaram banco e contas fictícias, separados do banco vazio da suíte.

Revisões independentes de backend e frontend não deixaram bloqueios. Foram corrigidos
compensação do upload sem depender do banco indisponível, consulta no repositório,
limite do nome de responsável, senha Unicode, largura da tabela e documentação antiga.
As evidências históricas abaixo descrevem entregas anteriores.

Em 2026-11-01, lint, 17 testes e build com typecheck passaram em Node 24 no Docker. Os testes incluem os oito fluxos existentes da portaria e nove verificações de sessão/navegação, usando um servidor HTTP local real para os contratos do cliente.

Também foi exercitado o frontend com FastAPI/Python 3.13 e PostgreSQL 17 temporário, migrado com Alembic e populado apenas com seis contas fictícias. Foram confirmados:

- Senha incorreta e bloqueio por excesso de tentativas (429 real).
- Login nos quatro perfis e conta sem vínculo; destinos corretos.
- Conta com dois condomínios: seleção após recarga e troca de perfil de Portaria para Morador.
- Recarga com sessão válida e saída com retorno ao login.
- Morador tentando abrir a área da Portaria: acesso negado.
- Invalidação da versão da sessão no banco de teste: retorno ao login com aviso de expiração.
- API temporária parada durante a recarga: erro recuperável, sem exibir dados antigos; retomada pelo botão de tentar novamente após restabelecer o serviço.
- Layout em desktop e viewport de celular de 390 × 844.

Revisão independente do diff e do contrato: sem achados relevantes. Os dados, senhas e scripts de fixtures usados no teste não integram o repositório.

Em 05/11/2026, foram adicionados testes de regressão da restauração com condomínio pendente/rejeitado, tanto selecionado quanto em outro vínculo da conta. Também verificam que estados desconhecidos continuam recusados e que os três perfis de condomínio não abrem operações quando o condomínio não está ativo. A suíte passa a ter 21 testes (13 de autenticação/navegação e os oito existentes da portaria).
