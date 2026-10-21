# Arquitetura

## Objetivo

Fundação técnica do projeto acadêmico IESI, sem antecipar os fluxos de negócio. Monorepo com frontend React e um único backend FastAPI. PostgreSQL é o único serviço executado em Docker nesta etapa.

Fluxo: navegador → React Router / Axios → HTTP REST `/api/v1` → FastAPI → services → repositories → SQLAlchemy síncrono → PostgreSQL.

## Monólito modular

Uma aplicação e um banco reduzem o custo de execução, depuração e colaboração. Os módulos representam domínios: autenticação, usuários, condomínios, unidades, encomendas, visitantes, reservas, ocorrências, avisos e auditoria. Não há chamadas de rede entre módulos, Redis, mensageria ou microserviços.

Cada funcionalidade cria apenas as camadas de que precisa:

| Camada | Responsabilidade |
| --- | --- |
| Router | HTTP, dependências de autorização, status e schemas |
| Schema | Entrada e saída explícitas com Pydantic; nunca serializar models indiscriminadamente |
| Service | Casos de uso, autorização de negócio e limite da transação |
| Repository | Consultas e persistência, sempre com escopo do condomínio quando aplicável |
| Models | Mapeamento de tabelas, chaves e restrições de integridade |

Routers não consultam SQL. Repositories não decidem permissões nem fazem commits independentes. Services coordenam commit; a dependência fecha sessões e reverte exceções. Não existe commit implícito ao concluir uma requisição. Um fluxo composto usa a mesma sessão. O pool utiliza pre-ping, cinco conexões e até dez conexões adicionais por processo; os limites são iniciais para desenvolvimento.

## Modelo estrutural

O modelo completo do MVP, com diagramas e constraints, está em [`modelo-de-dados.md`](modelo-de-dados.md). Esta seção descreve só o que a migração `20261015_0001` já criou.

- `usuarios`: identidade global, UUID gerado pela aplicação, e-mail único em minúsculas, nome, situação e indicação de administrador da plataforma. Ainda não há credenciais nem login.
- `condominios`: UUID, nome, situação e data de criação.
- `unidades`: condomínio obrigatório e identificação única dentro dele, por exemplo `Bloco A / 101`.
- `vinculos_condominio`: usuário, condomínio, perfil local (`administracao`, `funcionario`, `morador`), situação e unidade opcional. Um usuário pode participar de vários condomínios. Nesta base há um perfil e, no máximo, uma unidade por vínculo; múltiplas unidades ou múltiplos perfis por condomínio exigirão modelagem própria em uma sprint futura.

FKs usam `RESTRICT`, evitando exclusões em cascata de dados administrativos. Datas usam timezone. Índices cobrem o escopo do condomínio. A FK composta `(unidade_id, condominio_id)` garante que uma unidade indicada no vínculo pertença ao mesmo condomínio. O relacionamento é expresso por chaves estrangeiras; propriedades ORM de navegação só devem ser introduzidas quando necessárias, com carregamento explícito.

## Isolamento e autorização

O isolamento será lógico por `condominio_id`. Não há Row Level Security nem filtro automático global nesta etapa. As constraints garantem integridade referencial, mas não impedem sozinhas uma consulta sem filtro de ler outros condomínios.

Antes de qualquer endpoint de negócio ser publicado, será necessário autenticar o usuário, validar vínculo ativo no condomínio solicitado, verificar papel e filtrar todas as consultas pelo condomínio autorizado. Um ID recebido pela URL ou corpo não prova autorização. Operações com objetos de outro condomínio devem ser negadas sem revelar seus dados. O acesso global da plataforma exige verificação explícita, distinta dos perfis locais. Não confiar em cabeçalhos de usuário ou condomínio como autenticação.

Somente health e documentação técnica estão disponíveis, sem operações de negócio. Não há autenticação fictícia. Futuras funcionalidades precisam de testes negativos de acesso entre condomínios e de privilégios.

## Configuração e falhas

Pydantic Settings lê `.env` na raiz por caminho absoluto; variáveis do processo têm precedência. A URL SQLAlchemy é montada com `URL.create`, preservando senhas com caracteres especiais. `DATABASE_URL`, quando informada, substitui os campos separados. Logs básicos usam nível configurável; SQL echo permanece desligado.

Erros HTTP, validação e exceções inesperadas usam o envelope documentado em `api-contracts/health.md`. Respostas inesperadas não devolvem detalhes internos. CORS permite por padrão somente as origens locais indicadas no exemplo. CORS não substitui autorização. O health é liveness da API, não readiness do banco.

## Persistência e evolução

Alembic é o único mecanismo de evolução do schema. `app/db/models.py` registra todos os models no metadata; cada novo model deve ser importado nele. Revisar o resultado de autogenerate antes de aplicar, especialmente renomes, remoções, CHECKs e migrações de dados. Nunca editar uma migração já compartilhada e aplicada; criar uma nova. Não usar `create_all()` no ciclo da aplicação.

O CI cria um banco limpo, aplica e reverte a migração, aplica novamente e compara metadata com `alembic check`. Testes PostgreSQL verificam vínculos múltiplos e restrições de condomínio. SQLite é usado somente no teste unitário do ciclo de rollback da sessão, nunca como validação da migração PostgreSQL.

## Adição de funcionalidades

1. Definir contrato HTTP e critérios de autorização em `docs/api-contracts/`.
2. Criar o caso de uso no módulo correspondente com schemas, service e repository conforme necessário.
3. Se precisar de outro módulo, consumir sua interface pública de serviço; evitar importar routers ou acessar seus repositories diretamente.
4. Registrar models no agregador e gerar uma migração revisada.
5. Registrar router no agregador `/api/v1`, com dependências de autorização reais.
6. Adicionar testes do fluxo, falhas, permissões e isolamento. No frontend, criar a feature e usar o cliente HTTP centralizado.

Decisões complementares estão em `docs/decisions/`.
