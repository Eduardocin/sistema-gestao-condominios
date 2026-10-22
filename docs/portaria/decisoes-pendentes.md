# Portaria — revisão pendente da TASK-12

Fluxos e primeira versão navegável foram preparados. O contrato REST é uma proposta, não uma API implementada ou aprovada. A TASK-12 não deve ser marcada como concluída antes da revisão da equipe.

Decisões do responsável da portaria em 22/10/2026: manter os três estados de encomenda com confirmação posterior pelo recebedor; adotar a autorização reutilizável durante o período cadastrado do visitante, como no PR #5; corrigir o CHECK de encomendas para impedir dados parciais. A representação de contatos sem entrada continua pendente de alinhamento com a equipe.

| Tema | Alinhamento necessário | Responsável pelo alinhamento |
| --- | --- | --- |
| Telas como entrega | Aceitar a prévia navegável e capturas como substituição dos wireframes estáticos | Responsável da TASK-12 e equipe |
| Aparência e componentes | Revisar navegação, formulários, diálogos e novos componentes do catálogo | Matheus e responsável da TASK-12 |
| Modelo de dados | Revisar os três estados de encomenda, eventos separados, vínculo de quem retira, autorização por período e registro de contatos sem entrada | Davi e responsável da TASK-12 |
| Confirmação pelo morador | Validar a implementação da regra documentada na matriz após o PR #5: confirmação somente pelo recebedor | Responsáveis pela autorização central e TASK-12 |
| Contas compartilhadas | Confirmar `funcionario_id` por operação e auditoria da conta autenticada + funcionário selecionado | Davi e responsáveis pela autorização central |
| Visitantes existentes | Alinhar consulta por unidade, período do cadastro, cancelamento e verificação da autorização a cada entrada, sem consumo de uso único | Vitor e responsável da TASK-12 |
| Fotos / TASK-26 | Confirmar formatos, tamanho máximo, ciclo do upload, leitura protegida e limpeza de arquivos sem vínculo | Responsável da TASK-26 e backend |
| Contrato REST | Revisar nomes de campos, endpoints, permissões e envelope de resposta antes da integração | Frontend e backend envolvidos |

## Critério de conclusão

- Fluxos disponíveis e coerentes com as regras acordadas.
- Telas revisadas, incluindo estados vazios, validação, erros e confirmação das operações.
- Contrato REST revisado e alinhado ao modelo e à autorização central.
- Decisões acima resolvidas ou explicitamente aceitas pela equipe, com registro da revisão.

Nenhuma revisão externa ou aprovação de Davi, Matheus ou Vitor foi presumida nesta entrega.
