# Roteiro da demonstração

Roteiro de **10 minutos** em cinco atos, um por perfil, contando a mesma
história: um condomínio novo entra na plataforma e a rotina de um condomínio
já ativo acontece de ponta a ponta. Cada ato tem **o que clicar** e **o que
falar**. Tudo usa os dados fictícios do seed (`docker compose ... run demo-seed`,
veja o [README](../../README.md#demonstração-com-dados-fictícios)).

Todos os registros, ilustrações e credenciais são fictícios e exclusivos do
ambiente local. Cada reset recria a massa a partir da data da execução no fuso
America/Sao_Paulo; por isso “ontem”, “daqui a 2 dias” etc. sempre fazem sentido.

## Contas

Senha de todas: `Teste123`.

| Perfil | E-mail | Onde cai |
| --- | --- | --- |
| ADM da plataforma | `plataforma@example.test` | Análise de condomínios, suporte, comunicados e auditoria |
| Administração | `administracao@example.test` | Escolhe Jardins da Aurora ou Pátio do Horizonte |
| Portaria | `portaria.aurora@example.test` | Jardins da Aurora; responsável **Porteiro Demo** |
| Morador | `morador.aurora@example.test` | Ana Souza, Bloco A · 101, Jardins da Aurora |
| Administração (pendente) | `administracao.vistaverde@example.test` | Residencial Vista Verde, aguardando aprovação |

Contas extras (mesma senha) para trocar de ponto de vista se alguém pedir:
`morador.aurora.a102` (Bruno Lima), `morador.aurora.a201` (Carla Mendes),
`morador.aurora.b101` (Diego Rocha), `morador.aurora.b302` (Elisa Fernandes),
`morador.horizonte` (Fábio Martins, 202), `morador.horizonte.t101` (Gabriela
Nunes) e `portaria.horizonte`, todas `@example.test`.

## O que o seed cria

| Condomínio | Conteúdo |
| --- | --- |
| **Jardins da Aurora** (SP) | 2 blocos × 3 andares × 2 unidades (12 unidades), 5 moradores, 3 funcionários, 2 responsáveis, chaves para as 7 unidades vagas (Bloco B · 202 tem a chave fixa `AURRA-B2Z22`), 3 áreas comuns, 8 reservas (ativas, passada, cancelada pelo morador e pela Administração com motivo), 9 encomendas nos três estados, 4 visitantes (no prédio, já saiu, agendados), 4 veículos (com uma placa repetida entre unidades), 4 ocorrências (aberta, respondida, resolvida e reaberta), 4 avisos (vigentes, agendado e encerrado), 3 chamados de suporte e eventos de auditoria |
| **Pátio do Horizonte** (MG) | Torre única com 4 unidades, 2 moradores, 2 áreas, reservas, encomendas, visitante, veículos, ocorrências, avisos e 1 chamado: serve para mostrar o isolamento |
| **Residencial Vista Verde** (PR) | Cadastro **pendente** com estrutura, para o ADM aprovar ao vivo |
| Plataforma | 2 comunicados enviados às Administrações |

## Antes de começar (5 minutos antes)

1. Rode o seed para ter datas frescas e nenhum resto de ensaio.
2. Abra **quatro abas** no mesmo navegador, uma por perfil: ADM da
   plataforma, Administração (Jardins da Aurora), Portaria e Morador. O login
   fica guardado por aba, então cada uma mantém a sua conta. Abra cada aba
   nova digitando o endereço: “Duplicar aba” copia o login da aba de origem.
3. Deixe uma imagem qualquer na área de trabalho para a foto da encomenda.
4. Zoom do navegador em 90% se a projeção for 1366 × 768.

## Ato 1 — Plataforma: um condomínio novo entra (1,5 min)

Janela **ADM da plataforma**.

1. **Condomínios** → situação **Pendente** → *Residencial Vista Verde* →
   **Ver detalhes**. Mostre CNPJ, endereço e a estrutura enviada.
2. **Aprovar condomínio**.
3. **Auditoria** → o evento `condominio.aprovar` aparece no topo, com quem fez e quando.

> **Falar:** “O ADM aprova cadastros e consulta a auditoria, mas não enxerga
> encomendas, visitantes ou reservas de nenhum condomínio. Ao aprovar, o sistema
> gera uma chave de acesso para cada unidade.”

## Ato 2 — Administração: o condomínio em operação (2,5 min)

Janela **Administração**, em Jardins da Aurora.

1. **Visão geral** → a barra lateral mostra todos os módulos em qualquer tela.
2. **Condomínio e estrutura** → Bloco A e Bloco B, andares e unidades.
3. **Chaves de acesso** → Bloco B · 202 tem a chave `AURRA-B2Z22`, que um
   morador novo usaria para se vincular.
4. **Avisos** → mostre vigente importante, agendado e encerrado. Escolha o
   responsável **Responsável Demo** e crie um aviso “Limpeza da caixa d’água”
   para hoje. *(O morador vai vê-lo no Ato 4.)*
5. **Ocorrências** → situação **Em aberto** → *Vazamento na garagem* (reaberta
   pelo morador) → responda e **resolva** com o responsável.
6. **Reservas** → a reserva cancelada pela Administração mostra motivo e responsável.

> **Falar:** “Toda ação administrativa exige escolher quem é o responsável. É
> isso que vai para a auditoria, mesmo quando várias pessoas usam a mesma conta.”

## Ato 3 — Portaria: encomendas e visitantes (2 min)

Janela **Portaria**.

1. **Encomendas** → mostre as três situações (aguardando retirada, entregue
   aguardando confirmação, retirada confirmada).
2. **Receber encomenda** → Bloco A · 101, Ana Souza, “Caixa de café”, foto da
   nota, responsável **Porteiro Demo** → salvar.
3. **Visitantes** → *Visitantes no prédio*: Visitante Demo está na 101 desde
   ontem → **registrar saída**.
4. **Consultar veículos** → busque `BRA2E19`: a mesma placa aparece em duas
   unidades (A · 102 e B · 101).

> **Falar:** “A portaria usa uma conta compartilhada, mas cada registro guarda o
> nome do funcionário que agiu. A foto vai para um bucket privado e só abre por
> link assinado que expira em 60 segundos.”

## Ato 4 — Morador: a rotina do outro lado (2 min)

Janela **Morador** (Ana Souza).

1. **Visão geral** → o aviso criado no Ato 2 já aparece, junto com o da manutenção dos elevadores.
2. **Encomendas** → a *Caixa de café* do Ato 3 está lá. Abra *Pacote de
   papelaria* → confira a foto → **Confirmar que recebi**.
3. **Reservar área** → Churrasqueira, um horário livre nos próximos dias.
4. **Ocorrências** → abra “Lâmpada queimada na garagem”.
5. Volte à janela da **Administração** → **Ocorrências** → a nova ocorrência
   aparece como *Aguardando administração*.

> **Falar:** “O morador só vê a própria unidade. As abas que ele acessa são
> liberadas por permissão, por unidade.”

## Ato 5 — Isolamento entre condomínios (1 min)

1. Na **Administração**, **Trocar condomínio** → Pátio do Horizonte.
   Estrutura, áreas, encomendas e ocorrências são outras; nada da Aurora aparece.
2. *(Opcional, para banca técnica)* No Swagger (`/docs`), com o token do
   morador da Aurora, peça uma encomenda do Horizonte: a resposta é **404**,
   igual a um recurso inexistente.

> **Falar:** “O `condominio_id` vem do token, nunca da requisição. Recurso de
> outro condomínio responde 404, para não revelar nem que ele existe.”

## Se algo der errado

- **Dados bagunçados pelo ensaio:** rode o seed de novo (cerca de 40 s) e entre outra vez — o reset recria as contas.
- **Porta ocupada:** use as portas alternativas abaixo.
- **Sem rede/Docker na hora:** use o backup (seção seguinte) ou o vídeo do ensaio.
- **Pergunta sobre algo sem tela:** responda pelo Swagger em `/docs`.

## Ensaio de inicialização

Em 26/11/2026, o build, o seed e a subida do stack levaram **36,9 segundos**
com a sequência do README, projeto Compose e volumes novos. O ensaio usou
Docker Desktop Engine 29.9.2, Compose 5.6.1 e Windows 11 com 12 processadores
lógicos e 7,4 GiB disponíveis no Docker. Os builds reaproveitaram as camadas de
dependências Python, npm e MinIO. Um ensaio anterior que reinstalou as
dependências npm levou 46,3 segundos. Os tempos não medem a preparação em uma
máquina sem cache.

Se as portas padrão já estiverem ocupadas, ajuste as variáveis em
`.env.demo`, baseado em `.env.example`. Use `APP_ENV_FILE=.env.demo` para
que as mesmas variáveis cheguem aos containers.

```dotenv
APP_ENV_FILE=.env.demo
POSTGRES_PORT=55466
API_PORT=18066
WEB_PORT=15166
STORAGE_PORT=19066
STORAGE_CONSOLE_PORT=19166
CORS_ORIGINS=["http://127.0.0.1:15166","http://localhost:15166"]
VITE_API_BASE_URL=http://127.0.0.1:18066/api/v1
STORAGE_PUBLIC_ENDPOINT=http://127.0.0.1:19066
```

Nas portas do exemplo, acesse `http://127.0.0.1:15166/login`.
Mantenha `.env.demo` fora do Git.

## Backup e restauração

Gere o backup no formato custom logo após o seed do projeto de demonstração,
antes de testar ações. Crie a pasta local `.superpowers/demo-local/` para
guardar a cópia fora do Git. Os comandos usam as credenciais locais de
`.env.example` copiadas para `.env.demo`.

```sh
docker compose -p condominios-demo --env-file .env.demo exec -T db pg_dump -U condominios_dev -d condominios -Fc --no-owner --no-acl -f /tmp/task66-demo.dump
docker compose -p condominios-demo --env-file .env.demo exec -T db pg_restore --list /tmp/task66-demo.dump
docker compose -p condominios-demo --env-file .env.demo cp db:/tmp/task66-demo.dump .superpowers/demo-local/task66-demo.dump
```

Para restaurar, use outro projeto Compose com portas livres e crie um banco
vazio. Se a demo ainda estiver rodando, configure portas distintas em outro
arquivo de ambiente e passe o caminho desse arquivo nos comandos. O seed do
novo projeto prepara os quatro objetos PNG no MinIO, com as mesmas chaves
registradas no backup. As chaves seguem `condominio/{id}/{modulo}/{arquivo_id}`.
Os IDs dos condomínios e dos quatro arquivos são reservados à demo. O seed
inicial usa o banco descartável `condominios` do projeto de restauração. A
cópia do backup vai para `condominios_restaurado`:

```sh
docker compose -p condominios-restauracao --env-file .env.demo --profile demo run --build --rm demo-seed
docker compose -p condominios-restauracao --env-file .env.demo exec -T db createdb -U condominios_dev condominios_restaurado
docker compose -p condominios-restauracao --env-file .env.demo cp .superpowers/demo-local/task66-demo.dump db:/tmp/task66-demo.dump
docker compose -p condominios-restauracao --env-file .env.demo exec -T db pg_restore --exit-on-error --single-transaction -U condominios_dev -d condominios_restaurado /tmp/task66-demo.dump
docker compose -p condominios-restauracao --env-file .env.demo exec -T db psql -U condominios_dev -d condominios_restaurado -c "SELECT c.nome, c.status, count(v.id) AS vinculos FROM condominios c JOIN vinculos_condominio v ON v.condominio_id = c.id GROUP BY c.nome, c.status;"
```

A consulta final deve listar Jardins da Aurora e Pátio do Horizonte ativos e
Residencial Vista Verde pendente. As datas no backup são as da gravação; use o
seed para obter datas novas.

Para consultar a cópia restaurada na API, rode o comando abaixo em outro
terminal. Troque a porta publicada se a porta 8000 estiver ocupada.
O Swagger permite verificar os logins em `POST /api/v1/auth/login`.

```sh
docker compose -p condominios-restauracao --env-file .env.demo run --build --rm --no-deps -e POSTGRES_DB=condominios_restaurado -p 127.0.0.1:8000:8000 api
```
