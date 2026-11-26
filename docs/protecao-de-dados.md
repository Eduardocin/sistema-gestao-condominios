# Proteção de dados pessoais (LGPD básico, US-1007 / TASK-54)

Este documento descreve **o que o sistema faz hoje**, derivado dos models e do código do backend. Não é uma política jurídica. O que ainda não existe está em [Limitações conhecidas e pendências](#limitações-conhecidas-e-pendências).

## 1. Dados pessoais guardados

| Tabela | Colunas com dado pessoal | Finalidade |
| --- | --- | --- |
| `usuarios` | `nome`, `email`, `telefone`, `documento` (CPF/CNPJ da conta de Administração), `foto_arquivo_id`, `senha_hash`, `email_confirmado_em`, `consentimento_dados_em` | Login (US-101), cadastro de Morador e Administração (US-104, US-201) |
| `proprietarios_unidade` | `nome`, `documento`, `emails`, `whatsapps`, `telefone`, `foto_arquivo_id` | Proprietário da unidade, cadastrado pela Administração (US-207) |
| `moradores_unidade` | `parentesco` | Vínculo do Morador com a unidade (US-301) |
| `convites_morador` | `email`, `parentesco` (o convite guarda só o `token_hash`) | Convite de outro morador (US-303) |
| `funcionarios` | `nome`, `telefone`, `email`, `foto_arquivo_id` | Pessoas da portaria, sem login (US-209) |
| `responsaveis_administracao` | `nome` | Quem agiu pela conta compartilhada da Administração |
| `visitantes` | `nome`, `cpf`, `idade`, `observacoes` | Autorização de visita (US-501) |
| `veiculos` | `placa` | Cadastro de veículos (US-502) |
| `contatos_portaria`, `registros_visita` | dados da visita e de quem autorizou | Registro de entrada e saída (US-503) |
| `encomendas`, `ocorrencias`, `ocorrencia_interacoes`, `avisos` | nomes e texto livre digitado pelas pessoas | Operação do condomínio |
| `arquivos` | `nome_original` e o objeto no storage (fotos, anexos, documentos) | Uploads (US-1003) |
| `envios_email` | `destinatario` | Fila de e-mail |
| `registros_auditoria` | `usuario_id`, `responsavel_nome`, `ip`, `antes`/`depois` sanitizados | Trilha de ações críticas (US-1004) |
| `tokens_recuperacao_senha` | só `token_hash` | Redefinição de senha (US-102) |

CNPJ do condomínio (`condominios.cnpj`) é de pessoa jurídica e não é tratado como dado pessoal.

## 2. Quem acessa (por perfil)

O acesso segue a [matriz de permissões](permissoes-e-multitenant.md). O isolamento por `condominio_id` vale para tudo: dado de outro condomínio responde 404.

| Dado | Morador | Funcionário | Administração | ADM da plataforma |
| --- | --- | --- | --- | --- |
| Própria conta (`/contas/me`) | Completo | Completo | Completo | Completo |
| Proprietário da unidade | Nome, foto e contatos, **nunca o documento** | — | Completo (gere o cadastro) | — |
| Funcionários | — | Só `id` e `nome` dos ativos | Lista com telefone mascarado; detalhe completo | — |
| Visitantes | Os da própria unidade, com CPF | Nome e unidade, sem CPF | — | — |
| Auditoria | — | — | — | Completa, com IP e documentos mascarados |
| Fila de cadastro de condomínios | — | — | — | Nome e e-mail de quem enviou |

## 3. Como são protegidos

- **Senha:** só o hash argon2id (`usuarios.senha_hash`), nunca em resposta, log ou auditoria. Trocar ou redefinir a senha soma 1 em `sessao_versao` e derruba os tokens antigos.
- **Tokens de uso único:** o banco guarda só o SHA-256 (`token_hash`) do link de recuperação e do convite.
- **Formato no banco:** CPF, CNPJ e telefone só com dígitos; a máscara é aplicada na saída.
- **Máscara nas respostas** (`app/core/mascaras.py`): `***.456.789-**` (CPF), `**.***.123/0001-**` (CNPJ), `*******4321` (telefone), `a***@dominio.com` (e-mail). Hoje aplicada no telefone da lista de funcionários e nos documentos da auditoria.
- **Auditoria sanitizada** (`app/modules/auditoria/sanitizacao.py`): remove senhas, hashes, tokens, códigos de chave e segredos; mascara documentos com a mesma função das respostas.
- **Arquivos:** bucket privado; download por URL assinada que vale de 1 a 300 segundos (`STORAGE_URL_SECONDS`, padrão 60).
- **Logs filtrados** (`app/core/logging_seguro.py`): a mensagem e o traceback passam por um filtro que redige CPF, CNPJ, e-mail, JWT, `Bearer ...` e pares `senha=`, `token=`, `secret=` e semelhantes. No log de acesso do uvicorn a query string é removida.
- **Cabeçalhos de segurança** (`app/core/cabecalhos.py`), em todas as respostas, inclusive de erro: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` em `/api/`, CSP `default-src 'none'; frame-ancestors 'none'` (exceto nas páginas de documentação) e HSTS em produção.
- **Produção** (`app/core/config.py`): `/docs`, `/redoc` e `/openapi.json` desligados; a API recusa subir com o segredo JWT padrão, a senha padrão do banco, as chaves padrão do storage ou CORS com `*` ou origem `http://`.
- **Revisão automática:** `backend/tests/test_vazamento_dados.py` falha se um schema de resposta ganhar campo sensível sem justificativa escrita no próprio teste.

## 4. Quem vê CPF e telefone

| Dado | Rota | Quem vê | Forma |
| --- | --- | --- | --- |
| CPF/CNPJ da conta | `GET/PUT /contas/me` | Titular | Completo |
| CPF/CNPJ da conta | `GET /plataforma/auditoria` | ADM | Mascarado |
| Telefone da conta | `GET/PUT /contas/me` | Titular | Completo |
| Documento do proprietário | `GET /unidades/{id}`, `PUT /unidades/{id}/proprietario` | Administração | Completo |
| Documento do proprietário | `/minhas-unidades` | Morador | **Não aparece** |
| Telefone e WhatsApp do proprietário | `GET /unidades/{id}` | Administração | Completo |
| Telefone e WhatsApp do proprietário | `/minhas-unidades` | Morador | Completo (é o contato) |
| Telefone do funcionário | `GET /funcionarios` | Administração | Mascarado |
| Telefone do funcionário | `GET /funcionarios/{id}`, cadastro e edição | Administração | Completo |
| CPF do visitante | `/visitantes` (lista e detalhe) | Morador da unidade | Completo (a definir pelo grupo, ver pendências) |
| CPF do visitante | `/portaria/visitantes`, `busca-documento` | Funcionário | Não aparece; a busca recebe o CPF no corpo de um `POST` |

## Limitações conhecidas e pendências

- **Exclusão, portabilidade e retenção:** não há rotina para nenhuma delas. Nada é apagado: registros são desativados ou mudam de status (`ON DELETE RESTRICT`). Prazo de retenção: **a definir pelo grupo**.
- **Consentimento:** a coluna `usuarios.consentimento_dados_em` existe, mas nenhum fluxo grava nela (conferido no código). Coleta e registro do consentimento: **a definir pelo grupo**.
- **IP na auditoria:** é gravado e aparece na consulta da auditoria, que só o ADM acessa.
- **CPF do visitante na lista do Morador:** sai completo porque a tela de edição usa o valor da lista. Mascarar exige o front buscar o detalhe antes de editar: **a definir pelo grupo**.
- **E-mail na lista de funcionários e na fila do ADM:** sai completo, porque é o contato exibido. **A definir pelo grupo** se deve ser mascarado.
- **Texto livre** (observações, ocorrências, avisos) pode conter dado pessoal digitado pelas pessoas; não há filtro nesses campos.
- **Chave de acesso** da unidade é guardada em texto, porque a Administração precisa consultá-la (decisão 7 do [modelo de dados](modelo-de-dados.md)).
