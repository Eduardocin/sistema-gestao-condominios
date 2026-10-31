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

O modelo completo do MVP, com diagramas e constraints, está em [`modelo-de-dados.md`](modelo-de-dados.md). Esta seção descreve só o que as migrações `20261015_0001` e `20261028_0002` já criaram.

- `usuarios`: identidade global, UUID gerado pela aplicação, e-mail único em minúsculas, nome, situação e indicação de administrador da plataforma. Desde a `20261028_0002` há também `senha_hash` e `sessao_versao` (o `sv` do token), usados pelo login (TASK-80).
- `condominios`: UUID, nome, situação e data de criação.
- `unidades`: condomínio obrigatório e identificação única dentro dele, por exemplo `Bloco A / 101`.
- `vinculos_condominio`: usuário, condomínio, perfil local (`administracao`, `funcionario`, `morador`), situação e unidade opcional. Um usuário pode participar de vários condomínios. Nesta base há um perfil e, no máximo, uma unidade por vínculo; múltiplas unidades ou múltiplos perfis por condomínio exigirão modelagem própria em uma sprint futura.

FKs usam `RESTRICT`, evitando exclusões em cascata de dados administrativos. Datas usam timezone. Índices cobrem o escopo do condomínio. A FK composta `(unidade_id, condominio_id)` garante que uma unidade indicada no vínculo pertença ao mesmo condomínio. O relacionamento é expresso por chaves estrangeiras; propriedades ORM de navegação só devem ser introduzidas quando necessárias, com carregamento explícito.

## Isolamento e autorização

O isolamento é lógico por `condominio_id`. Não há Row Level Security nem filtro automático global: o filtro é aplicado de forma explícita pelo repositório base (`app/db/repositorio.py`), descrito abaixo. As constraints garantem integridade referencial, mas não impedem sozinhas uma consulta sem filtro de ler outros condomínios.

Todo endpoint de negócio precisa autenticar o usuário, validar vínculo ativo no condomínio do token, verificar papel e filtrar todas as consultas pelo condomínio autorizado. Um ID recebido pela URL ou corpo não prova autorização. Operações com objetos de outro condomínio são negadas sem revelar seus dados. O acesso global da plataforma exige verificação explícita, distinta dos perfis locais. Não confiar em cabeçalhos de usuário ou condomínio como autenticação.

Estão implementados o login (TASK-80) e a porta de entrada dos endpoints de condomínio, `get_current_context` (TASK-18), que cobre identidade e condomínio (passos 1 e 2 da [matriz](permissoes-e-multitenant.md#5-ordem-de-checagem)). Perfil, unidade e aba (passos 3 e 4) ainda são das TASK-19 e TASK-21. Não há autenticação fictícia. Funcionalidades novas precisam de testes negativos de acesso entre condomínios e de privilégios.

## Como criar um endpoint novo respeitando o isolamento

Três peças fazem o isolamento acontecer; o desenvolvedor do módulo não escreve o filtro:

| Peça | Onde | O que faz |
| --- | --- | --- |
| `ContextoDep` | `app/modules/auth/dependencies.py` | Valida o token (401) e confere vínculo ativo e condomínio ativo **no banco** (403). Entrega um `ContextoCondominio` imutável: `usuario_id`, `condominio_id`, `perfil`, `vinculo_id`. O `perfil` vem do vínculo, nunca do claim do token |
| `RepositorioDoCondominio` | `app/db/repositorio.py` | Aplica `condominio_id` em todo SELECT, UPDATE e DELETE, e preenche em todo INSERT. Recusa `condominio_id` vindo em `dados` e falha na definição da classe se o model não tem a coluna |
| `RecursoNaoEncontrado` | `app/core/errors.py` | Vira 404 `not_found` com mensagem genérica. É a mesma resposta para "não existe" e "é de outro condomínio" (R4) |

Passo a passo:

1. **Model** com `condominio_id` obrigatório, FK e índice (R2). Registre-o em `app/db/models.py` e crie a migration.
2. **Repository** que herda `RepositorioDoCondominio[SeuModel]` e declara `modelo = SeuModel`. Para consultas próprias, parta de `self.consulta()`, que já vem filtrada. Nunca use `session.get(...)` nem `select(SeuModel)` fora do repository.
3. **Service** que recebe a sessão e o contexto, chama o repository e faz o `commit`. Prefira desativar a apagar: nenhum perfil apaga registro (matriz, seção 7). O `remover` da base existe, mas é DELETE físico.
4. **Router** que depende de `ContextoDep`, com schemas de escrita `extra="forbid"`. A rota não tem `condominio_id` na URL, no corpo, na query nem em cabeçalho.
5. **Testes** com dois condomínios: o usuário do A tenta ler, listar, editar e apagar o que é do B e recebe 404 ou lista vazia. Copie o padrão de `backend/tests/isolamento/`.

O exemplo abaixo é o mesmo código que os testes exercitam (`backend/tests/isolamento/app_exemplo.py`; o teste `test_guia_sincronizado.py` falha se os dois divergirem). Imports e o model foram omitidos:

<!-- inicio-exemplo -->
```python
class ItemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")  # condominio_id no corpo vira 422 (R1)
    nome: str = Field(min_length=1, max_length=80)


class ItemSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    nome: str


class ItemRepositorio(RepositorioDoCondominio[Item]):
    modelo = Item  # o filtro por condomínio vem da classe base


class ItemService:
    def __init__(self, session: Session, contexto: ContextoCondominio) -> None:
        self.session = session
        self.itens = ItemRepositorio(session, contexto)

    def listar(self) -> list[Item]:
        return self.itens.listar()

    def obter(self, item_id: uuid.UUID) -> Item:
        return self.itens.obter(item_id)  # 404 se não existir ou for de outro condomínio

    def criar(self, dados: ItemEntrada) -> Item:
        item = self.itens.criar(dados.model_dump())
        self.session.commit()  # quem faz commit é o service, nunca o repository
        return item

    def renomear(self, item_id: uuid.UUID, dados: ItemEntrada) -> Item:
        item = self.itens.atualizar(item_id, dados.model_dump())
        self.session.commit()
        return item

    def remover(self, item_id: uuid.UUID) -> None:
        self.itens.remover(item_id)  # em módulo real, prefira desativar (matriz, seção 7)
        self.session.commit()


def get_item_service(
    session: Annotated[Session, Depends(get_session)], contexto: ContextoDep
) -> ItemService:
    return ItemService(session, contexto)  # o contexto vem do token + banco, nunca do cliente


ServiceDep = Annotated[ItemService, Depends(get_item_service)]
router = APIRouter(prefix="/itens")


@router.get("", response_model=list[ItemSaida])
def listar(service: ServiceDep) -> list[Item]:
    return service.listar()


@router.get("/{item_id}", response_model=ItemSaida)
def obter(item_id: uuid.UUID, service: ServiceDep) -> Item:
    return service.obter(item_id)


@router.post("", response_model=ItemSaida, status_code=201)
def criar(dados: ItemEntrada, service: ServiceDep) -> Item:
    return service.criar(dados)


@router.patch("/{item_id}", response_model=ItemSaida)
def renomear(item_id: uuid.UUID, dados: ItemEntrada, service: ServiceDep) -> Item:
    return service.renomear(item_id, dados)


@router.delete("/{item_id}", status_code=204)
def remover(item_id: uuid.UUID, service: ServiceDep) -> None:
    service.remover(item_id)
```
<!-- fim-exemplo -->

Regras de bolso:

- **Ordem das respostas:** sem token ou sessão inválida, 401; sem `cid`, sem vínculo ativo, ADM da plataforma ou condomínio não ativo, 403; recurso inexistente ou de outro condomínio, 404.
- **O que a base não faz:** não decide permissão por perfil, unidade ou aba (TASK-19 e TASK-21) e não faz commit. Um service que consulte o banco por conta própria passa por cima do filtro; `test_arquitetura_camadas.py` falha se um `service.py` ou `router.py` usar `select(...)` ou `session.get/execute/scalar/scalars/query`.
- **Campos protegidos:** `criar` e `atualizar` levantam `CampoProtegido` se `dados` trouxer `condominio_id` (e `id`, no `atualizar`). Isso é erro de programação, não de entrada do cliente: valide o corpo com schemas explícitos antes de chegar ao repository.
- **Rotas que não usam este contexto:** login, escolha de condomínio, `/auth/me` e `/plataforma/...` não têm `cid` e continuam com `get_usuario_autenticado`. O teste `test_nenhum_endpoint_recebe_condominio_id.py` aceita `condominio_id` do cliente apenas em `POST /auth/selecionar-condominio` e sob `/plataforma/`.
- **Pendência (variante de cadastro, R7):** até existir a dependência do fluxo de cadastro do condomínio, a Administração de um condomínio **não ativo** recebe 403 em toda rota que use `ContextoDep`. É proposital; o login continua devolvendo token para ela.

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
5. Registrar router no agregador `/api/v1`, com dependências de autorização reais (`ContextoDep`; veja [como criar um endpoint respeitando o isolamento](#como-criar-um-endpoint-novo-respeitando-o-isolamento)).
6. Adicionar testes do fluxo, falhas, permissões e isolamento. No frontend, criar a feature e usar o cliente HTTP centralizado.

Decisões complementares estão em `docs/decisions/`.
