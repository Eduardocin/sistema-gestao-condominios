# Notificações (e-mail assíncrono, US-803)

Contrato: [plataforma.md](../../../../docs/api-contracts/plataforma.md), seção 6.

- **Fila.** `envios_email` (outbox). Cada módulo insere o envio na transação da operação principal; se ela desfaz, o e-mail some junto.
- **Worker.** `worker.py`: laço que a cada `EMAIL_WORKER_INTERVALO_SECONDS` chama `service.processar_pendentes`. Roda na API com `EMAIL_WORKER_ATIVO=true` ou sozinho com `python -m app.modules.notificacoes.worker`. `FOR UPDATE SKIP LOCKED` permite mais de um worker.
- **Envio.** `smtp.py`: `EMAIL_BACKEND=console` (log) ou `smtp` (`SMTP_*`). O corpo vem de `corpo.py`, montado do banco com o `condominio_id` do envio.
- **Falhas.** Até `EMAIL_MAX_TENTATIVAS` (3); depois `falhou`. `ultimo_erro` guarda só o tipo do erro. Recurso inexistente ou evento sem modelo falha de uma vez.
- **Rotas (ADM da plataforma).** `GET /plataforma/envios-email` e `POST /plataforma/envios-email/{id}/reenvio` (202). Recurso da matriz: `envios_email`.
- **Recuperação de senha.** Usa envio direto separado da outbox: o token em texto não pode ser persistido na fila, auditoria ou logs. `POST /contas/recuperacao-senha` registra somente o hash, confirma a transação e agenda o envio direto; ver `contas/service.py`.
- **Provedor SMTP de produção.** Ainda depende da configuração das credenciais e do host do ambiente de implantação.
- **Testes.** `tests/notificacoes/`.
