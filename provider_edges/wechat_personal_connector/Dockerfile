FROM python:3.12-slim

WORKDIR /app

# pilk (WeChat SILK voice -> WAV) ships only as an sdist and compiles a C
# extension, so build tooling is needed at install time and purged afterwards.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && pip install --no-cache-dir \
        "flask==3.1.3" \
        "gunicorn==23.0.0" \
        "httpx>=0.27.0" \
        "qrcode[pil]>=8.0" \
        "cryptography>=43.0" \
        "pilk>=0.2.4" \
    && apt-get purge -y gcc python3-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY provider_edges /app/provider_edges

ENV PYTHONPATH=/app
ENV WECHAT_CONNECTOR_STATE_PATH=/data/wechat_personal_state.json

CMD ["gunicorn", "provider_edges.wechat_personal_connector.app:app", "--bind", "0.0.0.0:8095", "--workers", "1", "--threads", "4", "--timeout", "90"]
