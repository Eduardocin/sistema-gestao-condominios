# visitantes

Modelos SQLAlchemy em [models.py](models.py): `Visitante, RegistroVisita e Veiculo`. Eles representam cadastros vinculados à unidade, histórico de entrada/saída e veículos e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

O módulo disponibiliza cadastro, consulta, edição e cancelamento de visitantes pelo Morador (`/visitantes`), além da busca, autorização, entrada, saída e contatos da Portaria (`/portaria/visitantes`, `/portaria/autorizacoes`, `/visitas` e `/portaria/contatos`). O cadastro é a fonte da autorização reutilizável. A migração `20261121_0008` guarda a evidência da entrada e os contatos sem visita. O cadastro avulso e as operações de veículos ficam em entregas próprias.

Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md), o [contrato da API](../../../../docs/api-contracts/portaria.md) e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.
