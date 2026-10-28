# Escopo do MVP

Status: proposta para a reunião do grupo (TASK-7). Vale como escopo do projeto depois que o grupo confirmar as decisões da seção 5 e o registro for atualizado neste arquivo.

Documentos irmãos: [glossário](glossario.md) e [regras de negócio](regras-de-negocio.md). Tudo aqui parte da especificação funcional, das 52 user stories do Notion, da [matriz de permissões](../permissoes-e-multitenant.md) e do [modelo de dados](../modelo-de-dados.md).

## 1. O que o sistema é

Plataforma web para gestão de condomínios residenciais, organizada em torno da **unidade** (o apartamento) e usada por vários condomínios ao mesmo tempo, cada um isolado dos demais (multi-tenant). Ela substitui murais, cadernos de portaria, grupos de WhatsApp e combinados verbais por uma central única de encomendas, visitantes e veículos, reservas, ocorrências e avisos, com rastreabilidade das ações críticas.

Nome do sistema: **a definir** (seção 5). Até lá, o nome usado nos documentos é "Sistema de Gestão de Condomínios".

## 2. Quem usa

| Perfil | Quem é | Conta |
| --- | --- | --- |
| **Morador** | Proprietário ou residente de uma ou mais unidades | Individual, com autocadastro |
| **Funcionário** | Porteiro ou segurança do condomínio | Uma conta compartilhada por condomínio; os nomes ficam numa lista cadastrada pela Administração |
| **Administração** | Síndico, subsíndico ou empresa administradora de um condomínio | Uma conta compartilhada por condomínio, com autocadastro e aprovação do ADM |
| **ADM** | Equipe que opera a plataforma e atende todos os condomínios | Individual, criada pela equipe |

## 3. O que entra no MVP

O MVP tem **52 user stories**: 31 Must, 19 Should e 2 Could, distribuídas em 3 sprints de entrega depois da Sprint 0 (setup e modelagem). Must é o que o MVP não pode deixar de ter; Should entra se o tempo permitir; Could só se sobrar capacidade.

| Épico | Stories | Must | Should e Could | O que entrega |
| --- | --- | --- | --- | --- |
| E1 Acesso e contas | 4 | US-101, US-104 | US-102, US-103 | Login por e-mail ou telefone, cadastro de morador, recuperar senha e editar dados |
| E2 Condomínio e estrutura | 10 | US-201, US-202, US-203, US-207, US-209 | US-204, US-205, US-206, US-210; Could: US-208 | Conta da Administração, assistente de cadastro do prédio, aprovação pelo ADM, proprietário e chaves de acesso, porteiros |
| E3 Moradores e unidades | 5 | US-301, US-302, US-304 | US-303, US-305 | Vínculo com a unidade pela chave, ver unidades e proprietário, permissões por aba |
| E4 Encomendas | 4 | US-401, US-402, US-403 | US-404 | Registro com foto da nota, consulta pelo morador, retirada, relatório |
| E5 Visitantes e veículos | 6 | US-501, US-502, US-503 | US-504, US-505, US-506 | Cadastro pelo morador, entrada e saída na portaria, consulta e relatórios |
| E6 Áreas comuns e reservas | 5 | US-601, US-603, US-605 | US-602, US-604 | Cadastro de áreas, reserva por horário sem conflito, gestão pela Administração |
| E7 Ocorrências | 4 | US-701, US-702, US-703 | Could: US-704 | Abrir com anexos, acompanhar, tratar e responder |
| E8 Avisos e comunicados | 4 | US-801, US-802 | US-803, US-804 | Avisos com período, hub do morador, e-mail nos eventos, comunicados da plataforma |
| E9 Suporte e auditoria | 3 | US-903 | US-901, US-902 | Consulta de auditoria, chamados de suporte |
| E10 Fundação técnica | 7 | US-1001 a US-1006 | US-1007 | Isolamento por condomínio, autorização central, arquivos, auditoria, Docker e CI, migrações, proteção de dados |

Por sprint:

| Sprint | Foco | Stories |
| --- | --- | --- |
| Sprint 0 | Setup, modelagem e contratos | Sem stories de produto: repositório, Docker, DER, matriz, design system, contratos de API, escopo e README |
| Sprint 1 | Fundação e acesso | 16, todas Must: E10, contas, condomínio, chaves, vínculo e permissões |
| Sprint 2 | Operação do dia a dia | 15, todas Must: encomendas, visitantes e veículos, reservas, ocorrências, avisos e auditoria |
| Sprint 3 | Complementos | 21, Should e Could: edições, relatórios, e-mail, comunicados, suporte e proteção de dados |

As datas de cada sprint ainda não estão definidas.

## 4. O que fica fora do MVP

| Item | Situação | Motivo e o que fica no lugar |
| --- | --- | --- |
| **Boletos** (emissão, importação, status e inadimplência) | Fora; já registrado na matriz de permissões | Depende de integração bancária. O sistema não tem módulo financeiro |
| **Documentos** (repositório em pastas) | Fora; já registrado na matriz | Os documentos do cadastro do prédio (ata, contrato) continuam, mas como anexo do cadastro, não como módulo |
| **Financeiro** (receita, prestação de contas) | Fora; já registrado na matriz | Evolução futura |
| **Login por reconhecimento facial** | Fora; já registrado na matriz | A foto da conta fica como campo **opcional** |
| **WhatsApp** | Fora; já registrado na matriz | Só e-mail. O WhatsApp do proprietário é apenas dado de contato |
| **SMS** | Fora (proposta) | Recuperar senha e notificações só por e-mail |
| **PIN individual nas contas compartilhadas** | Fora; já registrado na matriz | A auditoria registra a conta e o nome do responsável escolhido na lista |
| **Convite do ADM como forma de entrada do condomínio** (modelo B2B, status "convidado") | Fora (proposta) | Só autocadastro com aprovação do ADM |
| **Taxa de reserva de áreas comuns** | Fora (proposta) | A reserva é gratuita no MVP |
| **Integrações externas** (consulta de CPF/CNPJ em órgão oficial, assinatura digital, catraca) | Fora | Citadas apenas como evolução. O sistema valida só o formato e os dígitos verificadores |
| **Aplicativo nativo** | Fora | Aplicação web responsiva |

## 5. Decisões para a reunião do grupo

A TASK-7 pede que cada ponto em aberto seja levado ao grupo e que a decisão seja registrada. A coluna "Proposta" é o que a documentação já assume. A coluna "Decisão do grupo" fica em branco até a reunião e deve ser preenchida neste arquivo, com a data.

| # | Ponto em aberto | Proposta | Decisão do grupo (data) |
| --- | --- | --- | --- |
| 1 | Boletos, Documentos e Financeiro fora do MVP | Fora (seção 4) | |
| 2 | Login facial | Fora; foto como campo opcional | |
| 3 | Canal de notificação | Só e-mail, sem WhatsApp nem SMS | |
| 4 | Contas compartilhadas | Mantidas, com o nome do responsável nas ações críticas e na entrega de encomenda | |
| 5 | Entrada de condomínios | Só autocadastro com aprovação do ADM; sem convite do ADM | |
| 6 | Vínculo do morador com a unidade | Imediato com a chave válida; a Administração desvincula depois, se for erro | |
| 7 | Dados do proprietário mostrados ao Morador | Tudo, **menos** o documento (CPF ou CNPJ) | |
| 8 | Permissões iniciais do morador | O primeiro da unidade com todas as abas; os seguintes, sem a aba Usuários | |
| 9 | Taxa de reserva de áreas | Sem taxa | |
| 10 | Antecedência máxima para reservar | Sem limite | |
| 11 | Nome do sistema | Escolher entre as opções abaixo ou propor outro | |

**Sobre o nome (ponto 11).** A especificação sugere **CondoHub**, **Vizin**, **Condô+** e **ResidePlus**, apenas como ideias de partida. Antes de decidir, vale pesquisar se o nome já está em uso por outro produto de gestão de condomínios e se o domínio e o nome de usuário no GitHub estão livres. A escolha é do grupo.

## 6. Como o escopo muda depois de fechado

1. Quem quer mudar o escopo abre a discussão com a story ou a task afetada.
2. O grupo decide em reunião ou no canal combinado, e a decisão é registrada neste arquivo, na tabela da seção 5, com a data.
3. A story é criada, alterada ou movida de sprint no Notion e os leads aprovam no portão de revisão da sprint.
4. Nada entra na sprint em andamento sem tirar outra de mesmo tamanho.

## 7. Critério para considerar o escopo fechado

- Todos os pontos da seção 5 têm decisão registrada.
- O grupo concorda que a seção 4 é a lista completa do que fica fora.
- O glossário e as regras de negócio foram lidos por todos e as dúvidas, resolvidas.
