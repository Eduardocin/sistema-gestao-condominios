# Acesso autenticado no frontend — TASK-15 / TASK-31

## Recorte autorizado

Substituir a prévia de `/login` por acesso real com e-mail e senha. Usar os contratos existentes de `/auth/login`, `/auth/selecionar-condominio`, `/auth/refresh` e `/auth/me`. Cadastro e funcionários permanecem fora deste recorte; a TASK-31 não será concluída integralmente.

## Decisões

- Sessão em `sessionStorage`, conforme escolha do responsável: sobrevive ao recarregamento da aba. Nunca guardar senha. O navegador pode restaurar sessões ao reabrir abas; esse armazenamento não substitui a expiração do servidor.
- O cliente público continua separado do cliente com Bearer. A API permanece responsável pelas permissões e pelo isolamento entre condomínios.
- `/auth/me` valida a identidade e o contexto antes de renderizar uma área interna; não interpretar o JWT como fonte de autorização no frontend.
- Um 401 em requisição autenticada tenta renovar uma vez; requisições concorrentes compartilham a renovação. Refresh inválido encerra a sessão. Falha de rede permite tentar novamente. Um 403 informa acesso negado sem renovar em ciclo.
- Logout ou troca de contexto invalida respostas antigas para que não restaurem uma sessão anterior.
- Seleção explícita quando há vários condomínios. A seleção é revalidada pelo backend; nenhum identificador de condomínio será acrescentado às operações comuns.
- Áreas iniciais de Morador, Portaria, Administração e Plataforma usam dados reais de `/auth/me`. Funcionalidades futuras ficam indisponíveis, sem dados operacionais fictícios. O protótipo público da portaria continua separado.
- Reutilizar componentes, tokens e estilos existentes; português e funcionamento em celular.

## Limites

Tokens acessíveis a JavaScript são uma decisão do MVP e exigem cuidado com XSS. Cookies HttpOnly exigiriam outro contrato no backend e não fazem parte desta entrega. Não há logout/revogação remota neste contrato: sair limpa a sessão desta aba. Não implementar permissões por aba, recuperação de senha, cadastro ou telas operacionais.

## Aceite

Login e seleção reais; restauração validada; navegação por perfil; mensagens para credenciais incorretas, limite de tentativas, rede, sessão expirada e acesso negado. Testes do cliente e da sessão, lint, build e verificação visual em desktop/celular. Nenhum dado pessoal real ou credencial versionado.
