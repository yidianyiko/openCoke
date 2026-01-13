#!/bin/bash
# 检查所有 LangBot 相关服务状态

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDS_FILE="$PROJECT_ROOT/.langbot_pids"

echo "=== LangBot 单服务器部署状态 ==="
echo ""

# 检查端口占用情况
echo "端口占用情况:"
echo "  5300 (LangBot 核心): $(lsof -ti:5300 | wc -l) 个进程"
echo "  8080 (Coke 主服务): $(lsof -ti:8080 | wc -l) 个进程"
echo "  8081 (LangBot Webhook): $(lsof -ti:8081 | wc -l) 个进程"
echo "  27017 (MongoDB): $(lsof -ti:27017 | wc -l) 个进程"
echo ""

# 检查进程状态
echo "进程状态:"

# MongoDB
if pgrep -f mongod > /dev/null; then
    echo "  ✓ MongoDB: 运行中 (PID: $(pgrep -f mongod))"
else
    echo "  ✗ MongoDB: 未运行"
fi

# LangBot 核心服务
if lsof -ti:5300 > /dev/null; then
    langbot_pid=$(lsof -ti:5300)
    echo "  ✓ LangBot 核心服务: 运行中 (PID: $langbot_pid)"
else
    echo "  ✗ LangBot 核心服务: 未运行 (端口 5300 未被占用)"
fi

# Coke 主服务
if pgrep -f "agent_start.sh" > /dev/null; then
    echo "  ✓ Coke 主服务: 运行中 (PID: $(pgrep -f agent_start.sh))"
else
    echo "  ✗ Coke 主服务: 未运行"
fi

# LangBot Input Handler
if pgrep -f "langbot_input.py" > /dev/null; then
    echo "  ✓ LangBot Input Handler: 运行中 (PID: $(pgrep -f langbot_input.py))"
else
    echo "  ✗ LangBot Input Handler: 未运行"
fi

# LangBot Output Handler
if pgrep -f "langbot_output.py" > /dev/null; then
    echo "  ✓ LangBot Output Handler: 运行中 (PID: $(pgrep -f langbot_output.py))"
else
    echo "  ✗ LangBot Output Handler: 未运行"
fi

echo ""

# 检查服务连通性
echo "服务连通性测试:"

# 测试 LangBot 核心服务
if curl -s http://localhost:5300/healthz > /dev/null 2>&1; then
    echo "  ✓ LangBot 核心服务 (5300): 可访问"
else
    echo "  ✗ LangBot 核心服务 (5300): 不可访问"
fi

# 测试 LangBot Webhook
if curl -s -X POST http://localhost:8081/langbot/webhook -d '{}' > /dev/null 2>&1; then
    echo "  ✓ LangBot Webhook (8081): 可访问"
else
    echo "  ✗ LangBot Webhook (8081): 不可访问"
fi

# 测试 MongoDB
if mongo --eval "db.runCommand('ping')" > /dev/null 2>&1; then
    echo "  ✓ MongoDB (27017): 可访问"
else
    echo "  ✗ MongoDB (27017): 不可访问"
fi

echo ""

# 显示最近的日志
LOG_DIR="$PROJECT_ROOT/logs"
if [ -d "$LOG_DIR" ]; then
    echo "最近日志 (最后 5 行):"
    for log_file in "$LOG_DIR"/*.log; do
        if [ -f "$log_file" ]; then
            echo "  $(basename "$log_file"):"
            tail -n 5 "$log_file" | sed 's/^/    /'
            echo ""
        fi
    done
fi