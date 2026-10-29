# Glossário

Status: proposta para a reunião do grupo (TASK-7). Os termos seguem o que já está na [matriz de permissões](../permissoes-e-multitenant.md) e no [modelo de dados](../modelo-de-dados.md). Onde existe um nome técnico no banco ou na API, ele aparece entre crases.

Documentos irmãos: [escopo do MVP](escopo-mvp.md) e [regras de negócio](regras-de-negocio.md).

## 1. Pessoas e perfis

| Termo | Significado |
| --- | --- |
| **Morador** | Pessoa vinculada a uma ou mais unidades (proprietário ou residente). Conta individual. Perfil local `morador`. |
| **Proprietário** | Dono da unidade, cadastrado pela Administração com nome, documento, contatos e foto. **Não é um usuário do sistema**: é um registro da unidade (`proprietarios_unidade`). Pode ou não ter conta de morador. |
| **Funcionário** | Porteiro ou segurança do condomínio. Usa uma conta compartilhada por condomínio (perfil local `funcionario`). Os nomes das pessoas ficam numa lista cadastrada pela Administração e **não fazem login**. |
| **Administração** | Quem gere um condomínio: síndico, subsíndico ou empresa administradora. Usa uma conta compartilhada por condomínio (perfil local `administracao`). Também chamada de "Administração do Prédio". |
| **ADM** | Equipe que opera a plataforma e atende todos os condomínios. Conta individual, marcada por `administrador_plataforma`. **Não** é um perfil de condomínio e não vê o dia a dia de nenhum deles. |
| **Responsável (pela Administração)** | Nome de quem opera a conta compartilhada da Administração, escolhido numa lista a cada ação crítica, para a auditoria saber quem agiu. Não é usuário. |
| **Conta compartilhada** | Login único usado por várias pessoas do mesmo perfil num condomínio (Funcionários e Administração). Trocar o acesso dela derruba as sessões abertas. |
| **Perfil** | Papel de uma conta num condomínio: morador, funcionário ou administração. O ADM é um privilégio global à parte. |

## 2. Condomínio e estrutura

| Termo | Significado |
| --- | --- |
| **Condomínio** (ou prédio) | Cada cliente da plataforma. É o **tenant**: todos os dados de negócio pertencem a um condomínio e nunca se misturam. |
| **Bloco, andar e unidade** | A estrutura física: o condomínio tem blocos, cada bloco tem andares e cada andar tem unidades. A unidade é o apartamento. |
| **Unidade** | O apartamento, centro de quase todos os processos: moradores, visitantes, veículos, encomendas, reservas e ocorrências são ligados a ela. |
| **Assistente de cadastro** | Passo a passo em que a Administração informa nome, blocos, andares e unidades do prédio. O sistema recebe a estrutura inteira de uma vez e grava tudo ou nada. |
| **Status do condomínio** | `pendente` (aguarda análise do ADM), `ativo` (em uso), `rejeitado` (o ADM recusou, com motivo; pode ser corrigido e reenviado) e `desativado` (suspenso pelo ADM). Só `ativo` libera o dia a dia. |
| **Aprovação** | Análise do ADM sobre um condomínio `pendente`: aprova ou rejeita, e rejeitar exige um motivo que a Administração consegue ler. |
| **Reenvio** | Nova submissão de um cadastro `rejeitado`, depois de corrigido. O histórico das tentativas é mantido. |

## 3. Acesso e vínculo

| Termo | Significado |
| --- | --- |
| **Chave de acesso** | Código único de uma unidade, gerado quando o condomínio é aprovado. A Administração o repassa ao proprietário, que o digita **uma vez** para se vincular. Pode ser regenerada (a anterior deixa de valer na hora) ou revogada. Nunca é mostrada ao Morador depois. |
| **Vínculo** | Ligação entre uma conta e um condomínio com um perfil (`vinculos_condominio`). Para o Morador, existe ainda o vínculo com cada unidade (`moradores_unidade`), que pode ser `ativo` ou `desvinculado`. |
| **Desvincular** | Encerrar o vínculo de um morador com a unidade. O que ele já registrou continua na unidade. O acesso cai na requisição seguinte. |
| **Aba** | Cada seção do aplicativo do Morador: Unidades, Visitantes, Veículos, Reserva de Áreas, Encomendas, Ocorrências e Usuários. |
| **Com Acesso e Sem Acesso** | Permissão de um morador numa aba de uma unidade. Quem tem Com Acesso na aba Usuários define a dos outros moradores da mesma unidade. Sem Acesso devolve 403 no servidor. |
| **Hub** | Tela inicial de cada perfil, com o quadro de avisos e os atalhos para as abas. |
| **Login** | Entrada com e-mail ou telefone e senha. Quem tem vínculo em mais de um condomínio escolhe qual usar. |
| **Token (JWT)** | Credencial de curta duração emitida no login. Diz *quem é* o usuário (`sub`) e *em qual condomínio* está (`cid`); a versão da sessão (`sv`) permite derrubar sessões. Perfil e permissões são lidos do banco a cada requisição. |

## 4. Operação do dia a dia

| Termo | Significado |
| --- | --- |
| **Encomenda** | Pacote recebido na portaria, registrado pelo Funcionário com foto da nota fiscal e unidade de destino. Tem três estados: `aguardando_retirada`, `entregue_aguardando_confirmacao` e `retirada_confirmada`. |
| **Destinatário e recebedor** | Destinatário é o morador a quem a encomenda se destina; recebedor é quem retirou. Podem ser pessoas diferentes da mesma unidade. |
| **Confirmação de recebimento** | Etapa final: o morador que recebeu confirma pela própria conta. A conta de Funcionários não confirma pelo morador. |
| **Visitante** | Pessoa autorizada por um morador a entrar na unidade, com período de validade. O cadastro é uma **autorização reutilizável** dentro do período. |
| **Visita (registro de visita)** | Cada entrada e saída de um visitante, registrada pela portaria. Um cadastro pode gerar várias visitas, mas só uma pode estar em aberto por vez. |
| **Visitante avulso** | Visitante cadastrado na hora pela portaria, sem cadastro prévio do morador. |
| **Veículo** | Veículo de uma unidade, com placa, marca, modelo e cor. |
| **Área comum** | Espaço reservável do condomínio (salão, churrasqueira, quadra), com horário de funcionamento. |
| **Reserva** | Uso de uma área comum por uma unidade em um horário de 1 hora numa data. Fica `ativa` ou `cancelada`. |
| **Bloqueio de data** | Período em que a Administração impede reservas numa área, por exemplo para manutenção. |
| **Ocorrência** | Registro de um problema aberto por um morador (barulho, vazamento, dano), com título, detalhe e anexos. Tem dois estados: `em_aberto` e `resolvida`. A reabertura é um evento do histórico. |
| **Aviso** | Comunicado da Administração aos moradores e funcionários do próprio condomínio, com período de exibição. Pode ser marcado como importante. |
| **Comunicado da plataforma** | Mensagem do ADM às Administrações. |
| **Chamado de suporte** | Pedido de ajuda aberto pela Administração e atendido pelo ADM. |
| **Evento de e-mail** | Situação que dispara um e-mail: recuperação de senha, aprovação do condomínio, encomenda registrada e reserva cancelada. O envio é assíncrono. |

## 5. Rastreabilidade e isolamento

| Termo | Significado |
| --- | --- |
| **Multi-tenant** | Uma única plataforma atende vários condomínios, cada um isolado. O identificador do condomínio é `condominio_id`. |
| **Isolamento** | Regra de que um usuário nunca lê nem altera dado de outro condomínio. Recurso de outro condomínio responde 404, como se não existisse. |
| **Auditoria** | Registro de apenas inserção das ações críticas: quem (conta e responsável), o quê, em qual condomínio, valores antes e depois, IP e hora do servidor. |
| **Ação crítica** | Ação que muda o acesso ou o estado do condomínio e por isso é auditada: aprovar, rejeitar, gerar ou revogar chave, mudar permissão, cancelar reserva, entre outras. A lista está na seção 10 da matriz. |
| **Evento de segurança** | Registro de login falho, acesso negado (403) ou tentativa de acessar recurso de outro condomínio. |
| **Registro de apenas inserção** | Tabela em que nada se edita nem se apaga, nem pela aplicação nem pelo banco. |

## 6. Gestão do projeto

| Termo | Significado |
| --- | --- |
| **MVP** | Conjunto mínimo do sistema para a entrega: o que está na seção 3 do [escopo](escopo-mvp.md). |
| **User story** | Necessidade de um perfil escrita como "como X, eu quero Y, para que Z", com critérios de aceite. Identificada por `US-NNN`. |
| **Task** | Trabalho técnico de uma pessoa, ligado a uma ou mais stories. Identificada por `TASK-N`. |
| **Épico** | Grupo de stories do mesmo tema (E1 a E10; E0 é o setup). |
| **Sprint** | Ciclo de trabalho. A Sprint 0 é de setup e modelagem; as Sprints 1 a 3 entregam o produto. |
| **Must, Should e Could** | Prioridade da story (MoSCoW): Must é indispensável, Should entra se houver tempo e Could só se sobrar capacidade. |
| **Portão dos leads** | Revisão que os leads fazem antes de uma sprint seguir adiante. |
| **Definição de pronto** | Condição para uma task ser considerada concluída: código ou documento revisado e aprovado em pull request, com a integração contínua (CI) verde. |
| **DER** | Diagrama entidade-relacionamento: o [modelo de dados](../modelo-de-dados.md). |
| **Migração** | Arquivo versionado que altera a estrutura do banco (Alembic). Nunca se edita uma migração já criada. |
| **Contrato de API** | Documento que fixa rotas, campos e erros de uma parte da API antes de implementá-la. Fica em `docs/api-contracts/`. |
| **ADR** | Registro de uma decisão de arquitetura, em `docs/decisions/`. |
| **Pull request (PR)** | Pedido de mudança no repositório, que só entra na `main` com 1 aprovação e CI verde. |
