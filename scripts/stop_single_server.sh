#!/bin/bash
# 停止所有 LangBot 相关服务

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDS_FILE="$PROJECT_ROOT/.langbot_pids"

echo "=== 停止 LangBot 单服务器部署 ==="

if [ ! -f "$PIDS_FILE" ]; then
    echo "PID 文件不存在: $PIDS_FILE"
    echo "尝试通过进程名停止服务..."
    
    # 通过进程名停止
    pkill -f "gunicorn.*langbot_input|python.*-m gunicorn.*langbot_input" && echo "已停止 LangBot Input Handler"
    pkill -f "langbot_output.py" && echo "已停止 LangBot Output Handler"
    pkill -f "agent_start.sh" && echo "已停止 Coke 主服务"
    
    exit 0
fi

echo "从 PID 文件停止服务: $PIDS_FILE"

while IFS= read -r line; do
    if [[ $line =~ PID:\ ([0-9]+) ]]; then
        pid="${BASH_REMATCH[1]}"
        service_name=$(echo "$line" | cut -d':' -f1)
        
        if kill -0 "$pid" 2>/dev/null; then
            echo "停止 $service_name (PID: $pid)"
            kill "$pid"
            
            # 等待进程结束
            for i in {1..10}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            
            # 强制杀死仍在运行的进程
            if kill -0 "$pid" 2>/dev/null; then
                echo "强制停止 $service_name (PID: $pid)"
                kill -9 "$pid"
            fi
        else
            echo "$service_name (PID: $pid) 已停止"
        fi
    fi
done < "$PIDS_FILE"

# 清理 PID 文件
rm -f "$PIDS_FILE"

echo "所有服务已停止"
