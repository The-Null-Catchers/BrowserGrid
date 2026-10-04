FROM golang:1.24.8-bookworm AS build
WORKDIR /src
# Official security release RELEASE.2025-10-15T17-29-55Z, pinned to its exact commit.
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
RUN git init . && git remote add origin https://github.com/minio/minio.git \
    && git fetch --depth=1 origin ${MINIO_COMMIT} && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${MINIO_COMMIT}"
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home minio && mkdir /data && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/doc/minio/LICENSE
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
USER 10001:10001
EXPOSE 9000 9001
HEALTHCHECK --interval=5s --timeout=3s --retries=20 CMD curl --fail --silent http://localhost:9000/minio/health/live || exit 1
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
