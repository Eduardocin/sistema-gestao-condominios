# Apresentação final — Sistema de Gestão de Condomínios (Task extra)

Documento de apoio para a apresentação ao vivo. Tem três partes: **(1)** roteiro da apresentação, **(2)** justificativa das decisões técnicas e **(3)** simulação de defesa com perguntas de stakeholders. Todos os números e afirmações vêm do repositório (README, `docs/`, ADRs e código); o que ainda não existe está dito como não existe.

---

## Parte 1 — Apresentação do projeto

Tempo sugerido: 12 a 15 minutos + perguntas. Um bloco por slide.

### Slide 1 · O problema
- Encomendas anotadas em caderno, visitas liberadas por WhatsApp, reservas de salão por combinado verbal, avisos no mural.
- Consequência: sem histórico, sem responsável identificado, sem rastro de quem fez o quê.
- **Frase de abertura:** "Hoje, quando uma encomenda some na portaria, ninguém consegue provar quem recebeu e quem retirou."

### Slide 2 · A solução
Plataforma web multi-condomínio que centraliza as rotinas e **preserva o histórico**, com os dados de cada condomínio isolados dos demais.

| Perfil | O que faz |
| --- | --- |
| Administração | Gere estrutura (blocos, andares, unidades), funcionários, responsáveis, áreas comuns, avisos e relatórios |
| Morador | Vincula-se à unidade por chave, cadastra visitantes e veículos, reserva áreas, abre ocorrências, acompanha encomendas |
| Portaria | Registra encomendas com foto, entrada e saída de visitantes |
| ADM da plataforma | Aprova cadastros de condomínios e consulta auditoria, **sem acesso operacional** aos condomínios |

### Slide 3 · Escopo e entrega
- MVP definido em **52 user stories** (31 Must, 19 Should, 2 Could) em 10 épicos.
- Código: monólito modular com **19 módulos de domínio**, ~18,7 mil linhas de Python no backend, 81 arquivos de teste, 10 migrations, 125 commits.
- Fora do MVP, por decisão registrada: boletos, financeiro, documentos, login facial, WhatsApp, SMS, app nativo.

### Slide 4 · Arquitetura (uma figura)
```
React 19 + TS ─► HTTP/REST /api/v1 ─► FastAPI
                                       Router → Service → Repository
                                                     │
                                  ┌──────────────────┼───────────────┐
                              PostgreSQL 17      MinIO (S3,        Outbox de e-mail
                              (isolamento por    bucket privado,   (fila no banco)
                               condominio_id)    URL assinada 60s)
```
Quatro camadas com responsabilidade única: Router (HTTP/autorização), Service (caso de uso e transação), Repository (consulta sempre com escopo do condomínio), Models (constraints).

### Slide 5 · Segurança e privacidade (o diferencial)
- `condominio_id` **vem do token, nunca da requisição**; o corpo com esse campo é rejeitado (422).
- Recurso de outro condomínio responde **404**, igual a inexistente (não revela existência).
- Perfil lido **do vínculo no banco a cada requisição**, não do claim do JWT: revogar acesso vale na próxima chamada.
- Arquivos em bucket privado; download por URL assinada de 60 s.
- Auditoria transacional das ações críticas; documento de LGPD descrevendo dado, finalidade e quem vê.

### Slide 6 · Demonstração (roteiro de 10 minutos)
Roteiro completo, com cliques e falas, em [docs/demo/README.md](demo/README.md). Rode o seed antes para ter datas frescas.
1. **Plataforma:** aprovar o Residencial Vista Verde (pendente) e ver o evento na auditoria.
2. **Administração:** estrutura, chaves, criar um aviso, responder e resolver uma ocorrência reaberta.
3. **Portaria:** receber encomenda **com foto**, registrar saída de visitante, consultar placa repetida.
4. **Morador:** ver o aviso novo, confirmar a retirada da encomenda, reservar área e abrir ocorrência.
5. **Isolamento:** trocar para Pátio do Horizonte; no Swagger, recurso de outro condomínio responde 404.

### Slide 7 · Qualidade
- CI em GitHub Actions: Ruff, Mypy, Pytest contra PostgreSQL real, ESLint, TypeScript, validação de migrations em banco limpo e teste de storage privado com MinIO.
- Testes negativos obrigatórios: dois condomínios, outra unidade, perfil errado, aba sem acesso.

### Slide 8 · Estado atual e próximos passos (honesto)
- **Pronto:** backend dos 19 módulos nos recortes descritos no README; telas de acesso, funcionários e encomendas.
- **Pendente:** telas da maioria dos fluxos; entrega real de e-mail (a fila existe, o worker foi o último PR); US-208 (desativar condomínio), US-303 (convites), exportação CSV.
- Fechar com: "Priorizamos fundação e regras de negócio corretas antes de interface, porque o custo de errar isolamento de dados é maior que o de uma tela faltando."

> **Antes de apresentar:** confirme na `main` o que foi integrado desde este rascunho (o README diz "desta branch"). Não afirme em público algo que o README lista como pendente.

---

## Parte 2 — Justificativa das decisões técnicas

Formato: **decisão → por quê → alternativa descartada → custo assumido**.

| # | Decisão | Por quê | Alternativa descartada | Custo assumido |
| --- | --- | --- | --- | --- |
| 1 | **Monólito modular** em monorepo (ADR 0001) | Equipe acadêmica, trabalho paralelo, transação local simples, execução com um comando | Microserviços: mais contratos e infraestrutura sem benefício de escala necessário | Disciplina para manter fronteiras entre módulos; deploy único |
| 2 | **Isolamento lógico por `condominio_id`** em camada comum (`RepositorioDoCondominio`) | O desenvolvedor do módulo não escreve o filtro, então não esquece. Classe falha na definição se o model não tem a coluna | `condominio_id` por usuário (impede vários condomínios); banco por condomínio (operação cara) | Sem RLS: uma consulta SQL escrita fora do repository vazaria dados. Mitigado por convenção, guia de arquitetura e testes de isolamento |
| 3 | **Identidade global + vínculo por condomínio** (ADR 0002) | Uma pessoa pode ser morador num prédio e administrar outro | Usuário preso a um condomínio | Toda operação precisa resolver o vínculo ativo |
| 4 | **Moradores em várias unidades via `moradores_unidade`** (ADR 0003) | US-301 e US-304 exigem N unidades e permissão por aba por unidade; permite FKs e constraints | Várias linhas de vínculo (duplica perfil); array no vínculo (sem FK) | Autorização do morador consulta o banco a cada requisição |
| 5 | **FastAPI + Pydantic v2** | Validação e contrato OpenAPI automáticos; `extra="forbid"` bloqueia campos indevidos | Django/DRF (mais pesado para API pura) | Time precisa conhecer tipagem Python |
| 6 | **SQLAlchemy 2 síncrono** | Simplicidade de depuração e transações; carga prevista não exige async | Async: complexidade sem ganho mensurável no MVP | Menor concorrência por processo; pool limitado (5+10). Revisitar se houver carga |
| 7 | **PostgreSQL 17 + constraints no banco** (FK composta, CHECK, `RESTRICT`) | Integridade não depende só da aplicação; FK composta `(unidade_id, condominio_id)` impede unidade de outro prédio | Banco só como armazenamento | Migrations exigem coordenação (Alembic validado no CI) |
| 8 | **Service faz o commit; repository não** | Fronteira de transação explícita por caso de uso | Commit implícito por requisição | Cada service precisa lembrar de commitar |
| 9 | **JWT com `sv` (versão de sessão) + refresh + perfil lido do banco** | Trocar senha/credencial da conta compartilhada invalida tokens antigos; perfil não é forjável por claim | Sessão apenas stateless | Uma consulta de vínculo por requisição |
| 10 | **Contas compartilhadas** para Administração e Portaria, com lista nominal de responsáveis/funcionários | Realidade do condomínio (porteiro troca de turno); auditoria registra conta **e** nome escolhido | Conta individual por porteiro | Identificação do operador é declaratória, não autenticada (PIN individual ficou fora, decisão registrada) |
| 11 | **MinIO (S3) privado + URL assinada curta** | Arquivo fora do banco, compatível com S3 em produção, sem URL pública permanente | BLOB no PostgreSQL (infla backup); bucket público | Mais um serviço no Compose; compensação de falha entre storage e banco |
| 12 | **Upload binário** (não base64/multipart) com limite real de leitura | Menor consumo de memória e superfície de ataque | Base64 em JSON | Cliente precisa tratar corpo binário |
| 13 | **Outbox de e-mail no banco** | O evento é gravado na mesma transação do fato (aprovação, encomenda); envio não derruba a operação | Enviar SMTP dentro da requisição | Entrega assíncrona e atrasada; exige worker |
| 14 | **Desativação lógica, não DELETE** | Histórico e auditoria preservados; nenhum perfil apaga registro | Exclusão física | Consultas precisam filtrar por situação |
| 15 | **Auditoria transacional** | Registro e ação comitam juntos: não há ação sem rastro | Log de aplicação | Mais escrita no banco |
| 16 | **React 19 + TS + Vite**, sessão por aba em `sessionStorage`, renovação de token compartilhada | Tipagem, build rápido; sessão não persiste entre abas fechadas | `localStorage` (persistência maior, exposição maior a XSS entre sessões) | O usuário relogia ao fechar a aba |
| 17 | **Spec antes do código**: contratos em `docs/api-contracts`, ADRs, matriz de permissões | Frontend e backend avançaram em paralelo contra o contrato | Código primeiro | Documentação precisa ser mantida (há testes que falham se o guia divergir do código) |

**Princípio que une as decisões:** onde o erro é caro (vazamento entre condomínios, perda de histórico), a regra fica **no banco e na camada comum**; onde o erro é barato (tela, formato de relatório), a solução é a mais simples.

---

## Parte 3 — Simulação de defesa

**Como usar:** ensaiar em voz alta com duas pessoas fazendo os papéis. As respostas abaixo são o **roteiro**: são fiéis ao que o projeto faz, inclusive onde ele é fraco. Quando a pergunta tocar numa limitação, admita primeiro e depois mostre a mitigação.

### Banca / stakeholders simulados
- **Síndico (cliente)**: quer saber se resolve o dia a dia e se é confiável.
- **Professor de engenharia de software**: quer ver decisão fundamentada e trade-offs.
- **Segurança / jurídico (LGPD)**: quer saber quem vê o quê.
- **Investidor / coordenador**: quer saber se escala e o que falta para usar de verdade.

### Bloco A · Síndico

**1. "Por que só vejo poucas telas funcionando?"**
> Priorizamos a base que não pode ser refeita depois: isolamento entre condomínios, permissões e histórico. Backend dos módulos está completo nos recortes do README e testado; as telas de acesso, funcionários e encomendas estão integradas e as demais estão nos próximos passos. Uma tela se refaz em dias; um modelo de dados que vazou entre condomínios, não.

**2. "O porteiro troca de turno. Como sei quem recebeu a encomenda?"**
> A conta é compartilhada por condomínio, mas o porteiro escolhe seu nome numa lista cadastrada pela Administração, e isso é gravado na auditoria junto com a conta. Admitimos o limite: a escolha do nome é declaratória, não autenticada. Um PIN individual foi avaliado e deixado fora do MVP por decisão registrada.

**3. "O morador vai receber e-mail quando a encomenda chegar?"**
> O evento já é gravado numa fila (outbox) na mesma transação do registro, e há um worker assíncrono de envio. A recuperação de senha por e-mail ainda depende da solicitação e da configuração de SMTP em produção. Não vou prometer e-mail em produção hoje.

**4. "Posso ver as encomendas paradas há mais de uma semana?"**
> Há relatório administrativo por status e unidade, com filtro de período, no backend. Falta a tela. Não existe alerta automático de encomenda parada; é um próximo passo simples.

### Bloco B · Professor

**5. "Por que monólito e não microserviços?"**
> Equipe pequena, domínio fortemente relacional (unidade liga encomenda, visita, reserva e ocorrência) e necessidade de transação local. Microserviços trariam contratos e operação sem problema de escala que os justifique. Mantivemos fronteiras por módulo para permitir extrair um serviço depois (ADR 0001).

**6. "Por que SQLAlchemy síncrono?"**
> Decisão consciente por simplicidade e depuração. O MVP não tem carga que exija async, e misturar async no ORM aumentaria a complexidade da equipe. O pool tem limite explícito (5 + 10 por processo). Se a carga crescer, a camada repository concentra a mudança.

**7. "Isolamento só por aplicação não é frágil? Por que não Row Level Security?"**
> É o ponto mais honesto do projeto: sim, é uma defesa em uma camada. Mitigamos tornando o filtro **automático** no repositório base (quem herda não escreve o `WHERE`), com falha na definição da classe se o model não tem `condominio_id`, FK composta no banco e testes com dois condomínios em cada módulo. RLS está registrado no ADR 0002 como defesa adicional a avaliar.

**8. "Como garantem que ninguém esquece o filtro num endpoint novo?"**
> Três peças: `ContextoDep` entrega o contexto validado, `RepositorioDoCondominio` aplica o filtro, e o guia de arquitetura é testado (um teste falha se o exemplo do guia divergir do código). Um desenvolvedor que escrever `select(Model)` direto num service foge da convenção; isso é pego em revisão, não pelo compilador. Reconheço essa lacuna.

**9. "Por que o perfil vem do banco e não do JWT?"**
> Para que revogação tenha efeito imediato. Desvincular um morador ou trocar a credencial da conta compartilhada passa a valer na próxima requisição, sem esperar o token expirar. O custo é uma consulta por requisição, aceitável nesta escala.

**10. "Como testam?"**
> Pytest contra PostgreSQL real (não SQLite), validação das migrations em banco limpo no CI, teste de storage com MinIO real, e casos negativos obrigatórios: outro condomínio, outra unidade, perfil errado, aba sem acesso.

### Bloco C · Segurança e LGPD

**11. "Quem acessa dado pessoal e onde ele fica?"**
> Há um inventário por tabela com finalidade (`docs/protecao-de-dados.md`). O ADM da plataforma não tem acesso operacional aos condomínios; a Administração só vê o próprio; o morador só as unidades vinculadas e abas liberadas. Senhas e tokens guardam apenas hash.

**12. "O que a LGPD exige que vocês ainda não fazem?"**
> O documento lista limitações e pendências abertamente. Não tratamos de direitos do titular de ponta a ponta (como exportação/eliminação sob demanda) nem política de retenção automatizada. É um LGPD básico: mapear, minimizar, mascarar e auditar. Não é um parecer jurídico.

**13. "As fotos das encomendas ficam públicas?"**
> Não. Bucket privado; o download exige autenticação e devolve URL assinada que expira em 60 segundos. Arquivo de outro condomínio responde 404.

**14. "Alguém do suporte pode ler o histórico de funcionários?"**
> O histórico é exclusivo da Administração do próprio condomínio ativo e expõe apenas ação, data e responsável. É uma exceção restrita à auditoria geral, e o README registra que ela ainda aguarda revisão de autorização. Vou reportá-la como decisão pendente, não como fechada.

### Bloco D · Investidor / coordenação

**15. "Escala para quantos condomínios?"**
> Não medimos. A arquitetura não tem estado local por requisição e o banco é indexado por `condominio_id`, então a escala horizontal da API é direta; o gargalo inicial seria o PostgreSQL. Teste de carga não foi feito; seria o próximo passo antes de produção.

**16. "O que falta para um condomínio real usar?"**
> (1) Telas dos fluxos restantes; (2) SMTP em produção e recuperação de senha completa; (3) provisionamento inicial do ADM e deploy fora do Compose; (4) teste de carga e backup/restauração; (5) revisão jurídica de LGPD. Não é lançável hoje sem esses itens.

**17. "Qual o maior risco técnico?"**
> Isolamento só na aplicação (pergunta 7). Segundo: dívida de interface, porque o backend está bem à frente do frontend.

**18. "Por que não incluir boletos? É o que síndico mais quer."**
> Depende de integração bancária e entra num módulo financeiro. Foi decisão explícita de escopo, registrada em `escopo-mvp.md`, para entregar o núcleo operacional com qualidade.

### Perguntas-armadilha (resposta curta e honesta)

| Pergunta | Resposta |
| --- | --- |
| "Está pronto?" | "O backend do MVP está nos recortes descritos; o produto completo não, e dizemos o que falta." |
| "Já tem usuários reais?" | "Não. É um projeto acadêmico; não há validação em produção." |
| "O protótipo da portaria é real?" | "Não: `/prototipos/portaria` é demonstração com dados fictícios em memória; o fluxo real de encomendas está em `/app/portaria/encomendas`." |
| "Isso é à prova de vazamento?" | "Nenhum sistema é. Há quatro barreiras (token, repositório, constraints, testes) e uma lacuna conhecida (sem RLS)." |

### Checklist de ensaio
- [ ] Decorar as 3 limitações: sem RLS, e-mail ainda não é entrega ponta a ponta confirmada, telas incompletas.
- [ ] Ter o Swagger e a suíte de isolamento abertos para provar afirmações.
- [ ] Conferir a `main` atual antes de falar do que "está pronto".
- [ ] Definir quem responde cada bloco (A: produto, B: arquitetura, C: segurança, D: planejamento).
- [ ] Nunca afirmar algo que o README lista como pendente.
