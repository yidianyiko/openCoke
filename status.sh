#!/bin/bash

# 查看服务状态脚本 - 支持开发模式和单服务器部署模式

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PID 文件路径
AGENT_PID_FILE="$SCRIPT_DIR/.agent.pid"
ECLOUD_PID_FILE="$SCRIPT_DIR/.ecloud.pid"
LANGBOT_PID_FILE="$SCRIPT_DIR/.langbot.pid"
SINGLE_SERVER_PIDS_FILE="$SCRIPT_DIR/.langbot_pids"

# 解析参数
DETAILED=false
if [ "$1" = "--detailed" ] || [ "$1" = "-d" ]; then
    DETAILED=true
fi

echo "=========================================="
echo "Coke Project 服务状态"
echo "=========================================="

# 检测部署模式
if [ -f "$SINGLE_SERVER_PIDS_FILE" ]; then
    MODE="single_server"
    echo "部署模式: 单服务器部署"
elif [ -f "$AGENT_PID_FILE" ] || [ -f "$ECLOUD_PID_FILE" ] || [ -f "$LANGBOT_PID_FILE" ]; then
    MODE="dev"
    echo "部署模式: 开发模式"
else
    MODE="none"
    echo "部署模式: 未检测到运行中的服务"
fi

echo ""

# 检查服务的通用函数
check_service() {
    local name=$1
    local pid_file=$2
    local log_file=$3
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "✓ $name: 运行中 (PID: $pid)"
            if [ -n "$log_file" ] && [ -f "$log_file" ]; then
                local log_size=$(du -h "$log_file" 2>/dev/null | cut -f1)
                echo "  日志: $log_file ($log_size)"
            fi
            return 0
        else
            echo "✗ $name: 已停止 (PID 文件存在但进程不存在)"
            return 1
        fi
    else
        echo "✗ $name: 未运行 (无 PID 文件)"
        return 1
    fi
}

# 检查进程是否运行
check_process() {
    local name=$1
    local pattern=$2
    
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        local pid=$(pgrep -f "$pattern" | head -1)
        echo "✓ $name: 运行中 (PID: $pid)"
        return 0
    else
        echo "✗ $name: 未运行"
        return 1
    fi
}

# 根据模式检查服务
case $MODE in
    single_server)
        echo "【服务状态】"
        check_process "MongoDB" "mongod"
        check_process "LangBot 核心" "uvx.*langbot"
        check_process "Agent" "agent_runner.py"
        check_process "LangBot Input" "gunicorn.*langbot_input"
        check_process "LangBot Output" "langbot_output.py"
        
        if [ "$DETAILED" = true ]; then
            echo ""
            echo "【端口占用】"
            echo -n "  5300 (LangBot 核心): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:5300 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
            
            echo -n "  8080 (Coke 主服务): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:8080 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
            
            echo -n "  8081 (LangBot Webhook): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:8081 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
            
            echo -n "  27017 (MongoDB): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:27017 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
            
            echo ""
            echo "【服务连通性】"
            echo -n "  LangBot 核心 (5300): "
            if command -v curl >/dev/null 2>&1; then
                curl -s http://localhost:5300/healthz >/dev/null 2>&1 && echo "✓ 可访问" || echo "✗ 不可访问"
            else
                echo "⚠ curl 未安装"
            fi
            
            echo -n "  LangBot Webhook (8081): "
            if command -v curl >/dev/null 2>&1; then
                curl -s -X POST http://localhost:8081/langbot/webhook -d '{}' >/dev/null 2>&1 && echo "✓ 可访问" || echo "✗ 不可访问"
            else
                echo "⚠ curl 未安装"
            fi
        fi
        ;;
        
    dev)
        echo "【服务状态】"
        check_service "Agent" "$AGENT_PID_FILE" "agent/runner/agent.log"
        check_service "Ecloud" "$ECLOUD_PID_FILE" "connector/ecloud/ecloud.log"
        check_service "LangBot" "$LANGBOT_PID_FILE" "connector/langbot/langbot.log"
        
        if [ "$DETAILED" = true ]; then
            echo ""
            echo "【端口占用】"
            echo -n "  8080 (Ecloud): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:8080 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
            
            echo -n "  8081 (LangBot): "
            if command -v lsof >/dev/null 2>&1; then
                lsof -ti:8081 >/dev/null 2>&1 && echo "✓ 占用" || echo "✗ 未占用"
            else
                echo "⚠ lsof 未安装"
            fi
        fi
        ;;
        
    none)
        echo "未检测到运行中的服务"
        echo ""
        echo "尝试检查进程..."
        check_process "Agent" "agent_runner.py"
        check_process "Ecloud Input" "gunicorn.*ecloud_input"
        check_process "Ecloud Output" "ecloud_output.py"
        check_process "LangBot Input" "gunicorn.*langbot_input"
        check_process "LangBot Output" "langbot_output.py"
        ;;
esac

echo "=========================================="
echo ""
echo "快速命令:"
echo "  查看详细状态: ./status.sh --detailed"
echo "  查看日志: tail -f agent/runner/agent.log"
echo "  停止服务: ./stop.sh"
if [ "$MODE" = "dev" ]; then
    echo "  重启服务: ./stop.sh && ./start.sh"
elif [ "$MODE" = "single_server" ]; then
    echo "  重启服务: ./stop.sh && bash scripts/deploy_single_server.sh"
fi
echo "=========================================="
