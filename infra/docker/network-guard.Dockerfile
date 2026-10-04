FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends iptables && rm -rf /var/lib/apt/lists/*
COPY browsergrid/network_guard.py /guard.py
ENTRYPOINT ["python", "-B", "/guard.py"]
HEALTHCHECK --interval=3s --timeout=25s --retries=5 CMD python -B /guard.py check
