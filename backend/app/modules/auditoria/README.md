# Auditoria — TASK-82 e TASK-49 / US-1004 e US-903

Serviço central de inserção em `registros_auditoria`, usando o esquema oficial já existente.
A migration 0003 impede UPDATE, DELETE e TRUNCATE; esta entrega não altera migrations.
A consulta exclusiva do ADM da plataforma é implementada pela TASK-49, descrita abaixo.

## Interfaces internas

`registrar_acao(session, *, ctx, acao, recurso_tipo, recurso_id, responsavel=None, antes=None,
depois=None)` insere e faz flush **sem commit**. O service chamador confirma a operação e o evento
juntos. A falha de auditoria impede a confirmação da ação. Uma chamada explícita por ação lógica:
não há listeners ORM ou middleware inserindo eventos de sucesso em paralelo.

```python
from app.modules.auditoria import service as auditoria
from app.modules.auditoria.schemas import ContextoAuditoria, ResponsavelRef

auditoria.registrar_acao(
    session,
    ctx=ContextoAuditoria.do_condominio(contexto, ip=ip),
    acao="funcionario.cadastrar",
    recurso_tipo="funcionario",
    recurso_id=funcionario.id,
    responsavel=ResponsavelRef("administracao", responsavel_id),
    antes={},
    depois={"nome": funcionario.nome, "ativo": True},
)
# O commit continua pertencendo ao service de negócio.
```

O contexto é interno, formado por identidade e vínculo validados. Nunca construir contexto com
campos de um payload HTTP. O responsável é consultado no mesmo condomínio, deve estar ativo e
ter o tipo correspondente ao perfil; seu nome é copiado para preservar o histórico. Ausente:
422; inexistente, inativo ou de outro condomínio: 404. A gestão da própria lista de responsáveis
é a exceção da seção 5.2 do contrato: registra a conta autenticada sem exigir responsável.
`seguranca.login` também identifica a conta, antes da seleção de pessoa na conta compartilhada.

`registrar_evento_seguranca(*, acao, usuario_id, condominio_id, ip, perfil=None, recurso_tipo=None,
recurso_id=None, detalhe=None)` abre uma sessão independente, confirma e fecha. IDs que não são
visíveis nessa transação ficam nulos, evitando referências inválidas ou espera por dados não
confirmados. Há limites locais de espera por locks (500 ms) e por comando (2 s). Falhas de abertura,
inserção, commit ou rollback não propagam; o log operacional registra somente uma mensagem fixa,
sem SQL, parâmetros ou traceback potencialmente sensíveis. A fábrica pode ser injetada nos testes.

## Integrações

- Permissões: `permissao_aba.alterar`; repetir o mesmo valor não produz evento.
- Pessoas: `responsaveis.alterar`, `funcionario.cadastrar`, `funcionario.desativar`.
- Reservas: `reserva.criar`, `reserva.cancelar`; mantidos os dados e a transação já existentes.
- Login: `seguranca.login`, transacional com eventual rehash; falha ou bloqueio usa sessão própria
  (`seguranca.login_falho`, `seguranca.login_bloqueado`). Nunca grava e-mail digitado ou tokens.
- Autorização: um evento `seguranca.acesso_negado` por resposta 403 autenticada. O middleware captura
  a identidade publicada pelas dependências, o perfil/condomínio verificados e a rota estática.
- `seguranca.acesso_cross_tenant` identifica 404 de recurso em rota com contexto de condomínio
  validado. A descrição é deliberadamente `recurso_fora_do_escopo_ou_inexistente`: não consulta outro
  tenant nem afirma que o recurso exista. URL desconhecida não gera esse evento. Não registra
  parâmetros de URL/query, corpo ou cabeçalhos de autenticação.

O IP vem da conexão ASGI e é validado como IPv4/IPv6; cabeçalhos Forwarded/X-Forwarded-For não são
interpretados pela auditoria. Uma instalação com proxy deve configurar quais proxies o servidor
ASGI considera confiáveis. Contextos de requisições concorrentes são isolados e sempre liberados.

## Sanitização

Antes e depois são copiados recursivamente. Senhas, hashes, tokens, autorização, cookies, códigos
de chave, credenciais e URLs de conexão são removidos por nome de campo normalizado, incluindo
estruturas aninhadas, listas e variantes comuns. CPF/CNPJ são mascarados; UUIDs e datas são
convertidos sem usar repr de objetos. Ciclos/profundidade excessiva e objetos desconhecidos são
omitidos. Os chamadores devem enviar somente as alterações necessárias: o mecanismo não pode
identificar um segredo arbitrário inserido dentro de um campo de texto livre.

## Verificação e limites

[Testes específicos](../../../tests/auditoria/) cobrem dados, sanitização, responsáveis, rollback,
segurança persistida, concorrência de contexto, indisponibilidade e imutabilidade. As regressões
existentes de permissões, funcionários, autenticação e reservas continuam obrigatórias.

O trigger protege as operações normais. O papel da aplicação em produção não deve ter poderes de
superusuário, DDL ou desativação de triggers; o papel privilegiado usado na limpeza dos testes é
exclusivo de banco descartável. Eventos de segurança são best effort conforme o contrato: falha
no banco é observável no log, mas não substitui o erro HTTP original.

Ocorrências aguardam a TASK-40; aprovação, chaves e vínculos aguardam as respectivas tasks.
Avisos não fazem parte deste módulo; a consulta HTTP abaixo é a entrega da TASK-49.

## Consulta da plataforma — TASK-49 / US-903

`GET /api/v1/plataforma/auditoria` exige `require_platform_permission("auditoria:ver")`.
Sem identidade válida: 401; Morador, Funcionário e Administração: 403. O filtro por condomínio é
aceito nesta rota de plataforma e não constitui contexto de autorização para outros módulos.
Não existem operações HTTP de escrita ou exclusão da trilha.

Filtros opcionais: `condominio_id`, `usuario_id`, `de`, `ate`, `acao`, `recurso_tipo`, `recurso_id`.
Ação é exata (`reserva.cancelar`) ou prefixo terminado por ponto (`reserva.`); `_` é literal.
Datas `AAAA-MM-DD` incluem todo o dia no fuso `America/Sao_Paulo`, com limite superior exclusivo
no início do dia seguinte. Período invertido retorna 422. Sem `condominio_id`, a consulta inclui
todos os condomínios e eventos globais; sem usuário/condomínio, as referências da resposta são nulas.

Resposta: `{"items": [...], "page_size": 20, "next_cursor": null}`. Cada item contém `id`, `acao`,
`criado_em`, `usuario` e `condominio` (somente ID/nome), `responsavel_nome`, `perfil`, `recurso_tipo`,
`recurso_id`, `antes`, `depois` e `ip`. Antes/depois passam novamente pela sanitização para proteger
registros legados, sem tentar alterá-los. Máscaras já seguras são preservadas.

### Cursor

Ordem fixa: `criado_em DESC, id DESC`. `page_size` aceita 1 a 100, padrão 20. A consulta busca apenas
`page_size + 1` linhas, sem OFFSET nem contagem total. Se houver continuação, o cursor representa
a última linha devolvida: JSON `{"criado_em":"2026-11-17T12:00:00Z","id":1021}` codificado em
base64url UTF-8 sem padding. Ele não contém credenciais nem concede acesso: a autorização do ADM
é conferida em cada pedido. Não tem assinatura e pode representar qualquer posição válida.

O cliente reapresenta `cursor` mantendo os mesmos filtros. Só entram tuplas `(criado_em,id)` menores
que a posição, inclusive quando vários eventos têm o mesmo horário. `next_cursor=null` encerra a
leitura. Cursor malformado, data sem fuso, ID inválido ou campos extras retornam 422 no envelope
padrão. A navegação não é snapshot: inserções mais recentes aparecem ao reiniciar a consulta;
eventos inseridos posteriormente com data anterior ao cursor podem aparecer na continuação.

### Evidência de desempenho

Teste reproduzível: [test_desempenho.py](../../../tests/auditoria/test_desempenho.py).
Em 17/11/2026: Windows, Python 3.13.17, PostgreSQL 17.12 em Docker exclusivo, conexão local,
100.000 eventos sintéticos além de 1.007 registros presentes na transação, cache aquecido,
uma execução de aquecimento e 20 amostras por cenário, páginas de 100 itens. A medição inclui
TestClient HTTP/ASGI, autenticação real, PostgreSQL, sanitização e serialização; não inclui rede
HTTP externa. Logs operacionais estavam silenciados. Orçamento do teste local: p95 < 1 segundo.

| Cenário | p50 HTTP/ASGI (ms) | p95 HTTP/ASGI (ms) | SQL no EXPLAIN (ms) |
| --- | ---: | ---: | ---: |
| Sem filtros | 14,118 | 20,127 | 0,277 |
| Condomínio | 14,531 | 20,564 | 0,199 |
| Usuário | 14,794 | 19,947 | 0,304 |
| Ação rara (100 ocorrências em 100 mil) | 29,337 | 34,906 | 9,743 |
| Filtros combinados | 16,989 | 23,833 | 0,208 |
| Cursor após 90 mil eventos | 14,864 | 20,337 | 0,234 |

`EXPLAIN (ANALYZE, BUFFERS)` mostrou `ix_registros_auditoria_criado_em` com `Incremental Sort`
na maioria dos cenários; o filtro raro usou `Seq Scan` e `Sort`, ainda dentro do orçamento.
Não houve necessidade demonstrada de índice ou migration novos. São resultados locais com
amostras limitadas, não uma garantia de latência em produção. A carga sintética fica na transação
revertida da fixture; o teste não apaga eventos existentes ou desativa o trigger para essa carga.
