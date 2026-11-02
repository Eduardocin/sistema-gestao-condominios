# Auditoria

O módulo registra eventos por inserção; não oferece endpoints nem operações de atualização ou
exclusão. A tabela também rejeita `UPDATE`, `DELETE` e `TRUNCATE` por trigger no PostgreSQL. O banco
define a data do evento e valida que perfis compartilhados tenham responsável.

Use a sessão do caso de uso para manter a auditoria na mesma transação:

```python
from app.modules.auditoria import service as audit
from app.modules.auditoria.models import TipoEventoAuditoria

audit.log(session, tipo_evento=TipoEventoAuditoria.LOGIN, recurso="sessao", usuario_id=usuario.id)

audit.log(
    session,
    tipo_evento=TipoEventoAuditoria.MUDANCA_PERMISSAO,
    recurso="vinculo_condominio",
    recurso_id=str(vinculo.id),
    usuario_id=usuario.id,
    perfil=perfil,
    condominio_id=condominio_id,
    dados_antes={"perfil": perfil_anterior},
    dados_depois={"perfil": perfil_novo},
)
```

O serviço faz `flush`, mas não comita: o service do caso de uso mantém a responsabilidade pela
transação. Perfis `funcionario` e `administracao` são identificados automaticamente como contas
compartilhadas; cada chamada de auditoria desses perfis precisa enviar `nome_responsavel`. Para
operações sem perfil disponível, `conta_compartilhada=True` ativa a mesma exigência. O nome é
autodeclarado no MVP, pois não há PIN individual.

Tipos disponíveis: `LOGIN`, `FALHA_LOGIN`, `CRIACAO_CONTA`, `EDICAO_CONTA`, `APROVACAO`,
`REJEICAO`, `MUDANCA_PERMISSAO`, `RESERVA` e `OCORRENCIA`. Falhas sem usuário conhecido podem ser
registradas com `usuario_id=None`. Os fluxos de negócio devem chamar `audit.log(...)` quando forem
implementados.
