#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

STOPPED_ANY=false

echo "=========================================="
echo "停止 Coke Project 服务"
echo "=========================================="

if command -v pm2 >/dev/null 2>&1 && pm2 list 2>/dev/null | grep -q "coke-agent"; then
    echo "停止 PM2 管理的服务..."
    pm2 stop all
    STOPPED_ANY=true
fi

if pgrep -f "agent_runner.py" >/dev/null 2>&1; then
    echo "停止本地 worker..."
    pkill -f "agent_runner.py" || true
    STOPPED_ANY=true
fi

if command -v docker >/dev/null 2>&1 && [ -f "$SCRIPT_DIR/docker-compose.prod.yml" ]; then
    if docker compose -f "$SCRIPT_DIR/docker-compose.prod.yml" ps -q >/dev/null 2>&1; then
        echo "停止 Docker Compose 生产栈..."
        docker compose -f "$SCRIPT_DIR/docker-compose.prod.yml" down || true
        STOPPED_ANY=true
    fi
fi

echo "=========================================="
if [ "$STOPPED_ANY" = true ]; then
    echo "服务已停止"
else
    echo "没有检测到运行中的服务"
fi
echo "=========================================="
