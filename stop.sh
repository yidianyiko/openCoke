#!/bin/bash

# 停止所有服务脚本 - 支持开发模式和单服务器部署模式

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PID 文件路径
AGENT_PID_FILE="$SCRIPT_DIR/.agent.pid"
ECLOUD_PID_FILE="$SCRIPT_DIR/.ecloud.pid"
LANGBOT_PID_FILE="$SCRIPT_DIR/.langbot.pid"
PID_FILE="$SCRIPT_DIR/.start.pid"
SINGLE_SERVER_PIDS_FILE="$SCRIPT_DIR/.langbot_pids"

echo "=========================================="
echo "停止 Coke Project 所有服务"
echo "=========================================="

STOPPED_ANY=false

# 检测部署模式
if pm2 list 2>/dev/null | grep -q "langbot-core\|coke-agent\|ecloud-input"; then
    echo "检测到 PM2 模式"
    MODE="pm2"
elif [ -f "$SINGLE_SERVER_PIDS_FILE" ]; then
    echo "检测到单服务器部署模式"
    MODE="single_server"
elif [ -f "$AGENT_PID_FILE" ] || [ -f "$ECLOUD_PID_FILE" ] || [ -f "$LANGBOT_PID_FILE" ]; then
    echo "检测到开发模式"
    MODE="dev"
else
    echo "未检测到运行中的服务"
    MODE="none"
fi

# 停止服务的通用函数
stop_process() {
    local name=$1
    local pid=$2
    
    if kill -0 "$pid" 2>/dev/null; then
        echo "停止 $name (PID: $pid)..."
        kill -TERM "$pid" 2>/dev/null
        STOPPED_ANY=true
        
        # 等待进程结束，最多等待 10 秒
        for i in {1..10}; do
            if ! kill -0 "$pid" 2>/dev/null; then
                echo "  $name 已停止"
                return 0
            fi
            sleep 1
        done
        
        # 如果还没停止，强制杀死
        if kill -0 "$pid" 2>/dev/null; then
            echo "  强制停止 $name..."
            kill -9 "$pid" 2>/dev/null
        fi
    else
        echo "$name (PID: $pid) 已停止或不存在"
    fi
}

# 根据模式停止服务
case $MODE in
    pm2)
        # PM2 模式：停止所有 PM2 管理的服务
        echo "停止 PM2 管理的服务..."
        pm2 stop all
        echo "✓ 所有 PM2 服务已停止"
        STOPPED_ANY=true
        
        echo ""
        echo "是否要删除 PM2 服务配置？(y/n)"
        echo "提示: 停止服务不会删除配置，下次可以直接 pm2 restart all"
        echo "     删除后需要重新运行 ./start.sh --mode pm2"
        ;;
        
    single_server)
        # 单服务器模式：从 .langbot_pids 读取
        while IFS= read -r line; do
            if [[ $line =~ PID:\ ([0-9]+) ]]; then
                pid="${BASH_REMATCH[1]}"
                service_name=$(echo "$line" | cut -d':' -f1)
                stop_process "$service_name" "$pid"
            fi
        done < "$SINGLE_SERVER_PIDS_FILE"
        
        # 清理 PID 文件
        rm -f "$SINGLE_SERVER_PIDS_FILE"
        
        # 额外检查：通过进程名停止（以防 PID 文件不准确）
        echo ""
        echo "检查残留进程..."
        pkill -f "gunicorn.*langbot_input" 2>/dev/null && echo "  已停止残留的 LangBot Input Handler" && STOPPED_ANY=true
        pkill -f "langbot_output.py" 2>/dev/null && echo "  已停止残留的 LangBot Output Handler" && STOPPED_ANY=true
        pkill -f "agent_runner.py" 2>/dev/null && echo "  已停止残留的 Agent Runner" && STOPPED_ANY=true
        ;;
        
    dev)
        # 开发模式：从独立的 PID 文件读取
        if [ -f "$AGENT_PID_FILE" ]; then
            AGENT_PID=$(cat "$AGENT_PID_FILE")
            stop_process "Agent" "$AGENT_PID"
            rm -f "$AGENT_PID_FILE"
        fi
        
        if [ -f "$ECLOUD_PID_FILE" ]; then
            ECLOUD_PID=$(cat "$ECLOUD_PID_FILE")
            stop_process "Ecloud" "$ECLOUD_PID"
            rm -f "$ECLOUD_PID_FILE"
        fi
        
        if [ -f "$LANGBOT_PID_FILE" ]; then
            LANGBOT_PID=$(cat "$LANGBOT_PID_FILE")
            stop_process "LangBot" "$LANGBOT_PID"
            rm -f "$LANGBOT_PID_FILE"
        fi
        
        # 清理主 PID 文件
        rm -f "$PID_FILE"
        ;;
        
    none)
        # 没有检测到 PID 文件，尝试通过进程名停止
        echo "尝试通过进程名停止服务..."
        pkill -f "agent_runner.py" 2>/dev/null && echo "  已停止 Agent Runner" && STOPPED_ANY=true
        pkill -f "gunicorn.*ecloud_input" 2>/dev/null && echo "  已停止 Ecloud Input" && STOPPED_ANY=true
        pkill -f "ecloud_output.py" 2>/dev/null && echo "  已停止 Ecloud Output" && STOPPED_ANY=true
        pkill -f "gunicorn.*langbot_input" 2>/dev/null && echo "  已停止 LangBot Input" && STOPPED_ANY=true
        pkill -f "langbot_output.py" 2>/dev/null && echo "  已停止 LangBot Output" && STOPPED_ANY=true
        ;;
esac

echo "=========================================="
if [ "$STOPPED_ANY" = true ]; then
    echo "所有服务已停止"
else
    echo "没有运行中的服务"
fi
echo "=========================================="
