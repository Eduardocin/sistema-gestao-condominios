# Ambiente local: MinIO comunitário compilado de uma revisão oficial fixa.
# Código e licença ficam disponíveis em /usr/share/minio-source/.
FROM golang:1.24-bookworm AS build
ARG MINIO_COMMIT=7aac2a2c5b7c882e68c1ce017d8256be2feea27f
ADD https://codeload.github.com/minio/minio/tar.gz/${MINIO_COMMIT} /tmp/minio-source.tar.gz
RUN mkdir /src && tar -xzf /tmp/minio-source.tar.gz -C /src --strip-components=1
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/minio-source/LICENSE
COPY --from=build /src/NOTICE /usr/share/minio-source/NOTICE
COPY --from=build /tmp/minio-source.tar.gz /usr/share/minio-source/source.tar.gz
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
