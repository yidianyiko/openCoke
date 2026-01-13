#!/bin/bash
# 单服务器部署脚本 - 启动所有 LangBot 相关服务

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 配置文件
PIDS_FILE="$PROJECT_ROOT/.langbot_pids"
LOG_DIR="$PROJECT_ROOT/logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 清理旧的 PID 文件
> "$PIDS_FILE"

echo "=== 单服务器 LangBot 部署启动 ==="
echo "注意: 请确保 LangBot 核心服务已在端口 5300 运行"

# 1. 启动 MongoDB (如果未运行)
echo "检查 MongoDB 状态..."
if ! pgrep -f mongod > /dev/null; then
    echo "启动 MongoDB..."
    mongod --dbpath /data/db --port 27017 --fork --logpath "$LOG_DIR/mongodb.log"
    echo "MongoDB PID: $(pgrep -f mongod)" >> "$PIDS_FILE"
else
    echo "MongoDB 已运行"
fi

# 2. 检查 LangBot 核心服务
echo "检查 LangBot 核心服务 (端口 5300)..."
if ! curl -s http://localhost:5300/healthz > /dev/null 2>&1; then
    echo "错误: LangBot 核心服务未运行在端口 5300"
    echo "请先启动 LangBot 核心服务，然后重新运行此脚本"
    exit 1
else
    echo "LangBot 核心服务已运行"
fi

# 3. 启动 Coke 主服务
echo "启动 Coke 主服务..."
bash agent/runner/agent_start.sh > "$LOG_DIR/coke_main.log" 2>&1 &
COKE_MAIN_PID=$!
echo "Coke 主服务 PID: $COKE_MAIN_PID" >> "$PIDS_FILE"

# 4. 启动 LangBot Input Handler (Webhook 服务器)
echo "启动 LangBot Input Handler (端口 8081)..."
python -u connector/langbot/langbot_input.py > "$LOG_DIR/langbot_input.log" 2>&1 &
LANGBOT_INPUT_PID=$!
echo "LangBot Input Handler PID: $LANGBOT_INPUT_PID" >> "$PIDS_FILE"

# 5. 启动 LangBot Output Handler (消息发送器)
echo "启动 LangBot Output Handler..."
python -u connector/langbot/langbot_output.py > "$LOG_DIR/langbot_output.log" 2>&1 &
LANGBOT_OUTPUT_PID=$!
echo "LangBot Output Handler PID: $LANGBOT_OUTPUT_PID" >> "$PIDS_FILE"

echo ""
echo "=== 所有服务已启动 ==="
echo "PID 文件: $PIDS_FILE"
echo "日志目录: $LOG_DIR"
echo ""
echo "服务端口分配:"
echo "  - LangBot 核心服务: 5300"
echo "  - Coke 主服务: 8080"
echo "  - LangBot Webhook: 8081"
echo "  - MongoDB: 27017"
echo ""
echo "使用 'bash scripts/stop_single_server.sh' 停止所有服务"
echo "使用 'bash scripts/status_single_server.sh' 查看服务状态"

# 等待用户中断
echo ""
echo "按 Ctrl+C 停止所有服务..."
trap 'bash scripts/stop_single_server.sh; exit' INT
wait