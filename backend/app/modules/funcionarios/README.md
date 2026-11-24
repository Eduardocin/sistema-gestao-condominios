# Funcionários e responsáveis

Backend da TASK-31 com os complementos da US-209, baseado em `docs/api-contracts/plataforma.md`, seção 5. Um funcionário é uma pessoa que identifica ações da portaria e não recebe conta de login.

| Rota | Acesso e resposta |
| --- | --- |
| `GET /api/v1/funcionarios` | Administração: dados completos; Funcionário: somente `id` e `nome` dos ativos |
| `POST /api/v1/funcionarios` | Administração; `201` com o funcionário criado |
| `GET /api/v1/funcionarios/{id}` | Administração; objeto com o mesmo schema do cadastro, inclusive desligados |
| `PUT /api/v1/funcionarios/{id}` | Administração; corrige dados com as mesmas validações do cadastro |
| `GET /api/v1/funcionarios/{id}/historico` | Administração; eventos limitados ao funcionário do próprio condomínio |
| `POST /api/v1/funcionarios/{id}/desligamento` | Administração; `200` com `ativo=false` e `desligado_em` |
| `GET /api/v1/responsaveis-administracao` | Administração; lista direta de `{id,nome,ativo}` |
| `POST /api/v1/responsaveis-administracao` | Administração; `{nome}`; `201` com o responsável |

A listagem de funcionários retorna `{items,page,page_size,total}`. Filtros: `ativo` (padrão `true`), `busca` por trecho literal do nome, `page>=1` e `page_size` entre 1 e 100. Ordenação alfabética por nome, com ID para desempate. Funcionário recebe somente ativos mesmo enviando `ativo=false`. A lista de responsáveis aceita `ativo`, também com padrão `true`.

O cadastro de funcionário recebe `nome`, `funcao` (`porteiro` ou `seguranca`), `telefone`, `email`, `foto_arquivo_id` opcional e `responsavel_id`. Desligamento recebe somente `responsavel_id`. Nome tem de 1 a 120 caracteres; telefone tem 10 ou 11 dígitos; e-mail é validado e normalizado. Foto precisa ser imagem do módulo `fotos`, enviada pela própria conta no mesmo condomínio. Responsável inexistente, inativo ou de outro condomínio e foto fora do escopo retornam `404` genérico. Desligar novamente retorna `409` (`ja_desligado`). Não há exclusão física.

Responsáveis têm nome de 1 a 100 caracteres, único entre ativos do condomínio ignorando caixa e espaços repetidos. Duplicidade retorna `409` (`nome_duplicado`). A gestão da própria lista dispensa `responsavel_id`, permitindo o primeiro cadastro. Essa lista é acessível à Administração em condomínios `pendente`, `rejeitado` ou `ativo`; `desativado` é bloqueado. As operações de funcionários exigem condomínio `ativo`. A dependência especial dos responsáveis não relaxa o contexto das demais rotas.

Todos os repositórios de negócio herdam de `RepositorioDoCondominio`: o condomínio vem do JWT validado e vínculo atual, jamais do cliente. Operação e auditoria compartilham transação e rollback. Eventos: `responsaveis.alterar`, `funcionario.cadastrar`, `funcionario.editar`, `funcionario.desativar`; guardam conta autenticada, perfil, condomínio, responsável quando aplicável, recurso, IP válido e alterações. Travas de linha protegem duplicidade de responsável e desligamentos concorrentes.

Nos complementos da US-209, detalhe, edição e histórico são exclusivos da Administração
do condomínio ativo. A Portaria continua com a lista restrita de nomes ativos e recebe
403 nas consultas novas. Funcionário inexistente ou de outro condomínio retorna 404,
inclusive no histórico. Funcionários desligados continuam consultáveis e editáveis,
preservando `ativo=false`, a data de desligamento, ID e referências anteriores.

A edição usa `FuncionarioEntrada`, `FuncionarioSaida`, a validação existente de responsável
e foto e a trava de linha já usada no desligamento. `PUT` exige todos os campos obrigatórios
do cadastro; foto nula ou omitida limpa a referência. Não aceita campos protegidos nem
funciona como PATCH. O evento central `funcionario.editar` guarda apenas os campos alterados,
na mesma transação da atualização. Sem mudança efetiva, não há evento novo.

Histórico: `{items,page,page_size,total}`, com `page>=1`, `page_size` de 1 a 100 (padrão 20),
ordem `criado_em DESC, id DESC`. Cada item expõe somente `acao`, `criado_em`,
`responsavel_nome` e `usuario` (`{id,nome}` ou nulo para autor ausente).
Consulta apenas os eventos de cadastro, edição e desligamento com o condomínio, tipo de
recurso e funcionário corretos; não carrega os metadados antes/depois. Um funcionário
existente sem eventos retorna lista vazia. A auditoria geral permanece exclusiva do ADM.
Esta exceção restrita de histórico continua sujeita à revisão de Gabriel, sem aprovação
presumida ou ampliação das permissões globais.

## US-210 — conta compartilhada e responsáveis

Completa `PUT /api/v1/responsaveis-administracao/{id}` (`{nome}`) e
`POST /api/v1/responsaveis-administracao/{id}/desativacao` (`{}`). Reutiliza GET/POST,
normalização, contexto de cadastro e auditoria `responsaveis.alterar`, sem responsável
previamente selecionado. Duplicidade entre ativos: 409 `nome_duplicado`; último ativo:
409 `ultimo_responsavel`; desativação repetida: 409 `ja_desativado`. IDs e referências
permanecem. Editar um inativo não o reativa. Repetir o mesmo nome não gera evento.

`GET /api/v1/conta-funcionarios` devolve `{login,atualizada_em}` ou 404.
`PUT` recebe `{login,senha,responsavel_id}` e cria/troca a conta, retornando o mesmo
formato. Só Administração de condomínio ativo passa pelas permissões centrais
`contas_compartilhadas:ver/editar`. A gestão dos responsáveis continua disponível em
pendente/rejeitado/ativo; desativado é bloqueado também depois de esperar a trava.

A identidade dedicada usa `Usuario` sem tipo próprio, telefone/documento ou privilégio
de plataforma, e exatamente um `VinculoCondominio` de Funcionários, sem unidade.
Nunca se associa um usuário pelo e-mail informado. Colisão global de e-mail retorna
409 `login_indisponivel`; conta/vínculo inativo, sem senha ou incompatível retorna
409 `conta_compartilhada_incompativel`, sem criação paralela ou reativação automática.
Os fluxos de cadastro/vínculo existentes exigem tipo próprio e não associam essa conta
a outro perfil/condomínio; o serviço revalida todos os seus vínculos antes da troca.

Login é e-mail normalizado; senha segue o validador compartilhado e Argon2id.
Mudança efetiva preserva IDs e incrementa `sessao_versao`, derrubando access/refresh
antigos. Repetição idempotente preserva hash, versão, data e auditoria. Não emite tokens.
`credenciais_atualizadas_em` fica no vínculo, é gravada na criação/troca e corresponde
à saída `atualizada_em`. Legados sem data conhecida permanecem com `null`, sem inventar
uma data. Conta, vínculo e evento `conta_compartilhada.trocar_acesso` são transacionais;
o evento recebe só login/versão, nunca senha, hash ou token.

A migration `20261124_0009`, sobre `20261121_0008`, adiciona essa coluna nullable e dois
índices únicos parciais para `perfil='funcionario'`: por condomínio e por usuário,
incluindo vínculos inativos. Não restringe múltiplos condomínios de moradores ou
Administração. Antes da alteração, bloqueia gravações nas tabelas envolvidas e recusa
duplicidades, contas pessoais/plataforma, unidades indevidas e outros vínculos da mesma
conta. A correção desses legados é explícita; não exclui nem consolida dados. Downgrade
remove somente os índices e a coluna nova, preservando identidades/vínculos/históricos.

Criação/troca e gestão da lista usam condomínio `FOR NO KEY UPDATE` antes do responsável
(`FOR SHARE` na validação; `FOR UPDATE` na edição/desativação), e a troca depois bloqueia
a conta `FOR NO KEY UPDATE`, recarregando os dados. Isso serializa criação, versões,
nomes e proteção do último ativo e evita inverter a trava do responsável com as FKs de
outras operações. Falhas de auditoria ou persistência revertem a transação inteira.

Testes da entrega: [US-210](../../../tests/us210/), com HTTP/JWT reais, isolamento,
tokens antigos, idempotência, legados, rollback, índices no PostgreSQL e concorrência
por conexões independentes. Não há frontend, reativação ou exclusão física. A US-208
permanece fora do escopo; esta entrega não conclui a TASK-51 inteira.

Verificação: `tests/test_contas_funcionarios_api.py` usa HTTP real, JWT e PostgreSQL migrado; cobre perfis, A/B, filtros, fotos, bootstrap, auditoria e rollback controlado.

Os [testes dos complementos](../../../tests/test_funcionarios_complementos_api.py) cobrem detalhe, edição, histórico, validações, perfis, isolamento, preservação de desligados e encomendas, campos expostos e rollback após auditoria ou falha de commit.
