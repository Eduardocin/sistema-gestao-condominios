# visitantes

Modelos SQLAlchemy em [models.py](models.py): `Visitante, RegistroVisita e Veiculo`. Eles representam cadastros vinculados à unidade, histórico de entrada/saída e veículos e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

O módulo disponibiliza cadastro, consulta, edição e cancelamento de visitantes pelo Morador (`/visitantes`), além da busca, autorização, entrada, saída e contatos da Portaria (`/portaria/visitantes`, `/portaria/autorizacoes`, `/visitas` e `/portaria/contatos`). O cadastro é a fonte da autorização reutilizável. A migração `20261121_0008` guarda a evidência da entrada e os contatos sem visita. O cadastro avulso e as operações de veículos ficam em entregas próprias.

Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md), o [contrato da API](../../../../docs/api-contracts/portaria.md) e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.

## Relatórios administrativos — US-506 simplificada

[relatorios_router.py](relatorios_router.py) oferece `GET /api/v1/relatorios/visitantes`
e `GET /api/v1/relatorios/veiculos`, exclusivos da Administração de condomínio ativo,
com as permissões existentes `visitantes:ver` e `veiculos:ver`. Os filtros e respostas
ficam em [relatorios_schemas.py](relatorios_schemas.py), as regras em
[relatorios_service.py](relatorios_service.py) e as consultas em
[relatorios_repository.py](relatorios_repository.py).

Ambas aceitam `unidade_id`, `de`, `ate`, `page` (padrão 1) e `page_size` (padrão 20,
máximo 100). Datas inclusivas no fuso `America/Sao_Paulo` são convertidas para intervalo
com fim exclusivo no dia seguinte; datas invertidas, inválidas, `9999-12-31` e parâmetros
extras retornam 422. Unidade inexistente/alheia retorna 404; unidade inativa é admitida.
A resposta é `{items,total,page,page_size}`; ordenação por instante decrescente e ID
crescente, com filtros, total e paginação no banco. Não há seleção livre de condomínio.

Visitantes reutiliza `RepositorioVisitas.detalhada()` e filtra a entrada **efetiva**,
preservando saídas posteriores ao período, avulsos, visitas repetidas, cancelados e
funcionários desligados. Expõe referências de visitante/unidade/funcionários, bloco,
andar, `avulso`, situação e movimentações; não expõe CPF nem evidência interna. Nomes
e identificação da estrutura são atuais; o registro não tem snapshots desses nomes.

Veículos filtra `criado_em` e inclui removidos e unidades inativas, com os dados atuais,
`ativo`, datas de cadastro/remoção e `placa_duplicada`. A duplicidade é a existência atual
de cadastros ativos da placa em duas unidades ativas distintas do próprio condomínio,
independente dos filtros; linhas históricas também exibem esse indicador da placa,
sem participar da contagem de ativos. A consulta própria evita aplicar às linhas
históricas o pressuposto da consulta operacional de que o veículo já está ativo.
Não há circulação de veículos nem reconstrução de versões anteriores do cadastro.

Não há auditoria de sucesso por listagem; negações seguem o fluxo central. Não há
CSV, outros formatos de exportação ou alteração das rotas operacionais. Apenas a
US-506 simplificada está entregue; as demais partes da TASK-52 permanecem fora do escopo.
Contrato completo e cuidados com os PRs #30/#31 em
[convivencia.md, seção 6.4](../../../../docs/api-contracts/convivencia.md#64-relatórios-administrativos-us-506-simplificada-task-52).
Testes PostgreSQL em [tests/us506](../../../tests/us506).
