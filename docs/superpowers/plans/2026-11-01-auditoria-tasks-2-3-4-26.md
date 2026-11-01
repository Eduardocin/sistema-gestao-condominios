# Auditoria das TASK-2, TASK-3, TASK-4 e TASK-26

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** documentar a cobertura das 31 stories Must e atualizar os quatro cards com evidências reais, sem presumir aprovações humanas.

**Architecture:** mudança somente documental. O plano de testes liga critérios do Notion a casos manuais/automáticos e à implementação existente; a auditoria separa entrega técnica, integração e aceite da equipe.

**Tech Stack:** Markdown, GitHub Actions, pytest/PostgreSQL/MinIO e testes Node já existentes.

**Spec:** TASK-4 no Notion (`3f866650b896811ea0c1e75ca77ed874`), as 31 stories Must consultadas em 01/11/2026 e os critérios das TASK-2, TASK-3 e TASK-26.

## Global Constraints

- Não alterar código, esquema do banco, responsáveis ou decisões de negócio.
- Preservar os seis arquivos locais anteriores que não pertencem à entrega.
- Não afirmar que um cenário planejado foi executado; não concluir aceite dependente de outro integrante.
- Python 3.13 no CI; banco/arquivos de teste separados e dados fictícios.

## Review Focus

- Story Must ausente: conferir o conjunto exato dos 31 IDs da fonte.
- Critério perdido: conservar todos os critérios como resultados esperados do caso associado.
- Automação presumida: apontar arquivos/testes existentes e explicitar a cobertura parcial.
- Regra divergente: registrar confirmação posterior de encomenda, vínculo, reserva por horário e estados ainda propostos sem criar outra decisão.
- Card encerrado indevidamente: manter revisão/andamento enquanto faltarem aceite humano ou integração.

## Task 1: Plano de testes e auditoria documental

**Files:** criar `docs/plano-de-testes/README.md`, `docs/plano-de-testes/casos-must.md`, `docs/auditorias/2026-11-01-sprints-0-1.md`; modificar `README.md` com um link de descoberta.

- [x] Registrar caso, preparação, passos, resultados esperados, tipo, referência de responsável e situação para cada story Must.
- [x] Documentar execução de testes, ambiente separado, registro de resultados e roteiro manual da portaria.
- [x] Conferir cobertura de IDs/critérios, referências de arquivos e diff sem arquivos locais anteriores.
- [ ] Revisar a documentação e publicar PR; conferir o CI correspondente.

## Task 2: Atualizar Notion com evidências

- [ ] Marcar os itens tecnicamente entregues nos cards, preservando seus critérios de aceite.
- [ ] Registrar links, dependências, divergências e pendências de validação; manter responsáveis.
- [ ] TASK-2/TASK-3: Em revisão; TASK-26: Em andamento; TASK-4: Em revisão após a entrega documental.
- [ ] Ligar o plano na página Documentos e Links e confirmar o resultado das alterações.

## Decisões de execução

- Reutilizar o checkout em branch dedicada; os arquivos anteriores permanecem fora do commit.
- Não criar testes permanentes para uma mudança apenas documental; validar cobertura e links com uma conferência temporária.
- A ausência de aprovações registradas no PR #5, na lista de revisão do DER e na página Documentos e Links não autoriza presumir aceite dos módulos.
