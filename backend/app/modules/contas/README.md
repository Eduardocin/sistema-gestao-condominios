# Contas

Implementa os cadastros existentes da TASK-31 e o complemento da TASK-27 (US-104 e US-201),
conforme [nucleo.md](../../../../docs/api-contracts/nucleo.md), seção 3:

- `POST /api/v1/contas/morador`: público; nome completo, telefone, e-mail e senha.
- `POST /api/v1/contas/administracao`: público; os mesmos campos e CPF/CNPJ válido.
- `GET /api/v1/contas/me`: autenticado; somente os dados da própria conta.
- `PUT /api/v1/contas/me`: autenticado; substitui nome, telefone e e-mail do próprio cadastro
  global de Morador ou Administração. Retorna o mesmo objeto da consulta.

Os pedidos aceitam somente os campos declarados. Nomes têm espaços normalizados e e-mails ficam em minúsculas. Telefone e documento chegam somente com dígitos. A validação de CPF/CNPJ confere os dois dígitos verificadores. A senha tem de 8 a 128 caracteres, ao menos uma letra e um dígito e deve ser diferente do e-mail; somente seu hash Argon2id é persistido.

As duas rotas retornam `201` com o mesmo `LoginResponse` do login. O cadastro não cria condomínio nem vínculo: a sessão começa sem `cid` e pode ser usada imediatamente em `/auth/me` e `/auth/refresh`. O `tipo_cadastro` é persistido na tabela existente, sem alterar o formato público da sessão.

Duplicidades retornam `409 conflict`, com `reason` igual a `email_ja_cadastrado`, `telefone_ja_cadastrado` ou `documento_ja_cadastrado`. As constraints do banco também protegem pedidos concorrentes. Demais entradas inválidas retornam `422 validation_error` sem repetir valores pessoais ou senhas.

O service controla a transação; as consultas ficam em `repository.py`. Emissão e apresentação de sessão são reutilizadas de `auth/service.py` e `auth/presentation.py`, evitando um segundo mecanismo de autenticação.

## Perfil e segurança

Consulta e edição retornam `id`, `nome`, `email`, `telefone`, `tipo_cadastro`, `documento` e
`foto_arquivo_id`. Os quatro últimos campos podem ser nulos em contas legadas. Senha, hash,
tokens e privilégios não são serializados. O documento aparece somente ao titular autenticado.

`PUT` exige os três campos editáveis e rejeita qualquer outro campo (422), inclusive documento,
tipo de cadastro, senha, privilégios, IDs e referências de arquivos. Usa a mesma normalização
e os mesmos limites do cadastro; Morador continua exigindo nome completo. E-mail/telefone
da própria conta podem ser mantidos, mas não podem pertencer a outra conta. As constraints
também protegem atualizações concorrentes (409 com os mesmos `reason` do cadastro).

Não há ID de destino na rota. A identidade vem de `get_usuario_autenticado`, sem exigir
condomínio, e a escrita trava apenas o usuário autenticado. O `cid` eventualmente presente
no JWT não muda o usuário editado nem transforma esta ação global em ação de condomínio.
Edição preserva senha, `sessao_versao`, documento, tipo, privilégios e vínculos.
Contas sem `tipo_cadastro` (incluindo compartilhadas e ADM da plataforma) podem consultar
os próprios dados, mas recebem 403 na edição neste recorte. A gestão de acesso compartilhado
continua no fluxo da US-210, com responsável e revogação de sessões; esta rota não o contorna.

## Auditoria e limites

`conta.criar` e `conta.editar` usam `registrar_acao`, na mesma sessão e transação da conta.
Recurso: `usuario`, com o ID da conta; identidade e IP vêm do servidor. Condomínio, perfil
local e responsável ficam nulos, pois são operações de cadastro global, sem papel local
validado. O cadastro registra somente os campos públicos; a edição registra somente os
campos alterados. A sanitização central mascara o documento e nunca recebe senha/hash/tokens.
Falhas na auditoria ou no commit revertem a conta e o evento juntos.

O card menciona conta pendente, enquanto o contrato prevê autenticação imediata. Mantém-se
a sessão imediata e a conta sem condomínio/unidade: autenticar não concede vínculo ou acesso.
Aprovação de condomínio (TASK-29) e vínculo de Morador (TASK-30) permanecem separados.

`GET/PUT /contas/me` se sobrepõem ao resumo da US-103 (Gabriel, Sprint 3); a TASK-27 entrega
apenas consulta e edição de nome/e-mail/telefone. Troca/recuperação de senha e outros tipos
de conta não são antecipados. Foto continua opcional: a referência existente é retornada,
mas o upload global de conta ainda não está disponível no [storage](../../../../docs/storage.md).
Não se reutilizam arquivos de condomínio para contornar essa limitação. O documento
comprobatório permanece no cadastro do condomínio. Nenhuma migration ou dependência nova.

## Senha (TASK-53, parte A)

- `PUT /api/v1/contas/me/senha`: autenticado (sem exigir `cid`), `{"senha_atual", "senha_nova"}`.
  Só cadastro global (conta compartilhada e ADM: 403, como no `PUT /contas/me`). A conta fica
  travada (`FOR UPDATE`) durante a troca. Senha atual errada: 422 `senha_atual_incorreta`, contada
  no `LoginRateLimiter` com a chave `senha:{usuario_id}`; no limite, 429 com `Retry-After`, como no
  login; acerto zera o contador. Igual à atual: 422 `senha_nova_igual_atual`. Sucesso: hash novo,
  `sessao_versao + 1`, tokens de recuperação pendentes inutilizados e o mesmo `LoginResponse` do
  login, preservando o `cid` selecionado quando continua ativo e liberado (os tokens antigos caem).
- `POST /api/v1/contas/redefinicao-senha`: público, `{"token", "senha_nova"}`, 204 sem sessão. O
  banco guarda só `hash_do_token(token)` (SHA-256 hexadecimal, em `auth/security.py`; a parte B usa
  a mesma função). Numa transação: localiza o dono, trava a conta (`FOR UPDATE`), executa `UPDATE`
  condicional que consome o token, grava a senha nova, soma `sessao_versao + 1`, inutiliza demais
  tokens pendentes da conta e audita; após o commit, limpa eventual bloqueio da conta no
  `LoginRateLimiter`. Qualquer falha (inclusive senha igual ao e-mail) desfaz tudo e o token
  continua valendo. Inexistente, expirado, usado ou de conta inativa/sem cadastro próprio: o mesmo
  422 `token_invalido`.
- A regra da senha nova é a do cadastro, numa só função (`conferir_senha` em `schemas.py`). A
  comparação com o e-mail é feita no service, que é quem conhece a conta.
- Auditoria: `conta.senha_alterar` e `conta.senha_redefinir`, com só `sessao_versao` em
  `antes`/`depois`. Na rota pública, a identidade auditada é a dona do token, como em `conta.criar`.
- Pendente (parte B): `POST /contas/recuperacao-senha`, que gera o token e envia o e-mail
  (depende da TASK-50).
- **Divergência documental:** o card do Notion cita `/auth/esqueci-senha` e
  `/auth/redefinir-senha`. Vale o contrato (`nucleo.md`, seção 3.3): as rotas ficam em `/contas`.

Testes: [cadastros existentes](../../../tests/test_contas_funcionarios_api.py) e
[TASK-27](../../../tests/test_contas_perfil_api.py), [senha](../../../tests/test_contas_senha_api.py) e
[concorrência do token](../../../tests/test_contas_senha_concorrencia.py), contra PostgreSQL exclusivo migrado
(`TEST_DATABASE_URL`), com login real, isolamento de identidade, campos protegidos,
unicidade inclusive no banco, auditoria e falhas transacionais simuladas.
