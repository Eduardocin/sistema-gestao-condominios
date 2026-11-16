# reservas

Modelos SQLAlchemy em [models.py](models.py): `AreaComum, BloqueioArea e Reserva`. Eles representam áreas comuns, bloqueios e reservas com restrições por unidade, dia e horário e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

Contrato: seções 2 e 4 de [convivencia.md](../../../../docs/api-contracts/convivencia.md). Rotas em [router.py](router.py), regras em [service.py](service.py), consultas em [repository.py](repository.py).

## Áreas comuns (TASK-84, fase 1)

| Rota | Permissão |
| --- | --- |
| `GET /areas-comuns`, `GET /areas-comuns/{id}` | `areas_comuns:ver` (Morador só vê ativas; Administração vê todas e filtra por `ativa`) |
| `POST /areas-comuns` | `areas_comuns:criar` |
| `PUT /areas-comuns/{id}` | `areas_comuns:editar` |
| `POST /areas-comuns/{id}/desativacao` | `areas_comuns:desativar` |
| `POST /areas-comuns/{id}/reativacao` | `areas_comuns:editar` |

- O nome único (sem diferenciar maiúsculas) é garantido pelo índice `uq_areas_comuns_condominio_nome`. O service grava dentro de `session.begin_nested()` e traduz o `IntegrityError` em 409 `nome_duplicado`; não há `SELECT` prévio.
- `foto_arquivo_id` é conferido em `arquivos` do mesmo condomínio (422 `foto_invalida`); a FK composta `fk_areas_comuns_foto` é a última defesa.
- `PUT` que muda `abre_as` ou `fecha_as` responde 409 `reservas_fora_do_horario` se houver reserva `ativa`, de hoje em diante, fora da nova janela. Desativar uma área não mexe nas reservas.
- Repetir desativação ou reativação responde 409 (`area_ja_desativada`, `area_ja_ativa`).

## Reservas (TASK-84, fase 2)

| Rota | Permissão |
| --- | --- |
| `GET /areas-comuns/{id}/agenda?unidade_id&data` | `reservas:ver`, só Morador (Administração recebe 403) |
| `GET /areas-comuns/{id}/calendario?unidade_id&mes` | `reservas:ver`, só Morador |
| `POST /reservas` | `reservas:criar` (Morador) |
| `GET /reservas`, `GET /reservas/{id}` | `reservas:ver` (Morador: da unidade; Administração: do condomínio) |
| `POST /reservas/{id}/cancelamento` | `reservas:desativar` (Morador: `{}`; Administração: `motivo` e `responsavel_id`) |

- **Unidade e aba.** O `unidade_id` vem da query, do corpo ou da própria reserva, então o passo 4 é feito no service com `garantir_aba_da_unidade(..., "reservas")` (`app/modules/auth/autorizacao.py`): unidade alheia 404, aba Sem Acesso 403.
- **Concorrência.** As regras "uma reserva por unidade, área e dia" e "um slot, uma reserva" são dos índices parciais `uq_reservas_unidade_area_dia_ativa` e `uq_reservas_area_horario_ativa`. O service tenta o `INSERT` num savepoint e traduz o `IntegrityError` pelo nome do índice (`reserva_duplicada_unidade`, `horario_ocupado`). Não renomear esses índices.
- **Relógio.** "Passado" é início do slot <= agora, em America/Sao_Paulo (`app/core/tempo.py`). A dependência `get_relogio` deixa os testes congelarem o tempo.
- **Bloqueios.** Só leitura (`bloqueios_area` com `removido_em IS NULL`). O cadastro de bloqueios é outra task (US-602, Sprint 3).
- **Auditoria.** `reserva.criar` e `reserva.cancelar`, na mesma transação. Provisório: usa o `RepositorioAuditoria` de `permissoes_aba` até existir `registrar_acao` (TASK-82).
- **Pendente (TASK-48).** O cancelamento pela Administração ainda não cria o aviso para a unidade nem enfileira o e-mail `reserva_cancelada`. O ponto exato está marcado com `TODO(TASK-48)` em `ReservasService.cancelar`, antes do commit.

Testes: `backend/tests/reservas/`. `test_reservas_concorrencia.py` usa conexões reais com commit (sem a fixture de rollback) e apaga o que criou.

Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md) e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.
