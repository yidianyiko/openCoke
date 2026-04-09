FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY alibabacloud-nls-python-sdk-dev ./alibabacloud-nls-python-sdk-dev

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY . .

CMD ["python", "agent/runner/agent_runner.py"]
