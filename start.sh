#!/bin/bash

# 统一启动脚本
# 用法:
#   ./start.sh                     # 直接启动所有服务
#   ./start.sh -w <new_wId>        # 更新 wId 后启动
#   ./start.sh --force-clean       # 强制清理锁后启动
#   ./start.sh -w <new_wId> --force-clean  # 组合使用

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Coke Project 统一启动脚本"
echo "=========================================="

# 解析参数
NEW_WID=""
FORCE_CLEAN=""
CHARACTER="qiaoyun"

while [[ $# -gt 0 ]]; do
    case $1 in
        -w|--wid)
            NEW_WID="$2"
            shift 2
            ;;
        -c|--character)
            CHARACTER="$2"
            shift 2
            ;;
        --force-clean)
            FORCE_CLEAN="--force-clean"
            shift
            ;;
        *)
            echo "未知参数: $1"
            echo "用法: ./start.sh [-w <wId>] [-c <character>] [--force-clean]"
            exit 1
            ;;
    esac
done

# 激活虚拟环境
if [ -d ".venv" ]; then
    echo "激活虚拟环境..."
    source .venv/bin/activate
fi

# 更新 wId（如果指定）
if [ -n "$NEW_WID" ]; then
    echo "更新 ecloud.wId.$CHARACTER = $NEW_WID"
    python3 - "$CHARACTER" "$NEW_WID" <<'PYUPDATE'
import json
import sys

character = sys.argv[1]
new_wid = sys.argv[2]

with open("conf/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

old_wid = config.get("ecloud", {}).get("wId", {}).get(character, "未设置")
config.setdefault("ecloud", {}).setdefault("wId", {})[character] = new_wid

with open("conf/config.json", "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=4)

print(f"  旧值: {old_wid}")
print(f"  新值: {new_wid}")
PYUPDATE
    echo ""
fi

# 显示当前配置
echo "当前 ecloud.wId 配置:"
python3 -c "import json; c=json.load(open('conf/config.json')); print('  ' + json.dumps(c.get('ecloud',{}).get('wId',{}), indent=2).replace('\n','\n  '))"
echo ""

# 启动 agent
echo "=========================================="
echo "启动 Agent 服务..."
echo "=========================================="
bash agent/runner/agent_start.sh $FORCE_CLEAN &
AGENT_PID=$!

# 等待 agent 启动
sleep 3

# 启动 ecloud（在新终端或后台）
echo ""
echo "=========================================="
echo "启动 Ecloud 服务..."
echo "=========================================="
bash connector/ecloud/ecloud_start.sh &
ECLOUD_PID=$!

echo ""
echo "=========================================="
echo "所有服务已启动"
echo "  Agent PID: $AGENT_PID"
echo "  Ecloud PID: $ECLOUD_PID"
echo "=========================================="
echo ""
echo "查看日志:"
echo "  Agent:  tail -f agent/runner/agent.log"
echo "  Ecloud: tail -f connector/ecloud/ecloud.log"
echo ""

# 等待任意进程结束
wait
