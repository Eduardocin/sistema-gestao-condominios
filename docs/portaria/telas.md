# Portaria — telas navegáveis da TASK-12

Status: primeira versão para revisão visual e funcional. Substituição dos wireframes estáticos por uma prévia em React proposta pelo responsável da tarefa. A aceitação formal da entrega depende da equipe.

## Acesso e limites

Com o frontend em execução, abra `/prototipos/portaria`. Os atalhos laterais alternam entre Encomendas, Visitantes e Prévia do morador. Não há autenticação simulada nem chamadas de negócio ao backend: todos os registros são exemplos, mantidos em memória nesta aba. Recarregar, sair da rota ou reiniciar a demonstração descarta alterações e fotos. Não usar dados reais.

O seletor de morador é um controle exclusivo da demonstração, não uma troca de perfil autenticado. Na integração, a identidade e as permissões virão da autorização central. Os testes locais não comprovam isolamento multi-tenant da API.

## Telas e fluxos correspondentes

| Tela | Fluxo | Operações e estados |
| --- | --- | --- |
| Encomendas | 01 e 02 | Indicadores, busca por descrição/código/morador/unidade, filtro de status, lista vazia, acesso aos detalhes |
| Receber encomenda | 01 | Unidade, destinatário ativo, descrição, funcionário, foto obrigatória, leitura em andamento, falha de imagem e confirmação |
| Registrar entrega / detalhes | 02 | Foto, histórico, identificação do morador que retira, funcionário responsável e confirmação de entrega física |
| Minhas encomendas | 02 | Encomendas da unidade; confirmação disponível apenas para quem recebeu; diálogo de confirmação |
| Visitantes | 03 e 04 | Indicadores, busca e filtros, visitas em andamento/encerradas, histórico de contatos sem entrada |
| Registrar entrada | 03 | Visitante cadastrado, destino, funcionário, conferência de identidade e autorização prévia ou consulta externa |
| Registrar saída / histórico | 04 | Conferência da saída, funcionário, registro de encerramento e preservação da autorização usada |

## Roteiro de revisão

Capturas da área visível da primeira versão: [encomendas](telas/encomendas.jpg), [recebimento](telas/recebimento-encomenda.jpg), [entrega](telas/entrega-encomenda.jpg), [confirmação pelo morador](telas/confirmacao-morador.jpg), [visitantes](telas/controle-visitantes.jpg), [entrada](telas/entrada-visitante.jpg) e [saída](telas/saida-visitante.jpg). São referências visuais; o roteiro abaixo permite revisar também o conteúdo fora da captura e as interações.

1. Receber uma encomenda: selecione unidade, destinatário e funcionário; preencha a descrição. Tente confirmar sem foto: os campos devem permanecer preenchidos. Anexe uma imagem e registre.
2. Abra Registrar entrega. Selecione outro morador ativo da mesma unidade, confirme a entrega física e registre. O status deve ser **Entregue, aguardando confirmação**; a portaria não confirma pelo morador.
3. Abra Prévia do morador e escolha quem retirou a encomenda. Confirme que recebeu. A confirmação deve atualizar a lista e preservar o histórico de recebimento e entrega.
4. Em Visitantes, selecione Bloco A / 101 e depois Carlos Souza. Existe uma autorização de Ana válida por uma hora a partir da criação dos exemplos; registrar a entrada não consome essa autorização.
5. Registre a saída de Carlos. Uma nova entrada pode usar a mesma autorização enquanto o período estiver vigente. Se expirar, deve apresentar a consulta ao morador. Não é permitido registrar duas visitas simultâneas para o mesmo cadastro.
6. Na consulta externa, registre Interfone ou Telefone e escolha **Não autorizou** ou **Sem resposta**. O contato deve aparecer no histórico, sem criar uma visita em andamento.
7. Teste também uma autorização por contato externo com Marina Lima, destinada ao Bloco B / 202 e autorizada por Júlia Costa.
8. Busque um nome inexistente, confira os estados vazios, navegue por teclado e revise em tela estreita. As tabelas têm rolagem própria quando necessário.

## Decisões da interface propostas nesta versão

- Busca e filtros acima das listas; recebimento e entrada em formulários na área principal; entrega, confirmação e saída em diálogos.
- Funcionário selecionado em cada operação, respeitando as contas compartilhadas descritas na matriz de permissões.
- Descrição obrigatória com limite de 200 caracteres; imagens JPG, PNG ou WebP de até 5 MB. Esses limites são propostas e precisam ser alinhados ao contrato definitivo do armazenamento.
- Exemplos iniciais usam ilustração identificada como tal; novas encomendas exigem uma imagem que o navegador consiga abrir.
- Status sempre escritos em texto; erros de foto preservam os outros campos; ações físicas exigem confirmação explícita.
- Ao abrir um formulário ou retornar de um formulário/diálogo, o foco vai para o título do conteúdo. O próximo Tab continua nas ações e campos dessa tela.
- Decisão de 22/10/2026: mantida confirmação de encomenda pelo recebedor; visitantes passam a usar autorização por período, com múltiplas entradas após a saída anterior. A lista de visitantes é filtrada pela unidade. O objeto de autorização da prévia é uma projeção dos dados do cadastro; não pressupõe uma tabela de uso único na API.

## Componentes

Usa o design system existente e adiciona `OperationsLayout`, `MetricCard`, `Notice`, `CheckField` e `RecordPhoto`. O catálogo `/design-system` apresenta os novos elementos e um acesso à composição completa. `Badge wrap` permite status extensos em telas estreitas. As páginas mantêm somente estilos de layout em CSS Modules.

## Verificação

- Revisão em 22/10/2026: recebimento com foto e preservação dos campos no erro; entrega a outro morador da unidade; confirmação exclusiva do recebedor; contato sem resposta sem visita; entrada, saída e autorização preservada para reentrada. Foco conferido ao abrir e retornar de formulários e diálogos.
- Responsividade conferida com viewport de 390 × 844: página e formulário sem transbordamento horizontal; tabelas preservam sua rolagem interna. [Captura em tela estreita](telas/encomendas-mobile.jpg).
- Testes de transições locais: `npm test` em `frontend/` (Node compatível com o `engines` do projeto).
- Verificações existentes: `npm run typecheck`, `npm run lint`, `npm run build`.
- Conferência manual: seguir o roteiro acima. A integração e os testes de API continuam nas respectivas tarefas.

Veja [fluxos](fluxos.md), [contrato REST proposto](../api-contracts/portaria.md) e [pendências de revisão](decisoes-pendentes.md).
