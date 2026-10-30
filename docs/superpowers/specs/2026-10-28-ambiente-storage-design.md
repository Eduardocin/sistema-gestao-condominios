# TASK-2 e TASK-26 — ambiente e armazenamento

Status: aprovado pelo usuário em 28/10/2026; recorte implementado e validado, com dependências de integração preservadas.
Data: 28/10/2026.

## Objetivo

Permitir que o grupo suba o ambiente com Docker Compose e reutilize um serviço
Python de armazenamento de arquivos compatível com S3, preparando a integração
com a autorização central e as migrations sob responsabilidade de Gabriel e Davi.

## Evidência e restrições

- A main remota está em a994736dddfaac476a0015a954c17404233b7852; os PRs 7 e 8 já entraram.
- Só existem a migração estrutural inicial e os models de usuários, condomínios,
  unidades e vínculos. Não há autenticação, contexto autorizado nem tabela arquivos.
- O checkout tem Dockerfiles e mudanças de Compose/Vite ainda não commitados;
  aproveitar apenas o que for pertinente, preservando os demais arquivos.
- A decisão anterior de manter as dependências do banco com Davi continua válida.
- Os critérios da TASK-2 exigem banco, backend e storage com um comando e uma
  validação por outra pessoa do grupo. Uma execução automatizada local não
  substitui essa validação humana.
- O MinIO comunitário está arquivado e distribuído como fonte. A imagem deve ser
  construída de uma revisão fixa do código oficial, com atribuição/licença incluídas.
  É uma escolha para o ambiente local do projeto; não uma decisão de produção.
  Fonte: https://github.com/minio/minio#source-only-distribution

## Abordagens consideradas

1. **MinIO construído pelo Compose, a partir do código oficial fixado — proposta.**
   Mantém o serviço explicitamente solicitado no Notion, sem cadastro em nuvem.
   O primeiro build demora mais. Os próximos usam o cache do Docker.
2. **Outro serviço S3 compatível.** Pode evitar compilar o MinIO, mas muda a
   ferramenta indicada na TASK-26 e exige nova decisão do grupo.
3. **S3 em nuvem.** Evita manter o servidor local, mas adiciona conta, credenciais,
   conexão externa e possíveis custos; não é necessário para esta entrega.

A proposta preserva o MinIO pedido pelo usuário e usa o SDK Python oficial
por trás de um adaptador pequeno, sem acoplar os demais módulos ao cliente S3.

## Entrega 1 — TASK-2

- Compose com PostgreSQL, migração ativa, API, frontend e MinIO.
- Banco e arquivos em volumes persistentes; serviços de teste usam volumes/projeto
  próprios para não tocar nos dados do desenvolvedor.
- Inicialização idempotente de um bucket privado; sem leitura pública.
- Dependências e health checks para que a API só suba após banco e bucket prontos.
- API acessa o storage pelo hostname interno do Compose. URLs assinadas usam o
  endereço externo configurado, acessível pelo navegador. Não alterar a URL depois
  de assinar, pois o host faz parte da assinatura.
- Portas locais configuráveis e vinculadas a 127.0.0.1.
- .env.example com valores fictícios comentados para banco, storage, frontend e
  pontos de integração de JWT/SMTP; documentar quais ainda não são consumidos.
- Não sobrescrever o .env real. Não colocar credenciais em Dockerfiles, código ou logs.
- README com primeira execução por Docker, verificações, persistência e modo local.
- Sem implementar envio de e-mail ou login nesta entrega.

## Entrega 2 — base da TASK-26

- Módulo storage no backend com configuração, adaptador S3 e serviço reutilizável
  para upload, URL temporária de download e remoção.
- Contexto interno tipado com IDs de condomínio e usuário, fornecido pelo módulo
  chamador. Nenhum endpoint recebe esses IDs do cliente.
- Chaves geradas pelo servidor: condominio/{uuid}/modulo/{uuid}, sem nome original
  ou caminho enviado pelo usuário na chave.
- O upload retorna metadados compatíveis com o DER: ID, condomínio, chave, nome
  original, MIME, bytes e usuário remetente; não grava conteúdo no PostgreSQL.
- Imagens JPG/PNG/WebP até 5 MiB para encomendas e fotos; MP4 até 50 MiB apenas
  para ocorrências. Para suporte, imagens e PDF até 5 MiB, conforme política
  documentada para revisão por Tude. Validar tamanho real, extensão e conteúdo;
  imagens também precisam ser decodificáveis.
- Download e remoção conferem condomínio e exigem autorização explícita do módulo
  sobre o recurso associado. Ser do mesmo condomínio não prova acesso à encomenda,
  ocorrência ou chamado. Sem autorização, não gerar URL nem remover objeto.
- URL de download válida por 60 segundos por padrão, configurável com teto de
  5 minutos. Bucket privado; link temporário não é revogado instantaneamente.
- Não expor rotas HTTP de arquivos enquanto não existir a autorização central.
  Nada de usuário fictício ou cabeçalho manual funcionando como autenticação.
- Preparar o contrato de metadados e um rascunho Alembic fora de versions/ para
  Davi integrar a tabela arquivos na TASK-81, sem duplicar sua criação.
- Documentar integração: o módulo persiste os metadados na própria transação,
  remove o objeto recém-enviado se essa persistência falhar e protege a leitura
  por referência ao recurso. A integração concreta depende da tabela de Davi.
- Não promover o rascunho da portaria nem criar moradores ou funcionários aqui.

## Verificação

- Subida real em projeto Docker dedicado, usando .env.example, sem dados reais.
- Confirmar API saudável, bucket privado, upload/download/remoção e persistência
  depois de reiniciar os serviços sem apagar os volumes.
- Testar URL assinada no endereço externo configurado e recusa de GET anônimo.
- Testes do serviço com dois condomínios, autorização de recurso negada, nome
  malicioso, conteúdo incompatível, tamanho excedido e indisponibilidade do storage.
- Testes de integração usam MinIO real e PostgreSQL dedicado para o rascunho de
  metadados; isso não equivale a validar as migrations futuras da TASK-81.
- Backend: Ruff check, Ruff format --check, Mypy e pytest.
- Frontend: lint, testes e build se os arquivos de Docker/Vite forem incluídos.
- Atualizar a validação de Compose no CI e documentar como rodar os testes S3.
- Revisão final e explicação Codewise após implementação e verificação.

## Critérios de conclusão e dependências

A TASK-2 pode ser entregue tecnicamente após os testes do ambiente; a checagem
por outro integrante continua pendente até acontecer.

A base da TASK-26 pode ser implementada e testada agora. A tarefa completa só
fica concluída após integrar a tabela arquivos e a autorização real, com teste
de acesso cruzado pela API. Não fechar o card com testes apenas do serviço.

## Decisões deixadas à implementação

Nomes dos arquivos/classes, biblioteca de validação de imagens, revisão exata
fixada do MinIO, tratamento tipado dos erros e organização dos testes seguem o
padrão do repositório. Resolver detalhes mantendo escopo e simplicidade do MVP.
