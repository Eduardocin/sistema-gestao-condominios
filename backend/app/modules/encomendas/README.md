# Encomendas

O módulo implementa o recebimento pela portaria, a entrega física ao morador e a confirmação posterior de quem recebeu. O modelo `Encomenda` e suas restrições são definidos em [models.py](models.py) e na migração oficial `20261103_0004_portaria_convivencia.py`.

## API

As rotas usam a base `/api/v1` e o contexto autenticado para determinar o condomínio e o usuário:

| Método e rota | Uso |
| --- | --- |
| `GET /encomendas` | Lista paginada e filtrável por descrição, status, `unidade_id` e período (`data_de`, `data_ate`), dentro do escopo autorizado. Para o Morador `unidade_id` é obrigatório (422 sem ele) |
| `GET /encomendas/relatorio` | Relatório da Administração (US-404): contagem por status, no total e por unidade, com os mesmos filtros de período e unidade |
| `GET /encomendas/{id}` | Consulta histórico e estado atual |
| `POST /encomendas` | Recebe `multipart/form-data` com unidade, destinatário, descrição, funcionário e foto |
| `POST /encomendas/{id}/entrega` | Registra funcionário e morador que recebeu fisicamente |
| `POST /encomendas/{id}/confirmacao` | Morador identificado como recebedor confirma com corpo `{}` |
| `GET /portaria/unidades` | Opções de unidade para funcionário |
| `GET /portaria/unidades/{id}/moradores` | Moradores ativos vinculados à unidade; `somente_confirmaveis=true` filtra vínculos com a aba Encomendas ativa |

Os contratos e exemplos completos estão em [portaria.md](../../../../docs/api-contracts/portaria.md). Nenhum endpoint aceita `condominio_id`: consultas e gravações sempre usam o condomínio do JWT. O morador consulta apenas suas unidades autorizadas; para evitar entregar a uma conta sem acesso ao fluxo, a confirmação exige vínculo ativo, aba Encomendas ativa e a mesma conta vinculada ao recebedor. Recursos fora do escopo retornam 404 e transições repetidas retornam 409.

## Estados e efeitos da operação

```text
aguardando_retirada
  → entregue_aguardando_confirmacao
  → retirada_confirmada
```

A primeira transição é feita pela portaria depois da entrega física; a segunda é exclusiva do morador que recebeu. Cada transição bem-sucedida registra auditoria. O recebimento grava metadados da foto, encomenda, auditoria e evento de e-mail na mesma transação SQL. Os bytes da imagem são validados e armazenados no MinIO privado; falha SQL aciona compensação para remover apenas o objeto criado pela chamada.

O evento `encomenda_registrada` entra em `envios_email` com status pendente. O worker de envio pertence à US-803 e ainda não está implementado; a API não afirma que a mensagem foi enviada.

## Testes e interfaces

Os testes da API, permissões, isolamento, transições e compensação estão em `backend/tests/test_encomendas_api.py`, `backend/tests/test_banco_constraints.py` e `backend/tests/autorizacao/`. Os testes marcados `postgres` precisam de uma base PostgreSQL dedicada; os testes de storage também precisam de MinIO de teste. Veja [storage.md](../../../../docs/storage.md) para o ambiente e as políticas de arquivos.

A demonstração local em `/prototipos/portaria` continua isolada e usa dados em memória. As interfaces autenticadas de produção ficam em `/app/portaria/encomendas` e `/app/morador/encomendas`.
