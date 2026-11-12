# Contas

Implementa o recorte de cadastro da TASK-31, conforme `docs/api-contracts/nucleo.md`, seção 3:

- `POST /api/v1/contas/morador`: público; nome completo, telefone, e-mail e senha.
- `POST /api/v1/contas/administracao`: público; os mesmos campos e CPF/CNPJ válido.

Os pedidos aceitam somente os campos declarados. Nomes têm espaços normalizados e e-mails ficam em minúsculas. Telefone e documento chegam somente com dígitos. A validação de CPF/CNPJ confere os dois dígitos verificadores. A senha tem de 8 a 128 caracteres, ao menos uma letra e um dígito e deve ser diferente do e-mail; somente seu hash Argon2id é persistido.

As duas rotas retornam `201` com o mesmo `LoginResponse` do login. O cadastro não cria condomínio nem vínculo: a sessão começa sem `cid` e pode ser usada imediatamente em `/auth/me` e `/auth/refresh`. O `tipo_cadastro` é persistido na tabela existente, sem alterar o formato público da sessão.

Duplicidades retornam `409 conflict`, com `reason` igual a `email_ja_cadastrado`, `telefone_ja_cadastrado` ou `documento_ja_cadastrado`. As constraints do banco também protegem pedidos concorrentes. Demais entradas inválidas retornam `422 validation_error` sem repetir valores pessoais ou senhas.

O service controla a transação; as consultas ficam em `repository.py`. Emissão e apresentação de sessão são reutilizadas de `auth/service.py` e `auth/presentation.py`, evitando um segundo mecanismo de autenticação.

Ainda fora deste recorte: edição e foto de conta, recuperação de senha, cadastro do prédio e vínculo por chave. A criação de Administração não significa aprovação de um condomínio.

Verificação: `tests/test_contas_funcionarios_api.py`, contra PostgreSQL dedicado migrado (`TEST_DATABASE_URL`), cobre cadastro, login com a senha criada, JWT utilizável, validação e conflitos.
