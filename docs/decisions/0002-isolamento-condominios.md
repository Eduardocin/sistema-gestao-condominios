# ADR 0002 — Identidade global e vínculos por condomínio

Status: adotada como base inicial de modelagem. Data: 15/10/2026.

Contexto: existem quatro perfis previstos e um usuário pode participar de diferentes condomínios.

Decisão: usuário global com flag de administração da plataforma; vínculos locais únicos por usuário e condomínio, cada qual com perfil e unidade opcional. Unidades sempre pertencem a um condomínio. A unidade do vínculo é validada por FK composta. E-mails são persistidos em minúsculas. Exclusões relacionadas usam `RESTRICT`.

Alternativas: `condominio_id` no usuário impediria participação em vários condomínios; bancos separados aumentariam operação. RLS poderá ser avaliada mais tarde como defesa adicional.

Consequências: é possível separar privilégios globais e locais. A aplicação ainda deve autorizar e filtrar cada operação pelo condomínio. Um vínculo representa um único perfil e uma única unidade; múltiplos perfis/unidades no mesmo condomínio ficam para decisão futura, sem criar tabelas especulativas.
