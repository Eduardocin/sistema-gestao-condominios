# Alinhamento auth/storage antes do PR

- Base remota observada: main a994736. PRs 9, 10 e 11 ainda abertos.
- Combinar PR11 c4da086 na branch codex/ambiente-storage sem alterar main ou o PR11.
- Resolver .env.example, Settings, pyproject e testes preservando as duas funcionalidades.
- Deduplicar o lockfile e adotar JWT_SECRET_KEY/ACCESS_TOKEN_EXPIRE_MINUTES.
- Preservar todos os testes de autenticação e de arquivos; nenhum endpoint de storage é adicionado.
- Atualizar a referência de auth no PR9 sem redefinir os contratos futuros do núcleo.
- Validar Compose, backend completo com PostgreSQL/MinIO reais, migrations e frontend.
- Abrir PR com base feat/login-jwt: o diff é apenas Docker/storage e explicita dependência do PR11.
- Após merge do PR11, retargetar nosso PR para main antes de mesclá-lo. Não mesclar PRs de terceiros neste trabalho.

## Verificações executadas

- 137 testes do backend passaram, sem skips, com PostgreSQL e MinIO reais.
- Ruff lint, Ruff format --check e Mypy passaram na árvore combinada.
- Frontend: lint, 8 testes e build/typecheck passaram.
- Migrações ativas 0001/0002: upgrade, alembic check, downgrade base e novo upgrade passaram em banco separado de testes.
- Build e subida do Compose integrado passaram. .env real foi preservado.
- Revisão independente do alinhamento: nenhum impeditivo funcional; separação de linhas em test_settings.py corrigida e verificada.
- Contrato do PR9 alinhado à TASK-80 em 33740a8; CI do PR9 passou.

O PR de storage será publicado com base feat/login-jwt e dependência explícita do PR11. Retargetar para main após o merge do login; os cards continuam com as dependências de integração já documentadas.
