# Infraestrutura local

O [compose.yaml](../compose.yaml) na raiz executa PostgreSQL 17, MinIO, migrações Alembic, preparação do bucket, API FastAPI e frontend Vite. API e frontend usam seus Dockerfiles em `backend/` e `frontend/`.

O [Dockerfile do MinIO](minio/Dockerfile) constrói o serviço de arquivos a partir do código oficial fixado. Banco e objetos persistem nos volumes definidos no Compose.

Para subir o ambiente completo, configure `.env` a partir de `.env.example` e execute `docker compose up --build` na raiz. O modo com API/frontend locais também está descrito no [README principal](../README.md). Não armazenar dados ou credenciais nesta pasta.
