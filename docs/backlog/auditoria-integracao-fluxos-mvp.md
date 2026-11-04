# Integração da auditoria nos fluxos do MVP

## Story / task

TASK-24 — acompanhamento de integração; manter o ID definitivo alinhado ao Kanban da equipe.

## Status

A infraestrutura de auditoria e os fluxos de autenticação, contas, aprovação de condomínio e
vínculo Morador–Unidade já estão integrados no backend. Reservas e ocorrências permanecem pendentes
porque seus casos de uso ainda não estão implementados. Não criar fluxos de negócio substitutos
apenas para gerar eventos de auditoria.

## Integrações concluídas

- [x] Criar a tabela, modelo, serviço `audit.log(...)` e repositório apenas de inserção e leitura.
- [x] Impedir `UPDATE`, `DELETE` e `TRUNCATE` dos eventos no PostgreSQL.
- [x] Exigir o nome declarado de quem executou ações por contas compartilhadas de Administração e
      Funcionário, com validação na aplicação e no banco.
- [x] Registrar login e falhas de login.
- [x] Registrar criação e edição de contas e criação de condomínio pelo wizard.
- [x] Registrar aprovação e rejeição de condomínio, além dos eventos de notificação correspondentes.
- [x] Registrar solicitação e decisão de vínculo Morador–Unidade, incluindo as mudanças de permissão
      e notificações da decisão.
- [x] Cobrir essas integrações com testes existentes; há testes de cardinalidade para ações como
      rejeição de condomínio, login, operações de conta e eventos de vínculo.

## Pendências para concluir a integração dos fluxos do MVP

- [ ] Quando o módulo de reservas tiver casos de uso, integrar `RESERVA` às operações críticas
      implementadas, como criação e cancelamento. Registrar uma vez por operação efetivada, sem
      gerar evento em falha ou duplicar em retry. Coordenar com a frente responsável por reservas.
- [ ] Quando o módulo de ocorrências tiver casos de uso, integrar `OCORRENCIA` à abertura, resposta
      e mudanças de estado que alterem dados. Registrar uma vez por operação efetivada e não gerar
      evento em falha ou retry. Coordenar com a frente responsável por ocorrências.
- [ ] Integrar `MUDANCA_PERMISSAO` a outros casos de concessão, alteração ou remoção de permissões
      quando forem implementados, além dos fluxos de vínculo já cobertos.
- [ ] Para cada ação crítica nova, fornecer ator, perfil, condomínio, recurso, identificador do
      recurso, IP e dados antes/depois aplicáveis, usando a mesma sessão e transação do caso de uso.
- [ ] Para cada integração nova, adicionar testes PostgreSQL que comprovem exatamente um evento por
      operação concluída e nenhum evento se a operação falhar ou for revertida.
- [ ] Confirmar que não foram adicionados endpoints nem métodos de atualização ou exclusão dos
      eventos de auditoria.

## Critérios para encerrar as integrações pendentes

- [ ] Os casos de uso de reserva e ocorrência existem e chamam `audit.log(...)` uma única vez por
      mutação efetivada.
- [ ] Os eventos contêm os campos relevantes e respeitam o isolamento por condomínio.
- [ ] A auditoria usa a transação do caso de uso; erro ao registrar o evento também impede que a
      operação crítica seja persistida sem auditoria.
- [ ] A ausência de `nome_responsavel` impede a conclusão de uma ação feita por conta compartilhada.
- [ ] Testes PostgreSQL verificam cardinalidade, conteúdo do evento e rollback em caso de falha.
- [ ] Suíte backend, Ruff, formatação, mypy e validação Alembic passam no CI.

## Dependências e limite de escopo

As integrações de reservas e ocorrências dependem dos respectivos casos de uso serem implementados
pelas frentes responsáveis. Esta pendência não bloqueia a infraestrutura nem os fluxos já integrados
da TASK-24. Não criar endpoints ou fluxos de negócio substitutos dentro do módulo de auditoria. As
implementações devem usar a interface existente em
[`service.py`](../../backend/app/modules/auditoria/service.py).
