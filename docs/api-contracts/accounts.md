# Contas e perfil pessoal (TASK-27)

Rotas implementadas em `backend/app/modules/usuarios`.

## Cadastro público

`POST /api/v1/usuarios/moradores` recebe `nome`, `email`, `cpf`, `senha` e `chave_acesso` válida.
`POST /api/v1/usuarios/administracao` recebe os mesmos campos e `condominio_id`.

O e-mail é normalizado para minúsculas e deve ser único. O CPF é validado, normalizado para
11 dígitos e único. A senha exige ao menos 12 caracteres, letra maiúscula, minúscula, número e
símbolo. Respostas de sucesso são `201` e contêm a conta com `status_conta: "pendente"`.

O cadastro de Administração também cria um vínculo `administracao` inativo. Cadastros não ativam
usuários nem vínculos e não emitem tokens. A aprovação futura deve ativar a conta e o vínculo por
um caso de uso autorizado; contas pendentes não autenticam.

O cadastro de Morador exige chave válida de condomínio aprovado; a chave é consumida na mesma
transação da conta e do vínculo pendente. Cadastro sem chave válida retorna `422`. Consulte o
contrato da [aprovação e das chaves de acesso](./condominium-approval.md).
Depois de ativar a conta por seu fluxo de aprovação, o Morador solicita a unidade; o vínculo de
condomínio permanece inativo até a Administração aprovar essa solicitação. Veja o contrato de
[vínculo Morador–Unidade](./unit-resident-link.md).

Exemplo de cadastro de morador:

```json
{
  "nome": "Ana Martins",
  "email": "ana@exemplo.test",
  "cpf": "529.982.247-25",
  "senha": "Senha#Forte123"
}
```

Erro de validação: `422`; e-mail ou CPF duplicado: `409`; condomínio inexistente no cadastro da
Administração: `404`.

## Perfil autenticado

- `GET /api/v1/usuarios/me`: consulta os dados pessoais da conta autenticada.
- `PATCH /api/v1/usuarios/me`: atualiza `nome`, `email` e/ou `cpf` da própria conta. Não aceita
  usuário-alvo no path ou no body.

Alterações geram evento de auditoria `edicao_conta`; cadastros geram `criacao_conta`. A senha e o
CPF integral não são copiados para os dados antes/depois da auditoria. Para perfis compartilhados
(`funcionario` e `administracao`), a edição exige `nome_responsavel`.

## Aprovação pendente

O ciclo de aprovação/ativação não é exposto por estas rotas. A TASK-29/30 deve atualizar `status_conta`
para `ativo` e `usuarios.ativo` para `true` apenas depois da aprovação pertinente; para Administração,
também deve ativar o vínculo do condomínio. Esta rota não permite ao titular aprovar a própria conta.
