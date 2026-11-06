# Portaria — decisões para integração

Fluxos, telas navegáveis e contrato REST compõem a entrega da TASK-12, já encerrada no quadro. Este documento reúne alinhamentos para implementar as APIs da portaria, que ainda não estão disponíveis.

As tabelas de encomendas, visitantes e visitas estão na migração oficial `20261103_0004`; moradores por unidade, funcionários e arquivos estão na `20261103_0003`. A autorização central também está disponível. A cobertura das restrições de encomendas usa o esquema oficial em `backend/tests/test_banco_constraints.py`.

Decisões do responsável da portaria em 22/10/2026: manter os três estados de encomenda com confirmação posterior pelo recebedor; adotar a autorização reutilizável durante o período cadastrado do visitante, como no PR #5; corrigir o CHECK de encomendas para impedir dados parciais. A representação de contatos sem entrada continua pendente de alinhamento com a equipe.

| Tema | Alinhamento necessário | Responsável pelo alinhamento |
| --- | --- | --- |
| Telas como referência | Usar a prévia navegável como referência da integração e revisar os estados com dados reais | Responsável da TASK-12 e equipe |
| Aparência e componentes | Revisar navegação, formulários, diálogos e novos componentes do catálogo | Matheus e responsável da TASK-12 |
| Modelo de dados | Usar os modelos e as migrações oficiais, preservando os três estados de encomenda e a autorização por período; alinhar o registro de contatos sem entrada | Davi e responsável da TASK-12 |
| Confirmação pelo morador | Validar a implementação da regra documentada na matriz após o PR #5: confirmação somente pelo recebedor | Responsáveis pela autorização central e TASK-12 |
| Contas compartilhadas | Confirmar `funcionario_id` por operação e auditoria da conta autenticada + funcionário selecionado | Davi e responsáveis pela autorização central |
| Visitantes existentes | Alinhar consulta por unidade, período do cadastro, cancelamento e verificação da autorização a cada entrada, sem consumo de uso único | Vitor e responsável da TASK-12 |
| Fotos / TASK-26 | Confirmar formatos, tamanho máximo, ciclo do upload, leitura protegida e limpeza de arquivos sem vínculo | Responsável da TASK-26 e backend |
| Contrato REST | Revisar nomes de campos, endpoints, permissões e envelope de resposta antes da integração | Frontend e backend envolvidos |

## Critérios para a integração

- Fluxos disponíveis e coerentes com as regras acordadas.
- Telas revisadas, incluindo estados vazios, validação, erros e confirmação das operações.
- Contrato REST revisado e alinhado ao modelo e à autorização central.
- Decisões acima resolvidas ou explicitamente aceitas pela equipe, com registro da revisão.

Nenhuma revisão externa ou aprovação de Davi, Matheus ou Vitor foi presumida nesta entrega.
