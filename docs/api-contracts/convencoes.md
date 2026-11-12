# Convenções comuns dos contratos REST

Status: proposta para revisão no portão dos leads. Vale para [nucleo.md](nucleo.md) (TASK-78), [convivencia.md](convivencia.md) (TASK-10), [plataforma.md](plataforma.md) (TASK-11) e [portaria.md](portaria.md) (TASK-12). Onde este documento repete o que já está em `portaria.md` ou `health.md`, o texto é o mesmo; o que é novo está marcado como **proposta**.

Os contratos descrevem o conjunto planejado. Consulte os routers e o OpenAPI para
as rotas implementadas; autenticação, permissões por aba e arquivos já têm APIs.
Rotas protegidas usam a autorização central (US-1002) e a [matriz de permissões](../permissoes-e-multitenant.md).

## 1. Base e formato

- Prefixo `/api/v1`. JSON em UTF-8. IDs são UUID. Nomes de rotas, campos e valores de status em português, `snake_case`.
- Datas de registro (`criado_em`, `registrada_em`, `cancelada_em` e semelhantes) são geradas pelo servidor e nunca aceitas no corpo. Timestamps são ISO 8601 com fuso (`2026-11-14T18:00:00Z`). Datas puras são `AAAA-MM-DD` e horas cheias são `HH:MM`.
- **Fuso do condomínio:** datas e horários de negócio (reserva, período de visitante, vigência de aviso) valem no fuso do condomínio. O DER ainda não tem coluna de fuso; **proposta:** no MVP, `America/Sao_Paulo` fixo, definido em configuração, e a coluna entra se algum dia houver condomínio em outro fuso.
- Criação retorna 201 com o objeto e o cabeçalho `Location`. Consulta retorna o objeto direto. Listas seguem o formato abaixo.
- Escrita rejeita campos desconhecidos (`extra="forbid"` nos schemas Pydantic). Um `condominio_id`, `perfil` ou `usuario_id` no corpo é rejeitado com 422, nunca usado (R1).

## 2. Autorização

Toda rota autenticada passa pela dependência da US-1002, na ordem da seção 5 da matriz. Nas tabelas dos contratos, a coluna **Permissão** indica o perfil e, para o Morador, a aba exigida, no mesmo vocabulário da matriz (`[Reserva de Áreas]`, `[Encomendas]` etc.). O nome técnico das abas nas respostas e nos corpos é o do DER: `unidades`, `visitantes`, `veiculos`, `reservas`, `encomendas`, `ocorrencias`, `usuarios`.

### Rotas que não exigem `cid` no token (proposta)

A regra R1 diz que o condomínio vem do token. Seis grupos de rotas acontecem **antes** de existir um condomínio no token e precisam de uma variante da dependência ("autenticado, sem condomínio"):

| Rota | Quem | Por quê |
| --- | --- | --- |
| `POST /auth/login`, `POST /contas/morador`, `POST /contas/administracao`, recuperação de senha | Público | Ainda não há token |
| `POST /auth/selecionar-condominio` | Qualquer conta com vínculo | É ela que coloca o `cid` no token |
| `POST /vinculos/chave` | Conta de morador | A chave é que revela o condomínio |
| `POST /condominios` e `GET /condominios/meus` | Conta de Administração | O prédio ainda não existe ou é escolhido depois |
| `/plataforma/...` | ADM (`administrador_plataforma`) | O ADM nunca tem `cid` (R8, R9) |
| `GET /auth/me`, `GET /contas/me` | Qualquer conta | Tela inicial antes da escolha do condomínio |

## 3. Listas e paginação

Igual a `portaria.md`: `{"items": [], "page": 1, "page_size": 20, "total": 0}`, com `page` >= 1 e `page_size` de 1 a 100. Ordenação padrão por data decrescente com ID como desempate, salvo quando o contrato disser outra. Busca e filtros acontecem sempre **dentro** do escopo autorizado.

## 4. Erros

Envelope de `health.md`: `{"error": {"code": "...", "message": "..."}}`. Mensagens de 403 e 404 são genéricas e não citam o recurso, o condomínio ou a unidade.

| HTTP | `code` | Quando |
| --- | --- | --- |
| 401 | `not_authenticated` | Token ausente, inválido, expirado, sessão derrubada ou usuário inativo; incluir `WWW-Authenticate: Bearer` |
| 403 | `forbidden` | Perfil, aba, vínculo ou condomínio sem acesso |
| 404 | `not_found` | Recurso inexistente **ou** de outro condomínio ou unidade (R4) |
| 409 | `conflict` | Conflito de regra: reserva duplicada, transição repetida, chave já vinculada |
| 422 | `validation_error` | Entrada inválida |
| 500 | `internal_error` | Falha inesperada, mensagem genérica |

### Extensões propostas ao envelope

Três pequenas extensões, todas **aditivas** (quem ignora os campos novos continua funcionando). Dependem da aprovação do Gabriel, dono do envelope:

1. **`error.details` no 422.** Hoje `validation_error` devolve só "Dados inválidos.", e o assistente de cadastro do prédio (um pedido com dezenas de campos) precisa dizer **qual** campo falhou. Proposta: `"details": [{"campo": "blocos[0].andares[2].unidades[1]", "mensagem": "Já existe uma unidade com esse nome neste andar."}]`. Nunca devolver o valor enviado (pode ser senha ou dado pessoal), só o caminho e a mensagem.
2. **`error.reason` no 409.** O front precisa distinguir "esta unidade já reservou hoje" de "alguém acabou de pegar o horário" sem ler a mensagem. Proposta: `"reason": "reserva_duplicada_unidade"`, em `snake_case`, listado em cada contrato. A mensagem continua em português claro para exibir ao usuário.
3. **429 `too_many_attempts`.** Para o limite de tentativas erradas de chave de acesso (US-301). Resposta com `Retry-After` em segundos.

## 5. Ações explícitas, sem `DELETE`

- Mudança de estado é uma ação com nome de substantivo, no corpo de um `POST`: `/.../aprovacao`, `/.../rejeicao`, `/.../cancelamento`, `/.../encerramento`, `/.../desativacao`, `/.../reativacao`, `/.../resolucao`, `/.../reabertura`, `/.../regeneracao`, `/.../revogacao`, `/.../desvinculacao`. Não há `PATCH status` genérico, como já definido em `portaria.md`.
- **Nenhum perfil apaga registro** (matriz, seção 7): não existe `DELETE` nestes contratos. "Remover" significa desativar ou mudar de estado, e o registro continua nos históricos.
- Repetir uma ação que já foi feita (cancelar uma reserva cancelada) retorna 409.

## 6. Responsável nas ações da Administração

Funcionários e Administração usam conta compartilhada, então o token não diz quem agiu (matriz, seção 9). Toda ação da Administração que a matriz lista como crítica recebe `responsavel_id` no corpo:

- O servidor confirma que o ID está na lista de **responsáveis da Administração** do condomínio do token, ativo. Caso contrário, 404.
- O nome entra na resposta e na auditoria, junto com a conta autenticada.
- Para ações do Funcionário, o campo equivalente é `funcionario_id` (lista de funcionários ativos), como em `portaria.md`.

## 7. Arquivos

Fotos, anexos e documentos chegam como `*_arquivo_id`. O upload, a validação de tipo e tamanho, a leitura protegida e a limpeza ficam na TASK-26 (US-1003, Eduardo). Estes contratos nunca aceitam URL, caminho de disco nem base64. O servidor confere que o arquivo pertence ao condomínio do contexto e que o enviou o próprio usuário. Limites propostos, sujeitos à TASK-26: imagens JPG/PNG/WebP até 5 MB; vídeo MP4 até 50 MB, só em ocorrências.

## 8. Do contrato ao OpenAPI

Implementação interna da TASK-26 e políticas atuais: [storage.md](../storage.md).
A API de arquivos já integra autorização central e persistência definitiva; consulte
[storage.md](../storage.md) para rotas, payload binário e regras por recurso.
Para suporte, PDF até 5 MiB é uma proposta adicional a revisar com Tude.

O FastAPI gera o `/openapi.json` a partir dos schemas Pydantic. Este documento é o contrato "humano" que os schemas devem reproduzir campo a campo. Ao implementar uma rota, o PR atualiza o contrato se algo mudou e inclui testes de contrato (status, campos e códigos de erro) além dos testes negativos da seção 11 da matriz.
