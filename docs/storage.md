# Armazenamento — TASK-26

Serviço interno implementado. A tabela `arquivos` existe desde a migração `20261103_0003`
(TASK-81); a autorização central já está disponível, mas ainda falta integrar e publicar as rotas HTTP. Não existem endpoints de arquivos nesta
entrega; contexto e política abaixo são contratos internos, não autenticação.

## Ambiente local — TASK-2

Na primeira execução, copie `.env.example` para `.env` e rode na raiz:

```sh
docker compose up --build
```

Se já existe `.env`, acrescente as variáveis de storage do exemplo sem substituir
seu arquivo. É necessário Docker e Compose v2.24+. O comando prepara PostgreSQL,
MinIO, bucket privado, migrations, API e frontend.

| Serviço | Endereço padrão |
| --- | --- |
| Frontend | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000/api/v1/health |
| S3 | http://127.0.0.1:9000 |
| Console MinIO | http://127.0.0.1:9001 |

`POSTGRES_PORT`, `API_PORT`, `WEB_PORT`, `STORAGE_PORT` e `STORAGE_CONSOLE_PORT`
permitem trocar portas ocupadas/reservadas. Ao trocar a porta S3, ajuste também
`STORAGE_PUBLIC_ENDPOINT`. Ao trocar API/frontend, ajuste `VITE_API_BASE_URL`
e `CORS_ORIGINS` quando necessário. A API acessa S3 internamente por
`http://storage:9000`, mas assina usando o endpoint público e região explícita.
Não trocar o hostname depois de assinar: o host faz parte da assinatura.

O bucket dedicado é criado se necessário e sua política pública é removida na
inicialização. As credenciais administrativas locais ficam somente no backend
e no storage; nunca vão para o frontend. As variáveis JWT seguem o módulo auth
da TASK-80; SMTP continua como contrato futuro, ainda não consumido pela aplicação.

O MinIO comunitário é construído da revisão oficial
`7aac2a2c5b7c882e68c1ce017d8256be2feea27f`: sua distribuição passou a ser
somente fonte e o repositório foi arquivado. O primeiro build compila Go e pode
demorar; os seguintes usam cache. Código-fonte, LICENSE e NOTICE estão em
`/usr/share/minio-source/` da imagem. Uma implantação de produção precisa rever
o fornecedor mantido. [Fonte oficial](https://github.com/minio/minio#source-only-distribution).

Os volumes `postgres_data` e `storage_data` sobrevivem a reinícios e a
`docker compose down`. **`down --volumes` apaga os dados**; não usar para atualizar
o ambiente. Para API/frontend locais, subir `db storage storage-init` e seguir
o guia local do README, com o mesmo `.env`.

## Integração para os módulos

```python
settings = get_settings()
storage = StorageService(
    S3Adapter(settings),
    authorize=autorizar_arquivo,
    url_seconds=settings.storage_url_seconds,
)
ctx = StorageContext(contexto_autorizado.condominio_id, contexto_autorizado.usuario_id)
arquivo = storage.upload(ctx, "encomendas", "foto.png", "image/png", upload.file)
# Persistir os metadados (app.modules.storage.models.Arquivo) na transação do módulo.
url = storage.download_url(ctx, arquivo)
storage.remove(ctx, arquivo)
```

Imports: `Settings/get_settings` em `app.core.config`; `StorageService` em
`app.modules.storage.service`; `S3Adapter` em `.s3`; tipos em `.types`.
O exemplo é de integração futura: a política e o contexto autorizado pertencem
ao chamador. Nenhuma rota pode construir contexto de IDs enviados pelo cliente.

A política obrigatória `authorize(ctx, module, action, file)` nega por exceção.
Em upload, `file=None`: ela valida permissão de anexar ao recurso capturado pela
política. Nas outras ações recebe metadados carregados pelo servidor e valida
vínculo, aba/perfil e recurso associado. Ser do mesmo condomínio não basta.
Não existe allow-all padrão. As políticas permissivas dos testes são fixtures,
não exemplos de autorização para uma rota.

`FileMetadata` traz UUID, condomínio, módulo, chave, nome, MIME, tamanho real,
remetente e hora UTC. A chave é `condominio/{uuid}/{modulo}/{uuid}`; nome original
nunca vira caminho. O módulo é transitório e pode ser reconstruído da chave,
não é coluna adicional do DER. O serviço atual exige condomínio; arquivos de
conta/plataforma sem condomínio são integração futura.

Bytes ficam no S3; apenas metadados vão ao banco. Não há transação distribuída.
Se a persistência falhar, o chamador deve compensar removendo **somente o objeto
recém-enviado**, com autorização específica para limpar esse upload ainda não
vinculado. Se a limpeza também falhar, registrar seu ID para reconciliação sem
ocultar a falha original. Remover um arquivo já vinculado exige conferir suas
referências; não apagar registros de negócio por tabela ou por prefixo.

`StorageNotFound` corresponde ao futuro 404; `StorageValidationError` ao 422;
`StorageError` é falha de infraestrutura com mensagem genérica. Não registrar
credenciais, URLs assinadas ou detalhes das exceções internas.

## Políticas de arquivo

| Módulo | Tipos | Limite real |
| --- | --- | --- |
| encomendas, fotos | JPG/JPEG, PNG, WebP | 5 MiB |
| ocorrencias | Imagens acima; MP4 | 5 MiB imagem, 50 MiB vídeo |
| suporte | Imagens acima; PDF | 5 MiB |

PDF em suporte é proposta para revisão por Tude. Extensão/MIME devem concordar;
leitura limitada a limite + 1 byte. Imagens são verificadas e decodificadas, com
teto de 20 milhões de pixels; SVG não é aceito. MP4 tem os boxes do contêiner
verificados; PDF tem assinatura e marcador final verificados. Não há antivírus
nem transcodificação. Downloads usam `Content-Disposition: attachment`.

URLs duram 60 segundos por padrão, configuráveis entre 1 e 300. Um link já emitido
continua sendo uma credencial até expirar, mesmo se a permissão for revogada.

## Banco e testes

A tabela `arquivos` entrou na migração `20261103_0003`, a partir do rascunho desta task:
FK para usuários/condomínios, tamanho positivo, chave única e `UNIQUE (id, condominio_id)`,
alvo das FKs compostas que impedem usar um arquivo de outro condomínio. O model é
`app.modules.storage.models.Arquivo`.

Rodar as checagens usuais do backend: Ruff lint/format, Mypy e pytest. Integração
exige `TEST_DATABASE_URL` em PostgreSQL dedicado e `TEST_STORAGE_ENDPOINT`,
`TEST_STORAGE_PUBLIC_ENDPOINT`, `TEST_STORAGE_ACCESS_KEY`, `TEST_STORAGE_SECRET_KEY`
em MinIO de teste. A suíte S3 cria/remove somente bucket aleatório `teste-*`.
Sem essas variáveis, os testes de integração ficam como skip; isso não é prova
de integração. O CI tem um job específico com MinIO real.

TASK-2 ainda requer primeira execução por outro integrante. TASK-26 só pode ser
fechada após persistência definitiva e teste de acesso cruzado pela API autenticada.
