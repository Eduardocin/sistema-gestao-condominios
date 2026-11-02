# Integração da auditoria nos fluxos do MVP

## Story / task

TASK-24 — acompanhamento de integração; ID definitivo a registrar no Kanban da equipe.

## Objetivo

Garantir que as ações críticas dos fluxos do MVP gerem exatamente um evento imutável de auditoria,
incluindo a identificação declarada do responsável quando a ação vier de uma conta compartilhada
de Funcionário ou Administração.

## O que fazer

- [ ] Integrar `APROVACAO` e `REJEICAO` ao caso de uso de aprovação de condomínio, após a decisão ser
      efetivada. Coordenar com Paulo César.
- [ ] Integrar `MUDANCA_PERMISSAO` ao caso de uso de concessão, alteração ou remoção de permissões.
      Coordenar com Tude e a frente responsável pela autorização.
- [ ] Integrar `RESERVA` às ações críticas de reserva, incluindo criação e cancelamento, sem duplicar
      eventos em retries ou falhas. Coordenar com Vitor Negromante.
- [ ] Integrar `OCORRENCIA` à abertura, resposta e mudança de estado de ocorrências. Coordenar com
      Vitor Negromante.
- [ ] Em cada chamada, fornecer ator, perfil, condomínio, recurso, identificador do recurso, IP e
      dados antes/depois aplicáveis, usando a mesma sessão e transação do caso de uso.
- [ ] Para perfis `funcionario` e `administracao`, exigir e registrar `nome_responsavel` em cada
      ação crítica. O nome é autodeclarado no MVP; não representa autenticação individual.
- [ ] Adicionar teste de integração PostgreSQL por fluxo, verificando exatamente um evento para
      cada ação concluída, os campos do evento e ausência de evento quando a operação falhar antes
      de ser efetivada.
- [ ] Confirmar que não foram adicionados endpoints nem métodos de atualização ou exclusão dos
      eventos de auditoria.

## Pronto quando

- [ ] Cada caso de uso listado acima existe e chama `audit.log(...)` uma única vez após concluir
      sua operação.
- [ ] As integrações preservam isolamento por condomínio e usam a transação do caso de uso.
- [ ] A falta de `nome_responsavel` impede a auditoria de ação de conta compartilhada e não deixa
      a operação crítica ser concluída sem registro.
- [ ] Os testes PostgreSQL comprovam o evento correto e a cardinalidade igual a um para cada ação
      crítica integrada.
- [ ] A suíte backend, Ruff, formatação, mypy e validação Alembic passam no CI.

## Dependências e limite de escopo

Esta tarefa depende da implementação dos casos de uso de aprovação de condomínio, permissões,
reservas e ocorrências pelas frentes responsáveis. Não criar endpoints ou fluxos de negócio
substitutos dentro do módulo de auditoria. As implementações devem integrar a interface existente
em [`service.py`](../../backend/app/modules/auditoria/service.py).
