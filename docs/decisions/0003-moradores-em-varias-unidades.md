# ADR 0003 — Moradores em várias unidades

Status: proposta para o portão dos leads. Data: 21/10/2026.

Contexto: o ADR 0002 deixou um vínculo com um único perfil e, no máximo, uma unidade, adiando "múltiplos perfis/unidades no mesmo condomínio". As histórias US-301 ("um morador pode se vincular a mais de uma unidade") e US-304 (permissão por aba para cada morador, por unidade) tornaram o caso concreto.

Decisão: `vinculos_condominio` continua dizendo em qual condomínio a conta atua e com qual perfil, e segue único por usuário e condomínio. As unidades do Morador passam para a tabela `moradores_unidade` (usuário, unidade, status, parentesco), e as permissões por aba ficam penduradas nela. A coluna `vinculos_condominio.unidade_id` deixa de ser usada e é removida numa migração posterior. Detalhes em [`modelo-de-dados.md`](../modelo-de-dados.md).

Alternativas: permitir várias linhas de vínculo por usuário e condomínio (uma por unidade) duplicaria o perfil e complicaria a escolha de condomínio no login; guardar as unidades em um array no vínculo impediria FKs e constraints.

Consequências: a autorização do Morador lê as unidades ativas em `moradores_unidade` a cada requisição (R6 da matriz). Desvincular é mudar o status de uma linha, sem tocar no vínculo com o condomínio. Continua valendo um único perfil por conta em cada condomínio.
