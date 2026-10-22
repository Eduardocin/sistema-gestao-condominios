# Portaria — fluxos acordados

Os diagramas estão no [quadro FigJam da TASK-12](https://www.figma.com/board/FMaClEaEDHx5aRfKnzKZWD). Este texto registra as decisões usadas nas [telas navegáveis](telas.md), sem alterar o quadro.

## 01 — Recebimento de encomenda

Identificar unidade e destinatário com vínculo ativo → descrever a encomenda → identificar funcionário → anexar foto → confirmar recebimento. Registrar data/hora e responsável; iniciar em **Aguardando retirada**. Foto ausente ou inválida impede a conclusão e mantém os demais campos para nova tentativa.

## 02 — Entrega e confirmação

Localizar encomenda aguardando retirada → identificar quem retira e conferir vínculo ativo na mesma unidade → entregar fisicamente → registrar funcionário e data/hora → mudar para **Entregue, aguardando confirmação** → o morador que recebeu confirma pela própria conta → mudar para **Retirada confirmada**.

O destinatário ou outro morador ativo da unidade pode retirar. Recebimento, entrega e confirmação mantêm atores e horários distintos. Não repetir a entrega. A portaria consulta pendências e cobra confirmação por contato externo; não há assinatura, confirmação automática, prazo de encerramento nem confirmação administrativa em nome do morador.

## 03 — Entrada de visitante

Selecionar visitante já cadastrado → verificar identidade e destino → consultar autorização prévia para o visitante, unidade e janela de validade.

- Válida: confirmar a entrada sem consumir a autorização. Ela permite novas entradas dentro do período, após a saída da visita anterior.
- Ausente, expirada ou cadastro cancelado: consultar morador por interfone ou telefone e registrar a resposta.
- Morador autorizou: registrar entrada e iniciar visita **Em andamento**.
- Negativa ou sem resposta: registrar contato e não liberar entrada.

Decisão atualizada em 22/10/2026: mantida a abordagem do PR #5, com autorização prévia reutilizável durante o período cadastrado pelo morador. Cada entrada gera uma visita independente. O cadastro do visitante pertence à unidade de destino; não usar um cadastro de outra unidade. As datas do cadastro abrangem os dias informados, inclusive o último dia, no fuso do condomínio. Cadastro avulso de visitante pertence à TASK-64; a TASK-37 utiliza o cadastro feito pelo módulo de Vitor.

## 04 — Saída de visitante

Localizar visita em andamento → conferir saída física → identificar funcionário → registrar data/hora → mudar para **Encerrada**, preservando entrada e autorização. Não exige confirmação do morador. Visita sem saída registrada permanece em andamento para conferência; não é encerrada automaticamente. Uma nova visita exige nova verificação de autorização.
