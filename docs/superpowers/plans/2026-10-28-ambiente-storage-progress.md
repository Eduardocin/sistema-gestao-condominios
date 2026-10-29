# Ledger — plan: docs/superpowers/plans/2026-10-28-ambiente-storage.md

- Desenho aprovado em 28/10/2026. Execução nesta sessão.
- Base atualizada por fast-forward a a994736; branch codex/ambiente-storage. WIP anterior preservado.
- Ruling: reutilizar checkout atual com branch dedicada — o WIP de Compose/Docker/Vite pertence à entrega aprovada e deve ser aproveitado; não criar novo worktree nem duplicar dependências locais.
- Ruling: aprovação do desenho e pedido expresso de implementação autorizam prosseguir com os detalhes do plano, sem nova rodada de aprovação processual.
- Pre-flight: Task 1 espera bootstrap da Task 2; configuração pode ser preparada primeiro, mas validação de subida só ocorre após a Task 2. Task 3 consome FileMetadata da Task 2 e não ativa migrations de Davi.

- Task 1: ambiente compilado do zero e iniciado no projeto codex-condominios-storage-test. Banco/API/MinIO saudáveis; frontend HTTP 200. Porta 55173 recusada pelo Windows; usar WEB_PORT=15173 validou a configuração alternativa. Outro integrante ainda precisa executar do zero.
- Task 2: testes vermelhos por ausência do módulo/adaptador; serviço, validação, assinatura e integração real ficaram verdes. Assinatura externa por 127.0.0.1 baixada pelo host; leitura anônima retorna 403 e objeto removido retorna 404.
- Task 3: rascunho fora de versions/, com testes de upgrade/downgrade, FK e constraints em schemas dedicados. Migrações ativas passaram em banco storage_migrations_test: upgrade/check/downgrade/upgrade, sem divergência de metadata.
- Ruling: executar testes antigos de CORS com as origens padrão por variável do processo de pytest; o runtime do Compose continua com a porta alternativa. CORS alternativo foi validado por HTTP, sem mudar o comportamento dos testes anteriores.
- Ruling: o protocolo MP4 aceita box final de tamanho zero (até EOF); teste reproduziu recusa de contêiner permitido e passou após correção.
- Ruling: upload com resultado incerto compensa apenas a chave UUID recém-gerada; teste vermelho/verde comprova que o objeto anterior não é removido. Falha da limpeza registra apenas o ID para reconciliação.
- Banco e objeto fictícios sobreviveram ao reinício dos containers; assinatura após reinício funcionou no host.
- Frontend: lint, 8 testes e build/typecheck passaram na imagem nova.
- Revisão independente concluída: nenhum crítico; checksum inválido de PNG corrigido após reprodução na Pillow 13. Teste `test_png_bad_checksum_is_validation_error_before_s3` RED→GREEN, sem envio ao adaptador.
- Ruling: tratar o achado de limpeza do fixture como parte do isolamento/repetibilidade dos testes em banco com volume persistente — rollback e descarte garantidos. `test_storage_draft_fixture_does_not_leave_a_schema` reproduziu o schema residual e passou após correção.
- Final: suíte completa com PostgreSQL e MinIO reais: **80 passaram, sem skips**; Ruff lint/format e Mypy passaram (35 arquivos de fonte checados). Frontend: lint, 8 testes, typecheck/build passaram.
- Final: Ruling: HTTP, autenticação e persistência definitiva continuam com os donos das dependências; não são entregas falsamente concluídas por testes permissivos.
- Final: Ruling: vídeo/PDF têm inspeção estrutural limitada, documentada; não se promete decodificação ou antivírus.
- Final: Ruling: disponibilidade/endurecimento de produção ficam fora do ambiente acadêmico local aprovado; o MinIO comunitário é fonte fixa, arquivado.
- Final: Ruling: WIP anterior da portaria e AGENTS.md permanecem fora do commit. Os cards não serão fechados com as dependências pendentes.
- Ruling: um commit de entrega para as duas etapas acopladas, pois o Compose depende do bootstrap do serviço; evitar um commit intermediário de ambiente não executável.
