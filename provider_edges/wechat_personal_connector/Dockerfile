FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "flask==3.1.3" \
    "gunicorn==23.0.0" \
    "httpx>=0.27.0" \
    "qrcode[pil]>=8.0"

COPY provider_edges /app/provider_edges

ENV PYTHONPATH=/app
ENV WECHAT_CONNECTOR_STATE_PATH=/data/wechat_personal_state.json

CMD ["gunicorn", "provider_edges.wechat_personal_connector.app:app", "--bind", "0.0.0.0:8095", "--workers", "1", "--threads", "4", "--timeout", "90"]
