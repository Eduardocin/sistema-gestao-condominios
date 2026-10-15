# ADR 0001 — Monorepo e monólito modular

Status: adotada conforme os requisitos fornecidos. Data: 15/10/2026.

Contexto: equipe acadêmica desenvolvendo processos relacionados, com necessidade de execução local simples e trabalho paralelo.

Decisão: frontend e backend no mesmo repositório; backend único dividido por domínio, SQLAlchemy síncrono e PostgreSQL. Docker executa apenas o banco. Cada camada surge quando houver comportamento concreto.

Alternativas: microserviços aumentariam contratos e infraestrutura sem benefício necessário; uma aplicação sem limites de módulos facilitaria acoplamento entre os processos.

Consequências: uma entrega backend e transações locais simples. A equipe deve preservar interfaces de módulos e coordenar migrações de banco. Deploy e extração de serviços são decisões futuras.
