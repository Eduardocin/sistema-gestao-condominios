# Matriz de permissões e regras multi-tenant

Status: rascunho para aprovação dos leads (TASK-5). Base das histórias US-1001 (isolamento), US-1002 (autorização central) e US-304 (permissões por aba).

Este documento complementa [`architecture.md`](architecture.md) e o [ADR 0002](decisions/0002-isolamento-condominios.md). Onde houver conflito, vale este documento até a decisão ser levada a um novo ADR.

## 1. Escopo

Cobre os módulos do MVP: contas, condomínio e estrutura, chaves e vínculos, funcionários, encomendas, visitantes, veículos, áreas comuns e reservas, ocorrências, avisos, comunicados, suporte e auditoria.

Fora do MVP, portanto fora da matriz: boletos, documentos, financeiro, login facial, WhatsApp e PIN individual das contas compartilhadas.

Nome do campo de isolamento: **`condominio_id`** (é o nome usado nos models do repositório; as histórias do Notion escrevem `condominium_id`, é a mesma coisa).

## 2. Perfis e como aparecem no modelo

| Perfil | Como é representado hoje | Tipo de conta |
| --- | --- | --- |
| Morador | `vinculos_condominio.perfil = 'morador'`, com `unidade_id` | Individual |
| Funcionário | `vinculos_condominio.perfil = 'funcionario'` | **Uma conta compartilhada por condomínio** |
| Administração | `vinculos_condominio.perfil = 'administracao'` | **Uma conta compartilhada por condomínio** |
| ADM (plataforma) | `usuarios.administrador_plataforma = true`, **sem** vínculo | Individual |

Pontos importantes:

- O perfil "plataforma" nunca vira vínculo (o `CHECK` da migração já impede). É um privilégio global, separado dos perfis locais.
- Os **nomes** dos porteiros e seguranças (cadastrados pela Administração) e a lista de **responsáveis pela Administração** não são usuários e não fazem login. São registros usados em formulários e na auditoria (seção 9).
- Um mesmo usuário pode ter vínculos em condomínios diferentes, mas só atua em **um condomínio por vez** (o escolhido no token).

## 3. Regras multi-tenant

**R1. O `condominio_id` vem do token, nunca da requisição.** Rotas do dia a dia não têm `condominio_id` na URL, no corpo nem em cabeçalho. Se o cliente enviar o campo, ele é ignorado ou rejeitado (422), nunca usado.

**R2. Toda tabela de negócio tem `condominio_id` obrigatório**, com FK e índice. Tabelas que apontam para unidade usam a **FK composta** `(unidade_id, condominio_id)`, como já faz `vinculos_condominio`, para impedir uma unidade de outro condomínio.

**R3. O filtro é aplicado numa camada comum.** Todo repository recebe o contexto (`condominio_id`) e aplica o filtro em SELECT, UPDATE e DELETE. É proibido ter `get_by_id(id)` sem condomínio. INSERT usa o `condominio_id` do contexto.

**R4. Recurso de outro condomínio (ou de outra unidade do morador) responde 404**, igual a um recurso que não existe. Nunca 403, para não revelar que ele existe.

**R5. O banco não substitui a camada comum.** As constraints garantem integridade, mas uma consulta sem filtro ainda lê tudo. Por isso a regra R3 é testada (seção 10).

**R6. Perfil e unidades vêm do banco a cada requisição.** O token só diz *quem é* e *em qual condomínio está*. O vínculo ativo, o perfil, as unidades e as permissões por aba são lidos do banco, para que desvincular um morador, trocar a senha da conta compartilhada ou mudar uma aba valha **na hora**.

**R7. Condomínio que não está Ativo só aceita o fluxo de cadastro.** Pendente, Rejeitado ou Desativado: a Administração só consegue ver e corrigir o cadastro; as demais rotas respondem 403. (Hoje o model só tem `ativo`; os quatro status dependem do DER, ver seção 11.)

**R8. O ADM da plataforma não vê o dia a dia dos condomínios.** Ele acessa só: aprovação e edição de condomínios, suporte, auditoria e comunicados. Encomendas, visitantes, ocorrências, reservas e avisos de um condomínio são negados para o ADM.

**R9. Rotas da plataforma são separadas.** Só elas recebem um `condominio_id` na URL, sob `/api/v1/plataforma/...`, e exigem `administrador_plataforma = true`. Esse é o único lugar onde um ID de condomínio enviado pelo cliente é aceito.

**R10. A unidade vem do vínculo, não do cliente.** Quando uma rota do Morador recebe `unidade_id`, o servidor confirma que a unidade pertence a ele naquele condomínio; caso contrário, 404.

## 4. Token (JWT) e escolha do condomínio

Claims do access token (vida curta, por exemplo 15 minutos):

| Claim | Conteúdo | Observação |
| --- | --- | --- |
| `sub` | `usuarios.id` | Identidade |
| `cid` | `condominio_id` escolhido | Ausente para o ADM da plataforma |
| `sv` | versão da sessão do usuário | Trocar a senha ou o acesso da conta compartilhada incrementa e derruba as sessões (US-210) |
| `perfil` | perfil local | **Só para a interface** esconder menus. Nunca decide acesso (R6) |
| `exp`, `iat` | validade | |

As unidades **não** entram no token (R6).

Fluxo de login:

1. `POST /auth/login` valida credenciais. Se o usuário tem um único vínculo ativo, o token já vem com `cid`. Se tem vários, a resposta traz a lista de condomínios.
2. `POST /auth/selecionar-condominio` recebe o condomínio escolhido, **confirma que existe vínculo ativo** e emite novo token com `cid`.
3. Trocar de condomínio sempre passa pelo passo 2.

## 5. Ordem de checagem

Implementada uma única vez na dependência de autorização (US-1002). A primeira falha encerra a requisição.

| # | Etapa | O que verifica | Falha |
| --- | --- | --- | --- |
| 1 | Identidade | Token válido, não expirado, `sv` atual, usuário ativo | 401 |
| 2 | Condomínio | `cid` presente (ou rota de plataforma com `administrador_plataforma`), vínculo ativo no condomínio, condomínio Ativo (R7) | 403 |
| 3 | Perfil | O perfil do vínculo pode executar a **ação** no **módulo** (matriz da seção 7) | 403 |
| 4 | Unidade | Só para o Morador: a unidade pertence a ele (R10) e a **aba** correspondente está Com Acesso (seção 8) | 404 para unidade alheia, 403 para aba sem acesso |
| 5 | Recurso | O registro existe **dentro do condomínio** (R3/R4) | 404 |
| 6 | Regra de negócio | Exemplos: uma reserva por unidade, área e dia; retirada duplicada | 409 ou 422 |

Observação: a US-1002 lista "unidade, perfil". Aqui o **perfil vem antes da unidade** porque a unidade só se aplica ao Morador e a checagem de perfil é mais barata. O resultado para o usuário é o mesmo.

## 6. Códigos de erro

Usam o envelope já documentado em `api-contracts/health.md`: `{"error": {"code": "...", "message": "..."}}`.

| HTTP | `code` | Quando |
| --- | --- | --- |
| 401 | `not_authenticated` | Sem token, token inválido ou expirado, sessão derrubada, usuário inativo. Incluir `WWW-Authenticate: Bearer` |
| 403 | `forbidden` | Autenticado, mas sem permissão: perfil, aba Sem Acesso, vínculo inativo, condomínio não Ativo |
| 404 | `not_found` | Não existe **ou** é de outro condomínio / outra unidade (R4) |
| 409 | `conflict` | Conflito de regra, como reserva duplicada ou chave já usada |
| 422 | `validation_error` | Entrada inválida (já existe) |

Mensagens de 403 e 404 são genéricas e não citam o recurso, o condomínio ou a unidade.

## 7. Matriz perfil × módulo × ação

**Ações:** V = ver · C = criar · E = editar · D = desativar, cancelar ou desvincular (nenhum perfil apaga registro de forma definitiva).
**Escopo:** (U) só as unidades do Morador · (C) só o condomínio do token · (P) toda a plataforma.
**`[aba]`:** o Morador precisa estar Com Acesso na aba indicada (seção 8). **—** = negado.

| Módulo | Morador | Funcionário | Administração | ADM |
| --- | --- | --- | --- | --- |
| Conta própria | V E | V | V E | V E |
| Dados do condomínio | V (C), só o nome | V (C), só o nome | V E (C) | V E D (P) |
| Cadastro e aprovação do condomínio | — | — | C, e E para corrigir e reenviar o rejeitado (C) | V (P), aprovar, rejeitar, D (P) |
| Estrutura: blocos, andares, unidades | V (U) `[Unidades]` | V (C), só a identificação | V C E D (C). Não remove unidade com vínculo | V (P), só na análise do cadastro |
| Proprietário da unidade | V (U) `[Unidades]` | — | V C E (C) | — |
| Chave de acesso da unidade | — | — | V, gerar, regenerar, revogar (C) | — |
| Vínculo morador–unidade | C (solicitar com a chave), V do próprio status; convidar (U) `[Usuários]` | — | V (C), aprovar, rejeitar, D desvincular (C) | — |
| Permissões por aba dos moradores | V E (U) `[Usuários]` | — | — | — |
| Funcionários (lista de nomes, sem login) | — | V (C), só os nomes ativos | V C E D (C) | — |
| Conta compartilhada de Funcionários e responsáveis da Administração | — | — | V C E (C) | — |
| Encomendas | V (U) `[Encomendas]` | V C E (C). E = registrar retirada | V (C), relatório | — |
| Visitantes | V C E D (U) `[Visitantes]` | V (C), C visitante avulso, E registrar entrada e saída | V (C), relatório | — |
| Veículos | V C E D (U) `[Veículos]` | V (C) | V (C), relatório | — |
| Áreas comuns e bloqueio de datas | V (C), só áreas ativas `[Reserva de Áreas]` | — | V C E D (C) | — |
| Reservas | V C D (U), cancela só a própria `[Reserva de Áreas]` | — | V (C), D cancelar qualquer reserva, com motivo | — |
| Ocorrências | V C (U) e E para responder ou reabrir `[Ocorrências]` | — | V (C), E responder e mudar o status | — |
| Avisos do condomínio | V (C), só os vigentes | V (C), só os vigentes | V C E D (C) | — |
| Comunicados da plataforma | — | — | V (C), os que lhe foram enviados | V C D (P) |
| Chamados de suporte | — | — | V C (C), e mensagens no chamado | V E (P), atender |
| Auditoria | — | — | — | V (P) |

Regras que a tabela não mostra:

- **Reserva:** a agenda do Morador mostra apenas *livre*, *ocupado* ou *da minha unidade*. A API **nunca** devolve a identificação de outra unidade.
- **Encomenda:** só o Funcionário registra; ninguém edita os dados depois do registro, e correções ficam na auditoria.
- **Ocorrência:** o Funcionário não acessa o módulo.
- **Auditoria:** ninguém edita nem desativa registros; a aplicação só insere.
- **Chave de acesso:** o Morador a digita **uma vez**, para se vincular; ela nunca é devolvida a ele. Só a Administração a vê.

## 8. Permissões por aba do Morador (US-304)

Abas: **Unidades, Visitantes, Veículos, Reserva de Áreas, Encomendas, Ocorrências e Usuários**.

- Um Morador com **Com Acesso na aba Usuários** define Com Acesso ou Sem Acesso nas outras abas para cada morador da **mesma unidade**.
- A permissão é por **morador e unidade**, porque um morador pode estar em mais de uma unidade.
- A aba sem acesso responde **403** no backend mesmo que a tela seja burlada, e some da navegação do front.
- A mudança vale na próxima requisição (R6) e vai para a auditoria (quem mudou, para quem, de quê para quê).
- **Proposta de padrão** (confirmar com o Paulo): o primeiro morador vinculado à unidade nasce com acesso a todas as abas. Quem entra depois nasce Com Acesso em todas **menos Usuários**, até o responsável liberar.
- **Trava:** não é permitido retirar a aba Usuários de quem é o último a tê-la naquela unidade. Sem isso, ninguém mais consegue mudar permissões.
- Funcionário e Administração **não** têm permissão por aba: cada um enxerga os módulos da sua linha na matriz.

## 9. Contas compartilhadas e responsável pela ação

Como Funcionários e Administração usam uma conta única por condomínio, o nome de quem agiu não está no token. Por isso:

- **Encomenda:** o campo `recebido_por` é obrigatório e vem da lista de Funcionários cadastrados no condomínio.
- **Ações da Administração** listadas na seção 10: o campo `responsavel` é obrigatório e vem da lista de responsáveis do condomínio. O servidor valida que o nome pertence ao condomínio do token.
- A auditoria grava `usuario_id` (a conta) **e** o responsável informado.
- Trocar o acesso da conta compartilhada incrementa o `sv` e derruba as sessões ativas (US-210).

## 10. Ações críticas que vão para a auditoria

Registro de apenas inserção, com: usuário (conta), responsável informado, perfil, `condominio_id`, ação, recurso, valores antes e depois, IP e data/hora do servidor.

| Grupo | Ações |
| --- | --- |
| Condomínio | Aprovar, rejeitar (com motivo), desativar, reativar, reenviar cadastro, editar dados e estrutura |
| Acesso | Gerar, regenerar e revogar chave de acesso; aprovar, rejeitar e desfazer vínculo; mudar permissão por aba; trocar acesso da conta compartilhada |
| Pessoas | Cadastrar e desativar funcionário; alterar lista de responsáveis; editar proprietário da unidade |
| Operação | Cancelar reserva (Administração); bloquear data; alterar status de ocorrência; registrar retirada de encomenda; publicar ou editar aviso |
| Plataforma | Enviar comunicado; atender e fechar chamado |
| Segurança | Login falho; **acesso negado (403)**; tentativa de acessar recurso de outro condomínio (404 cross-tenant) |

## 11. Como esta matriz é testada

Os testes da US-1002 e da US-1001 saem desta tabela.

1. **Matriz parametrizada:** para cada linha da seção 7 e cada perfil, um teste chama a rota e confere 2xx, 403 ou 404.
2. **Isolamento entre condomínios:** dois condomínios com dados em todos os módulos. O usuário do A tenta ler, listar, editar e desativar o que é do B. Esperado: 404 ou lista vazia, nunca o dado.
3. **Entrada ignorada:** enviar `condominio_id` no corpo, na query e em cabeçalho não muda o resultado.
4. **Unidade alheia:** Morador acessa recurso de outra unidade do mesmo condomínio → 404.
5. **Aba sem acesso:** 403 no backend; mudança de permissão vale na requisição seguinte.
6. **Revogação imediata:** morador desvinculado perde o acesso sem esperar o token expirar.
7. **Condomínio não Ativo:** Pendente, Rejeitado e Desativado negam tudo, exceto o fluxo de cadastro.
8. **ADM:** não acessa encomendas, visitantes, ocorrências, reservas nem avisos de condomínio algum.
9. **Auditoria:** cada ação da seção 10 gera exatamente um evento, e um 403 gera evento de segurança.

## 12. Impactos no modelo de dados (para alinhar com o Davi)

O modelo atual não cobre ainda, e isso deve entrar numa migração **nova** (não editar a 0001):

- **Credenciais e login:** `senha_hash`, `telefone` (login por e-mail ou telefone) e `sessao_versao` (o `sv` do token) em `usuarios`.
- **Status do condomínio:** Pendente, Ativo, Rejeitado e Desativado no lugar do booleano `ativo`, mais o motivo da rejeição.
- **Chave de acesso por unidade** (única, regenerável) e **proprietário da unidade**.
- **Múltiplas unidades por morador:** hoje há no máximo uma unidade por vínculo (`unique(usuario_id, condominio_id)`). A US-302 ("minhas unidades") e esta matriz pedem uma tabela de vínculo **morador–unidade**, com a permissão por aba pendurada nela.
- **Funcionários (nomes) e responsáveis da Administração** como tabelas próprias, sem login.
- **Auditoria** de apenas inserção, com os campos da seção 10.
- **`condominio_id` e FK composta** em toda tabela nova.

## 13. Checklist para criar uma rota nova

- [ ] A rota usa a dependência de autorização com o par `módulo:ação` da seção 7.
- [ ] O repository recebe o contexto e filtra por `condominio_id` (e por unidades do Morador, quando for o caso).
- [ ] Nenhum `condominio_id` ou `perfil` é lido do corpo, da URL ou de cabeçalho.
- [ ] Recurso inexistente ou de outro condomínio responde 404.
- [ ] Ação crítica da seção 10 chama o serviço de auditoria, com o responsável quando a conta é compartilhada.
- [ ] Há testes negativos: outro condomínio, outra unidade, perfil errado e aba Sem Acesso.
