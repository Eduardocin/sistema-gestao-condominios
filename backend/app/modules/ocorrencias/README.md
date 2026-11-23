# ocorrencias

Modelos SQLAlchemy em [models.py](models.py): `Ocorrencia, OcorrenciaAnexo e OcorrenciaInteracao`. Eles representam ocorrências, anexos e histórico de interações e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

Contrato: seção 5 de [convivencia.md](../../../../docs/api-contracts/convivencia.md). Rotas em [router.py](router.py), regras em [service.py](service.py), consultas em [repository.py](repository.py).

## API (TASK-40, US-701 a US-703)

| Método e rota | Permissão |
| --- | --- |
| `POST /ocorrencias` | `ocorrencias:criar` (Morador) |
| `GET /ocorrencias`, `GET /ocorrencias/{id}` | `ocorrencias:ver` (Morador da unidade; Administração) |
| `POST /ocorrencias/{id}/respostas` | `ocorrencias:editar` (Administração) |
| `POST /ocorrencias/{id}/resolucao` | `ocorrencias:editar` (Administração) |
| `POST /ocorrencias/{id}/comentarios` | `ocorrencias:editar` (só Morador) |
| `POST /ocorrencias/{id}/reabertura` | `ocorrencias:editar` (só Morador) |

- **Unidade e aba.** O `unidade_id` vem da query, do corpo ou da própria ocorrência, então o passo 4 é feito no service com `garantir_aba_da_unidade(..., "ocorrencias")`: unidade alheia 404, aba Sem Acesso 403. O Funcionário recebe 403 pela matriz.
- **Lista.** O Morador precisa de `unidade_id` e vê só aquela unidade; `de`/`ate` são filtros da Administração. Ambos filtram por `status` e paginam (20 por padrão, máximo 100). A lista devolve `ultima_interacao_em` (nula sem interação) e `aguardando_administracao` (verdadeiro quando não há resposta ou a última interação é do Morador).
- **Anexos.** Até 5 arquivos já enviados ao storage no módulo `ocorrencias`, sem repetição. O service confere que o arquivo é do condomínio, foi enviado pela conta autenticada e é imagem ou MP4; qualquer outro caso é 422. As FKs compostas são a última defesa.
- **Resposta.** Exige texto e um responsável ativo da Administração do condomínio (inativo ou de outro prédio: 404). A interação guarda a conta autenticada em `usuario_id` e o responsável escolhido em `responsavel_id`; o detalhe mostra o nome do responsável.
- **Resolução.** Só de `em_aberto` (senão 409 `ocorrencia_ja_resolvida`); grava `resolvida_em`, cria a interação `resolucao` e o evento de auditoria `ocorrencia.resolver`, tudo na mesma transação. A ocorrência nunca é apagada.
- **Isolamento.** Toda consulta parte de `RepositorioDoCondominio`; ocorrência de outro condomínio responde 404, e a lista correspondente é vazia.

## Comentários e reabertura (TASK-63, US-704)

- **Perfil.** A matriz dá `editar` ao Morador e à Administração, então o router confere o perfil além da permissão: `exigir_morador` (comentar, reabrir) e `exigir_administracao` (responder, resolver).
- **Comentário.** Vale em qualquer estado e não muda o status. Até 5 anexos, com as regras da abertura; um arquivo já anexado à ocorrência é recusado (422), porque a chave de `ocorrencia_anexos` é (ocorrência, arquivo).
- **Reabertura.** Só de `resolvida` (409 `ocorrencia_nao_resolvida`), com a linha travada. Limpa `resolvida_em`, grava a interação `reabertura` e audita `ocorrencia.reabrir`. A ocorrência volta à fila da Administração (`aguardando_administracao = true`).

Testes: `backend/tests/ocorrencias/`. Consulte o [modelo de dados](../../../../docs/modelo-de-dados.md) e as [convenções de arquitetura](../../../../docs/architecture.md). Os testes das restrições do banco ficam em `backend/tests/test_banco_constraints.py`.
