# Avisos — TASK-48 / US-801 e US-802

Modelos SQLAlchemy em [models.py](models.py): `Aviso, Comunicado e ComunicadoDestinatario`. Eles representam avisos do condomínio e comunicados da plataforma com seus destinatários e estão registrados em `app/db/models.py`. O esquema é criado pelas migrações oficiais em `backend/alembic/versions/`.

Avisos usam os modelos e as constraints existentes, sem migration adicional. Comunicados da
plataforma não fazem parte desta entrega e continuam sem operações HTTP neste módulo.

## API

Prefixo `/api/v1/avisos`; contrato completo na seção 1 de
[plataforma.md](../../../../docs/api-contracts/plataforma.md).

| Método e rota | Permissão |
| --- | --- |
| `GET /avisos`, `GET /avisos/{id}` | `avisos:ver` |
| `GET /avisos/vigentes` | `avisos:ver`; alias da consulta de vigentes |
| `POST /avisos` | `avisos:criar` (Administração) |
| `PUT /avisos/{id}` | `avisos:editar` (Administração) |
| `POST /avisos/{id}/encerramento` | `avisos:desativar` (Administração) |

Listas: `items`, `page`, `page_size`, `total`; padrão 20, máximo 100 itens por página.
Administração filtra `situacao=vigentes|agendados|encerrados|todos` (padrão `vigentes`);
`encerrados` inclui expirados e encerrados antecipadamente. Para Morador e Funcionário,
o filtro sempre é de vigentes, inclusive na consulta por ID. Não existe DELETE.

- Vigência: `inicio_em <= agora < fim_em`, sem `encerrado_em`; importantes primeiro,
  depois `inicio_em DESC, id DESC`. A expiração é filtrada na consulta, sem job.
- `titulo` e `texto` têm espaços externos removidos e limites de 1–120 e 1–2000 caracteres.
  Datas exigem fuso e `fim_em > inicio_em`. Escrita rejeita campos desconhecidos.
- O condomínio vem do contexto autenticado. Morador vê avisos gerais e das suas unidades
  com vínculo ativo em `moradores_unidade`; Funcionário vê somente gerais. Não existe aba
  de avisos nem dependência da permissão de reservas para ler o aviso.
- `unidade` é nula nos gerais ou `{id, identificacao}` nos automáticos. `publicado_por`
  aparece somente para Administração, preservando o autor original após uma edição.
- Toda escrita exige responsável ativo do condomínio. O responsável da edição/encerramento
  fica na auditoria central (`aviso.publicar`, `aviso.editar`, `aviso.encerrar`).
  A ação e o evento usam a mesma sessão e o mesmo commit.
- Edição e encerramento travam o registro e rejeitam encerrados/expirados com 409
  `aviso_encerrado`. Automáticos rejeitam edição com 409 `aviso_automatico`, mas aceitam
  encerramento antecipado. O histórico e o período original são preservados.

## Interface interna e reservas

[publicar_para_unidade](service.py) recebe sessão, contexto validado, unidade, título,
texto e responsável. Valida o mesmo conteúdo da API, responsável e unidade do condomínio,
publica e audita **sem commit**. Por padrão, o aviso é importante e vale por sete dias.
`dias_de_exibicao` exige inteiro positivo; `ip` e `relogio` são parâmetros internos opcionais.

O cancelamento de reserva pela Administração chama essa interface com motivo, data e hora.
Reserva, aviso e os dois eventos de auditoria são confirmados juntos; falha em qualquer
etapa reverte todos. Cancelamento pelo Morador não publica aviso. Enfileiramento de e-mail
e cadastro de bloqueios continuam fora desta entrega.

Testes PostgreSQL em [tests/avisos](../../../tests/avisos/) cobrem contrato, permissões,
isolamento, vigência, ordenação, responsáveis, auditoria e atomicidade com falhas simuladas.
As regressões existentes de [reservas](../../../tests/reservas/) também são obrigatórias.
