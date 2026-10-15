FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml requirements.lock ./
COPY browsergrid ./browsergrid
COPY cli ./cli
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock && pip install --no-deps --prefix=/install . \
    && pip install --no-cache-dir --upgrade --prefix=/install 'msgpack>=1.2.1' 'urllib3>=2.8.0' 'setuptools>=78.1.1'
FROM python:3.13-slim
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --upgrade 'msgpack>=1.2.1' 'urllib3>=2.8.0' 'setuptools>=78.1.1' \
    && python -m pip check
RUN useradd --uid 10001 --create-home browsergrid
COPY --from=build /install /usr/local
WORKDIR /app
COPY alembic.ini ./
COPY packages/db/migrations ./packages/db/migrations
COPY infra/scripts/init.py ./init.py
USER browsergrid
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn","browsergrid.api.app:app","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
