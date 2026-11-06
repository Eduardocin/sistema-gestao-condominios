# avisos

Modelos SQLAlchemy em [models.py](models.py): `Aviso, Comunicado e ComunicadoDestinatario`. Eles representam avisos do condomínio e comunicados da plataforma com seus destinatários e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

Rotas, schemas HTTP, services e repositories deste módulo ainda serão implementados. A existência dos modelos não disponibiliza operações HTTP.

Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md), os contratos de [avisos](../../../../docs/api-contracts/convivencia.md) e [comunicados](../../../../docs/api-contracts/plataforma.md), e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.
