#!/bin/bash

# 获取脚本所在目录，自动切换到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Working directory: $(pwd)"

# 设置环境
export env=aliyun

# 从 .env 文件加载环境变量（如果存在）
if [ -f ".env" ]; then
    echo "Loading environment variables from .env"
    set -a
    source .env
    set +a
fi

# 激活虚拟环境（如果存在）
if [ -d ".venv" ]; then
    echo "Activating virtual environment"
    source .venv/bin/activate
fi

# 确保临时目录存在
mkdir -p coke/temp
mkdir -p connector/ecloud

# 停止已有进程
echo "Stopping existing processes..."
pkill -f "gunicorn.*ecloud_input" 2>/dev/null || true
pkill -f "ecloud_input.py" 2>/dev/null || true
pkill -f "ecloud_output.py" 2>/dev/null || true
sleep 1

# 启动服务
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Starting ecloud_input.py with Gunicorn..."
nohup "$PYTHON_BIN" -m gunicorn -w 2 -b 0.0.0.0:8080 --log-level info \
    connector.ecloud.ecloud_input:app > connector/ecloud/ecloud.log 2>&1 &
echo "ecloud_input.py (Gunicorn) PID: $!"

echo "Starting ecloud_output.py..."
nohup "$PYTHON_BIN" -u connector/ecloud/ecloud_output.py >> connector/ecloud/ecloud.log 2>&1 &
echo "ecloud_output.py PID: $!"

echo "Services started. Tailing log..."
tail -f connector/ecloud/ecloud.log
