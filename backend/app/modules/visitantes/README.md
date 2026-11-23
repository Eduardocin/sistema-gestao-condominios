# visitantes

Modelos SQLAlchemy em [models.py](models.py): `Visitante, RegistroVisita e Veiculo`. Eles representam cadastros vinculados à unidade, histórico de entrada/saída e veículos e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

## API de visitantes (TASK-38, US-501)

Contrato: seção 6.2 de [convivencia.md](../../../../docs/api-contracts/convivencia.md). Rotas em [router.py](router.py), regras em [service.py](service.py), consultas em [repository.py](repository.py).

| Método e rota | Permissão |
| --- | --- |
| `GET /visitantes`, `GET /visitantes/{id}` | `visitantes:ver` (só Morador) |
| `POST /visitantes` | `visitantes:criar` (só Morador) |
| `PUT /visitantes/{id}` | `visitantes:editar` (só Morador) |
| `POST /visitantes/{id}/cancelamento` | `visitantes:desativar` (só Morador) |

- **Perfil.** A matriz dá `visitantes` também a Funcionário e Administração, mas estas rotas são do Morador (`so_morador` no router, antes de validar o corpo); a consulta da portaria é o contrato de `portaria.md`.
- **Unidade e aba.** `garantir_aba_da_unidade(..., "visitantes")` no service: unidade alheia 404, aba Sem Acesso 403.
- **CPF.** Opcional, 11 dígitos, com dígitos verificadores (`validar_documento`; CNPJ não vale).
- **Edição e cancelamento.** `PUT` só sem visita registrada (409 `visitante_ja_utilizado`); cancelamento só sem visita em andamento (409 `visita_em_andamento`). As duas ações travam a linha com `FOR UPDATE`, o que bloqueia a portaria de registrar uma entrada no mesmo instante.
- **Situação.** Calculada pelo dia no fuso do condomínio; as datas são inclusivas.

Veículos (US-502) ainda não têm rotas.

Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md), o [contrato da API](../../../../docs/api-contracts/portaria.md) e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.
