# Vínculo Morador–Unidade — TASK-30 / US-301 e US-302

Implementa o [contrato do núcleo, seções 7–8](../../../../docs/api-contracts/nucleo.md#7-vínculo-do-morador-com-a-unidade)
com os modelos existentes, sem migration ou dependência nova.

## API

| Método e rota | Permissão e resposta |
| --- | --- |
| `POST /api/v1/vinculos/chave` | Conta autenticada com `tipo_cadastro=morador`, sem exigir `cid`; `{"chave":"K7M2P-9QXW4"}`; 201 com referências de unidade/condomínio e `Location` para o detalhe |
| `GET /api/v1/minhas-unidades` | Perfil Morador no condomínio ativo selecionado; somente associações/unidades ativas com aba `unidades` habilitada; `page=1`, `page_size=20` (1–100), `total` |
| `GET /api/v1/minhas-unidades/{unidade_id}` | Mesmo perfil/condomínio; 404 sem associação própria ativa ou unidade inativa; 403 se a aba está desabilitada |

O POST ignora caixa, hífens e espaços da chave; exige dez símbolos do alfabeto da TASK-29,
com limite de 64 caracteres de entrada. Formato inválido e campos desconhecidos: 422.
Não recebe IDs de condomínio, unidade ou usuário, perfil, permissões ou estado.
O destino é obtido da chave vigente, mesmo se o token já tiver outro condomínio selecionado.
Condomínio e unidade precisam estar ativos. Inexistente, revogada, regenerada ou indisponível
produzem o mesmo 404 genérico e contam como erro. ADM, Administração e contas compartilhadas
sem tipo Morador recebem 403; identidade inválida/inativa recebe 401.

Uma pessoa pode ter várias unidades no mesmo condomínio e em condomínios diferentes.
Duplicação ativa retorna 409 `ja_vinculado`. Um vínculo global existente de outro perfil,
ativo ou inativo, retorna 409 `perfil_incompativel`, sem conversão. O vínculo global de
Morador é reutilizado e pode ser reativado ao criar uma nova associação após desvinculação.
A associação histórica não é sobrescrita. A chave não é consumida/revogada pelo uso.
Não há novo JWT na resposta: o frontend mantém o fluxo `selecionar-condominio` existente.

## Transações e concorrência

A transação de sucesso cria/reutiliza `VinculoCondominio`, cria `MoradorUnidade` ativo com
origem `chave`, inicializa as sete abas, grava tentativa bem-sucedida e registra auditoria.
Um único commit confirma todos os efeitos; qualquer falha reverte também o reset dos erros.
As constraints existentes de vínculo global e associação ativa permanecem inalteradas.

O bloqueio de conta (`FOR NO KEY UPDATE`) serializa tentativas e vínculos do mesmo usuário,
inclusive para unidades diferentes. Após localizar a chave, a transação mantém leitura
compartilhada do condomínio e `FOR UPDATE` na unidade. A vigência da chave é consultada
novamente depois desse bloqueio, o mesmo usado pela regeneração/revogação na TASK-29.
Assim, uso e substituição são serializados: se o uso confirma primeiro, o vínculo é válido;
se a substituição confirma primeiro, a chave antiga é recusada.

A contagem dos moradores ativos e a criação das permissões acontecem sob o bloqueio da
unidade. O primeiro ativo recebe todas as sete abas; os seguintes recebem todas, exceto
`usuarios`. Usa `RepositorioPermissoes.definir` e as constantes existentes da TASK-21;
não altera a edição de permissões nem a trava do último com acesso à aba Usuários.

## Tentativas persistentes

O limite usa somente `TentativaChaveAcesso` e o índice existentes. Não usa cache/contador
paralelo: o limiter de login é em memória e não atende à persistência exigida por esta task.
Cinco erros consecutivos dentro de quinze minutos bloqueiam por quinze minutos a partir
do quinto. Os cinco erros respondem 404; novas tentativas durante o bloqueio respondem 429
com `Retry-After` em segundos, antes de qualquer consulta de chave.

404 e 429 gravam `sucesso=false` e confirmam essa escrita antes de lançar o erro HTTP.
O rollback da dependência não apaga os registros. Pedidos bloqueados ficam no histórico,
mas não renovam o prazo nem contam como novas avaliações de chave. O estado é reconstruído
desde o último sucesso, ignorando essas avaliações bloqueadas; sucesso reinicia a sequência.
Formato inválido (422) e conflitos de vínculo (409) não contam como chave incorreta nem
reiniciam a sequência. Timestamps são ordenados sob a tranca da conta, com incremento mínimo
de um microssegundo em caso de relógio igual, para preservar a ordem de erros e sucessos.

## Autenticação, consultas e dados pessoais

`GET /auth/me` e a autorização por unidade passam a obter todas as unidades ativas de
`moradores_unidade`. O campo legado `vinculos_condominio.unidade_id` permanece no banco,
sem leitura na autenticação/autorização nem preenchimento no novo fluxo. Não há fallback
para ele, duplicação de associações ou alteração de claims/formatos JWT.

O seletor de `/auth/me` inclui unidades vinculadas ativas independentemente da aba Unidades;
`/minhas-unidades` filtra também essa aba. Alterar associação/permissão vale na próxima
requisição. Sem unidades disponíveis, a listagem retorna `items=[]`, `total=0`.
Os repositórios de consulta herdam o isolamento por condomínio e filtram também o usuário.

O proprietário público contém apenas nome, e-mails, WhatsApps, telefone e referência à foto;
CPF/CNPJ e códigos de chave não fazem parte dos schemas de saída. O download da foto usa o
storage atual e exige associação à unidade e aba Unidades. Não há nova API de upload.

## Auditoria e diferenças do card

O sucesso usa o evento já previsto `vinculo.aprovar`, indicando a autorização imediata pela
chave (`origem=chave`), com conta, perfil Morador, condomínio, recurso, data/hora e IP.
Não representa aprovação administrativa. Falhas e bloqueios usam `seguranca.chave_invalida`
via `registrar_evento_seguranca`, com transação independente e somente o status HTTP.
Nem auditoria nem logs recebem códigos, senhas ou tokens; erros SQL do fluxo são traduzidos
sem parâmetros sensíveis. A falha de auditoria de negócio reverte o vínculo; a auditoria de
segurança preserva o comportamento de melhor esforço da TASK-82, sem apagar as tentativas.

O contrato adotado é **vínculo imediato e ativo por chave válida**. O card menciona solicitação,
fila, aprovação/rejeição administrativa e responsável principal; esses elementos não são
implementados, pois o modelo só prevê `ativo`/`desvinculado`. O primeiro morador recebe as
permissões iniciais, sem nova entidade de responsável. Não há evento de e-mail para esse
fluxo no contrato atual; não são criados notificações, SMTP ou mudanças em `EnvioEmail`.
Convites permanecem fora deste recorte (US-303).

## US-305 — desvinculação segura

`POST /api/v1/unidades/{unidade_id}/moradores/{morador_unidade_id}/desvinculacao`
usa `desvinculacoes_moradores:criar`, sem ampliar permissões genéricas de vínculos.
Administração de condomínio ativo envia `{responsavel_id}` válido; Morador envia `{}`,
com associação e aba Usuários ativas na mesma unidade. Morador não pode informar o
responsável administrativo nem remover a si mesmo. Funcionário e ADM não têm acesso.
Resposta 200: `{id,status,desvinculado_em,chave_revogada}`, com data em UTC.

Altera somente a associação e os efeitos de acesso previstos. Preserva usuário, autores,
permissões e registros operacionais. Sem outra associação em unidade ativa desse condomínio,
desativa o vínculo global; não altera a conta, `sessao_versao` ou outros condomínios.
JWT antigo perde o acesso na próxima requisição. Sem vínculo global, refresh com o `cid`
antigo retorna 401 e seleção desse condomínio, 404; a identidade continua válida.

Se permanecerem associações ativas, exige um gestor efetivo, contado pelo mesmo repository
da US-304: conta e vínculo global ativos, perfil Morador, sem privilégio de plataforma,
associação ativa e aba Usuários habilitada. Violação: 409 `ultimo_usuarios`. Transferência
de aba continua sendo feita por Morador autorizado. Administração pode remover o último
morador e deixar a unidade vazia; um novo primeiro vínculo recebe as sete abas da US-301.

Revoga a chave vigente automaticamente, sem criar/expor outra; ausência de chave não impede
a operação. Depois, a Administração usa `POST /api/v1/unidades/{id}/chave`, não regeneração,
e fornece a nova chave somente a pessoas legitimamente autorizadas. Moradores restantes
mantêm acesso. Repetição legítima: 409 `ja_desvinculado`; recurso alheio/inexistente: 404;
perfil/aba negados: 403; unidade inativa para Administração: 409 `unidade_inativa`.

Ordem de travas: conta do alvo SHARE, condomínio SHARE, responsável SHARE (Administração),
unidade UPDATE, associação/vínculo. Compatível com vínculo por chave, US-210, estrutura,
chaves e permissões. Após a espera, reconsulta autorização e contagens e recarrega entidades;
não trava a conta do executor em ordem inversa nas remoções mútuas. A única transação inclui
um evento `vinculo.desfazer`, com efeito no vínculo global e ID/indicador da chave revogada,
sem código nem evento duplicado `chave.revogar`. SHARE na conta é compatível com as leituras
de destinatários da portaria, evitando inversão conta/unidade com o recebimento de encomendas.
Conflita com NO KEY UPDATE da vinculação; desvínculos paralelos do mesmo usuário decidem
o vínculo global e contam as demais associações sob a trava desse vínculo. Falhas revertem todos os efeitos.

Sem nova migration; permanece `20261124_0009`. Estados legados com unidade ocupada sem gestor
ou associação sem vínculo global de perfil Morador exigem regularização explícita; não há
permissão administrativa nova para corrigir abas nem reativação silenciosa. A US-303 segue
pendente e a TASK-58 inteira não está concluída. O ajuste da matriz aguarda revisão técnica
de Gabriel no PR. Testes: [US-305](../../../tests/us305/).

A regressão de [históricos](../../../tests/us305/test_historicos.py) também verifica os
fluxos integrados de encomendas filtradas/relatório, reservas, bloqueios e comentários/
reabertura de ocorrências. O mesmo JWT mantém a outra unidade legítima, mas perde o
acesso à unidade removida e aos arquivos exclusivos dela, inclusive quando foi o autor.
O bloqueio administrativo ainda pode cancelar a reserva histórica e enfileirar o evento
existente; isso não implementa processamento ou envio SMTP.

## Testes

[Vínculo/rollback](../../../tests/task30/test_vinculos.py),
[tentativas](../../../tests/task30/test_tentativas.py),
[consultas/autenticação/storage](../../../tests/task30/test_consultas.py) e
[concorrência/durabilidade](../../../tests/task30/test_concorrencia.py) reutilizam as fixtures
existentes e o PostgreSQL exclusivo do worktree. A concorrência usa sessões e transações
reais, barreiras/eventos sem sleeps e limpeza somente dos UUIDs criados pelos testes.
