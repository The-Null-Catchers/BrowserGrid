FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml requirements.lock ./
COPY browsergrid ./browsergrid
COPY cli ./cli
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock \
    && /opt/venv/bin/pip install --no-deps . \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade 'msgpack>=1.2.1' 'urllib3>=2.8.0' 'setuptools>=78.1.1' \
    && /opt/venv/bin/pip check
FROM python:3.13-slim
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home browsergrid
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
# pip vendors older copies of several libraries; no package manager is required at runtime.
# Remove only pip and its bundled libraries from the final image, not the application wheels.
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
    /opt/venv/lib/python3.13/site-packages/pip /opt/venv/lib/python3.13/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13 \
    /opt/venv/bin/pip /opt/venv/bin/pip3 /opt/venv/bin/pip3.13
WORKDIR /app
COPY alembic.ini ./
COPY packages/db/migrations ./packages/db/migrations
COPY infra/scripts/init.py ./init.py
USER browsergrid
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn","browsergrid.api.app:app","--host","0.0.0.0","--port","8000","--no-proxy-headers"]
