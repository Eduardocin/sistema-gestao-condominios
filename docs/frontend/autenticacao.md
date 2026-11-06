# Acesso autenticado — recorte das TASK-15 e TASK-31

## Entregue

- Login com e-mail/senha no contrato existente do backend.
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
| `/selecionar-condominio` | Seleção autenticada entre vínculos |
| `/app` | Resolve o destino pelo contexto validado |
| `/app/morador` | Visão geral e unidades retornadas pela API |
| `/app/portaria` | Visão geral do funcionário |
| `/app/administracao` | Visão geral da administração |
| `/app/plataforma` | Visão geral do administrador da plataforma |
| `/app/sem-condominio` | Conta autenticada sem condomínio disponível para operações |
| `/acesso-negado` | Mensagem de restrição e retorno à própria área |

Cadastro permanece uma prévia desabilitada. Serviços operacionais aparecem como indisponíveis nas áreas reais. `/prototipos/portaria` continua sendo demonstração pública com dados fictícios em memória, sem integração operacional.

## Limites da sessão

- `sessionStorage` mantém a sessão ao recarregar e normalmente a encerra ao fechar a aba; restauração de abas pelo navegador pode preservá-la. A API determina a validade efetiva dos tokens.
- Tokens são acessíveis a JavaScript: a aplicação deve preservar as proteções contra XSS. Cookies HttpOnly exigiriam mudanças no contrato e não integram este recorte.
- Sair limpa esta aba; não há endpoint de revogação remota no contrato atual.
- Se o navegador bloquear o storage, a sessão funciona em memória e se perde ao recarregar.
- A sessão reconhece os quatro estados do condomínio: pendente, ativo, rejeitado e desativado, conforme o contrato ampliado no PR #17. Somente ativo abre as áreas operacionais; o fluxo de correção cadastral permanece fora deste recorte.
- Cadastro, recuperação de senha, funcionários e permissões por aba ainda faltam: esta entrega não conclui a TASK-31, nem todos os itens da TASK-15 (por exemplo, formatador e validação de uso pela equipe).

## Evidências de validação

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
