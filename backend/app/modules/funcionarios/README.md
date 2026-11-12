# Funcionários e responsáveis

Recorte da TASK-31 baseado em `docs/api-contracts/plataforma.md`, seção 5. Um funcionário é uma pessoa que identifica ações da portaria e não recebe conta de login.

| Rota | Acesso e resposta |
| --- | --- |
| `GET /api/v1/funcionarios` | Administração: dados completos; Funcionário: somente `id` e `nome` dos ativos |
| `POST /api/v1/funcionarios` | Administração; `201` com o funcionário criado |
| `POST /api/v1/funcionarios/{id}/desligamento` | Administração; `200` com `ativo=false` e `desligado_em` |
| `GET /api/v1/responsaveis-administracao` | Administração; lista direta de `{id,nome,ativo}` |
| `POST /api/v1/responsaveis-administracao` | Administração; `{nome}`; `201` com o responsável |

A listagem de funcionários retorna `{items,page,page_size,total}`. Filtros: `ativo` (padrão `true`), `busca` por trecho literal do nome, `page>=1` e `page_size` entre 1 e 100. Ordenação alfabética por nome, com ID para desempate. Funcionário recebe somente ativos mesmo enviando `ativo=false`. A lista de responsáveis aceita `ativo`, também com padrão `true`.

O cadastro de funcionário recebe `nome`, `funcao` (`porteiro` ou `seguranca`), `telefone`, `email`, `foto_arquivo_id` opcional e `responsavel_id`. Desligamento recebe somente `responsavel_id`. Nome tem de 1 a 120 caracteres; telefone tem 10 ou 11 dígitos; e-mail é validado e normalizado. Foto precisa ser imagem do módulo `fotos`, enviada pela própria conta no mesmo condomínio. Responsável inexistente, inativo ou de outro condomínio e foto fora do escopo retornam `404` genérico. Desligar novamente retorna `409` (`ja_desligado`). Não há exclusão física.

Responsáveis têm nome de 1 a 100 caracteres, único entre ativos do condomínio ignorando caixa e espaços repetidos. Duplicidade retorna `409` (`nome_duplicado`). A gestão da própria lista dispensa `responsavel_id`, permitindo o primeiro cadastro. Essa lista é acessível à Administração em condomínios `pendente`, `rejeitado` ou `ativo`; `desativado` é bloqueado. As operações de funcionários exigem condomínio `ativo`. A dependência especial dos responsáveis não relaxa o contexto das demais rotas.

Todos os repositórios de negócio herdam de `RepositorioDoCondominio`: o condomínio vem do JWT validado e vínculo atual, jamais do cliente. Operação e auditoria compartilham transação e rollback. Eventos: `responsaveis.alterar`, `funcionario.cadastrar`, `funcionario.desativar`; guardam conta autenticada, perfil, condomínio, responsável quando aplicável, recurso, IP válido e alterações. Travas de linha protegem duplicidade de responsável e desligamentos concorrentes.

Ainda fora deste recorte: edição, detalhe e histórico HTTP de funcionários; edição/desativação de responsáveis; provisionamento e troca de senha da conta compartilhada. As linhas antigas continuam preservadas no banco.

Verificação: `tests/test_contas_funcionarios_api.py` usa HTTP real, JWT e PostgreSQL migrado; cobre perfis, A/B, filtros, fotos, bootstrap, auditoria e rollback controlado.
