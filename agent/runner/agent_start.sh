#!/bin/bash

# 获取脚本所在目录，自动切换到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "Working directory: $(pwd)"

# 设置环境
export env=aliyun

# 细粒度控制后台任务
export DISABLE_DAILY_AGENTS="true"        # 禁用 daily agent
export DISABLE_BACKGROUND_AGENTS="false"  # 启用 background agent（包括提醒功能）
export AGNO_TELEMETRY=false
export AGENT_WORKERS=10

# 从 .env 文件加载环境变量（如果存在）
if [ -f ".env" ]; then
    echo "Loading environment variables from .env"
    set -a
    source .env
    set +a
fi

# 激活虚拟环境（如果存在）
PYTHON_BIN=""
if [ -d ".venv" ]; then
    echo "Activating virtual environment"
    source .venv/bin/activate
    PYTHON_BIN=".venv/bin/python"
fi

# 回退查找 Python
if [ -z "$PYTHON_BIN" ] && [ -n "$VIRTUAL_ENV" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi
if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

echo "Using Python: $PYTHON_BIN"

# 检查依赖
"$PYTHON_BIN" - <<'PYCHECK' >/dev/null 2>&1 || "$PYTHON_BIN" -m pip install -r agent/requirements.txt
import pymongo
PYCHECK

# 确保日志目录存在
mkdir -p agent/runner

# 停止已有进程
echo "Stopping existing agent_runner process..."
pkill -f "agent_runner.py" 2>/dev/null || true
sleep 1

# 清理锁（避免残留锁导致死循环）
# 使用 --force-clean 参数可以清理所有锁（包括未过期的）
if [ "$1" = "--force-clean" ]; then
    echo "Force cleaning ALL locks..."
    "$PYTHON_BIN" - <<'PYCLEAN'
import sys
sys.path.append(".")
from dao.lock import MongoDBLockManager
lock_manager = MongoDBLockManager()
result = lock_manager.locks.delete_many({})
print(f"Force cleaned {result.deleted_count} locks")
PYCLEAN
else
    echo "Cleaning up expired locks..."
    "$PYTHON_BIN" - <<'PYCLEAN'
import sys
sys.path.append(".")
from dao.lock import MongoDBLockManager
from datetime import datetime
lock_manager = MongoDBLockManager()
result = lock_manager.locks.delete_many({"expires_at": {"$lt": datetime.utcnow()}})
print(f"Cleaned {result.deleted_count} expired locks")
PYCLEAN
fi

# 后台运行
echo "Starting agent_runner.py in background..."
nohup "$PYTHON_BIN" agent/runner/agent_runner.py > agent/runner/agent.log 2>&1 &
echo "agent_runner.py PID: $!"

echo "Service started. Tailing log..."
tail -f agent/runner/agent.log