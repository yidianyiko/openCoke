#!/bin/bash

# 统一启动脚本
# 支持开发模式和生产模式
#
# 用法:
#   ./start.sh                              # 开发模式（默认）
#   ./start.sh --mode prod                  # 生产模式（单服务器部署）
#   ./start.sh --mode pm2                   # PM2 模式
#   ./start.sh --check                      # 启动前检查平台配置
#   ./start.sh -w <new_wId>                 # 更新 wId 后启动
#   ./start.sh --force-clean                # 强制清理锁后启动
#   ./start.sh --mode prod --check          # 组合使用

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 默认参数
MODE="dev"
CHECK_PLATFORM=false
NEW_WID=""
FORCE_CLEAN=""
CHARACTER="qiaoyun"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode|-m)
            MODE="$2"
            shift 2
            ;;
        --check)
            CHECK_PLATFORM=true
            shift
            ;;
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
        --help|-h)
            echo "Coke Project 统一启动脚本"
            echo ""
            echo "用法: ./start.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --mode, -m <mode>      部署模式: dev (默认), prod, pm2"
            echo "  --check                启动前检查 LangBot 平台配置"
            echo "  -w, --wid <wId>        更新 ecloud wId"
            echo "  -c, --character <name> 指定角色名称 (默认: qiaoyun)"
            echo "  --force-clean          强制清理所有锁"
            echo "  --help, -h             显示此帮助信息"
            echo ""
            echo "模式说明:"
            echo "  dev   - 开发模式: 启动 Agent + Ecloud + LangBot 连接器 (nohup)"
            echo "  prod  - 生产模式: 完整部署 (MongoDB + LangBot 核心 + Coke)"
            echo "  pm2   - PM2 模式: 使用 PM2 统一管理所有服务 (推荐)"
            echo ""
            echo "PM2 模式优势:"
            echo "  - 统一管理所有服务 (LangBot + Agent + ecloud + connectors)"
            echo "  - 自动重启崩溃的服务"
            echo "  - 日志管理和轮转"
            echo "  - 支持单独重启某个服务"
            echo "  - 实时监控和状态查看"
            echo ""
            echo "示例:"
            echo "  ./start.sh                    # 开发模式"
            echo "  ./start.sh --mode pm2         # PM2 模式 (推荐)"
            echo "  ./start.sh --check            # 启动前检查配置"
            echo "  ./start.sh -w abc123          # 更新 wId 后启动"
            echo ""
            echo "PM2 管理命令 (启动后):"
            echo "  ./pm2-manager.sh status       # 查看状态"
            echo "  ./pm2-manager.sh restart coke-agent  # 重启单个服务"
            echo "  ./pm2-manager.sh logs         # 查看日志"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 './start.sh --help' 查看帮助"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Coke Project 统一启动脚本"
echo "部署模式: $MODE"
echo "=========================================="

# 部署前检查（可选）
if [ "$CHECK_PLATFORM" = true ]; then
    echo ""
    echo "运行部署前检查..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    python scripts/check_langbot_platform.py
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ 平台配置检查失败，请先修复配置问题"
        echo "提示: 编辑 conf/config.json 配置 langbot.bots"
        exit 1
    fi
    echo "✓ 平台配置检查通过"
    echo ""
fi

# 开发模式启动函数
start_dev_mode() {
    # PID 文件路径
    PID_FILE="$SCRIPT_DIR/.start.pid"
    AGENT_PID_FILE="$SCRIPT_DIR/.agent.pid"
    ECLOUD_PID_FILE="$SCRIPT_DIR/.ecloud.pid"
    LANGBOT_PID_FILE="$SCRIPT_DIR/.langbot.pid"

    # 信号处理函数：优雅关闭所有服务
    cleanup() {
        echo ""
        echo "=========================================="
        echo "接收到终止信号，正在优雅关闭所有服务..."
        echo "=========================================="
        ./stop.sh
        exit 0
    }

    # 注册信号处理
    trap cleanup SIGINT SIGTERM

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

    # 启动 agent（使用 nohup 后台运行）
    echo "=========================================="
    echo "启动 Agent 服务..."
    echo "=========================================="
    nohup bash agent/runner/agent_start.sh $FORCE_CLEAN > logs/agent-startup.log 2>&1 &
    AGENT_PID=$!
    echo $AGENT_PID > "$AGENT_PID_FILE"

    # 等待 agent 启动
    sleep 3

    # 启动 ecloud（使用 nohup 后台运行）
    echo ""
    echo "=========================================="
    echo "启动 Ecloud 服务..."
    echo "=========================================="
    nohup bash connector/ecloud/ecloud_start.sh > logs/ecloud-startup.log 2>&1 &
    ECLOUD_PID=$!
    echo $ECLOUD_PID > "$ECLOUD_PID_FILE"

    # 启动 LangBot（多平台网关，使用 nohup 后台运行）
    if [ -f connector/langbot/langbot_start.sh ]; then
        echo ""
        echo "=========================================="
        echo "启动 LangBot 网关..."
        echo "=========================================="
        nohup bash connector/langbot/langbot_start.sh > logs/langbot-startup.log 2>&1 &
        LANGBOT_PID=$!
        echo $LANGBOT_PID > "$LANGBOT_PID_FILE"
    fi

    # 保存主进程 PID
    echo $$ > "$PID_FILE"

    echo ""
    echo "=========================================="
    echo "所有服务已在后台启动"
    echo "  Agent PID: $AGENT_PID"
    echo "  Ecloud PID: $ECLOUD_PID"
    if [ -n "$LANGBOT_PID" ]; then
        echo "  LangBot PID: $LANGBOT_PID"
    fi
    echo "=========================================="
    echo ""
    echo "查看日志:"
    echo "  Agent:  tail -f agent/runner/agent.log"
    echo "  Ecloud: tail -f connector/ecloud/ecloud.log"
    echo "  LangBot: tail -f connector/langbot/langbot.log"
    echo ""
    echo "查看状态: ./status.sh"
    echo "停止服务: ./stop.sh"
    echo ""
    echo "服务将在后台持续运行，可以安全关闭终端"
    echo "=========================================="
}

# PM2 模式启动函数
start_pm2_mode() {
    echo "启动 PM2 模式（统一管理所有服务）..."
    echo ""
    
    # 激活虚拟环境
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
    
    # 清理过期锁（如果需要）
    if [ -n "$FORCE_CLEAN" ]; then
        echo "清理锁..."
        python3 - <<'PYCLEAN'
import sys
sys.path.append(".")
from dao.lock import MongoDBLockManager
lock_manager = MongoDBLockManager()
result = lock_manager.locks.delete_many({})
print(f"Force cleaned {result.deleted_count} locks")
PYCLEAN
        echo ""
    fi
    
    # 停止旧的非 PM2 进程
    echo "清理旧进程..."
    pkill -f "agent_runner.py" 2>/dev/null || true
    pkill -f "gunicorn.*ecloud_input" 2>/dev/null || true
    pkill -f "ecloud_output.py" 2>/dev/null || true
    pkill -f "gunicorn.*langbot_input" 2>/dev/null || true
    pkill -f "langbot_output.py" 2>/dev/null || true
    sleep 2
    echo ""
    
    # 使用 PM2 启动所有服务
    echo "1. 启动所有服务 (PM2)..."
    pm2 start ecosystem.config.json
    pm2 save
    
    echo ""
    echo "2. 等待 LangBot 核心启动..."
    
    # 检查 LangBot 核心是否启动成功（最多等待 30 秒）
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s http://localhost:5300/healthz > /dev/null 2>&1; then
            echo "✓ LangBot 核心服务已启动"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            echo "❌ LangBot 核心服务未能成功启动（超时 30 秒）"
            echo "请检查 PM2 日志: pm2 logs langbot-core"
            exit 1
        fi
        echo -n "."
        sleep 1
    done
    
    echo ""
    echo "=========================================="
    echo "PM2 模式启动完成"
    echo "=========================================="
    echo ""
    pm2 status
    echo ""
    echo "服务列表:"
    echo "  - langbot-core    (LangBot 核心服务，端口 5300)"
    echo "  - coke-agent      (Agent 服务)"
    echo "  - ecloud-input    (E云管家 webhook，端口 8080)"
    echo "  - ecloud-output   (E云管家消息发送)"
    echo "  - langbot-input   (LangBot webhook，端口 8081)"
    echo "  - langbot-output  (LangBot 消息发送)"
    echo ""
    echo "管理命令:"
    echo "  查看状态:     pm2 status"
    echo "  查看日志:     pm2 logs [service-name]"
    echo "  重启服务:     pm2 restart [service-name]"
    echo "  重启全部:     pm2 restart all"
    echo "  停止服务:     pm2 stop [service-name]"
    echo "  停止全部:     pm2 stop all"
    echo "  删除服务:     pm2 delete [service-name]"
    echo ""
    echo "单独重启某个服务:"
    echo "  pm2 restart langbot-core   # 重启 LangBot 核心"
    echo "  pm2 restart coke-agent     # 重启 Agent"
    echo "  pm2 restart ecloud-input   # 重启 ecloud input"
    echo "  pm2 restart ecloud-output  # 重启 ecloud output"
    echo "  pm2 restart langbot-input  # 重启 langbot input"
    echo "  pm2 restart langbot-output # 重启 langbot output"
    echo ""
    echo "查看实时日志:"
    echo "  pm2 logs --lines 100       # 所有服务"
    echo "  pm2 logs coke-agent        # 单个服务"
    echo "=========================================="
}

# 生产模式启动函数
start_prod_mode() {
    PIDS_FILE="$SCRIPT_DIR/.langbot_pids"
    LOG_DIR="$SCRIPT_DIR/logs"
    
    # 创建日志目录
    mkdir -p "$LOG_DIR"
    
    # 清理旧的 PID 文件
    > "$PIDS_FILE"
    
    echo "=== 单服务器生产部署 ==="
    
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
        echo ""
        echo "提示: 使用以下命令启动 LangBot 核心："
        echo "  cd langbot-workdir && uvx langbot@latest"
        echo "  或"
        echo "  ./start.sh --mode pm2"
        exit 1
    else
        echo "LangBot 核心服务已运行"
    fi
    
    # 3. 启动 Coke 主服务 (Agent)
    echo "启动 Coke 主服务 (Agent)..."
    bash agent/runner/agent_start.sh $FORCE_CLEAN > "$LOG_DIR/coke_main.log" 2>&1 &
    COKE_MAIN_PID=$!
    echo "Coke 主服务 PID: $COKE_MAIN_PID" >> "$PIDS_FILE"
    
    # 4. 启动 LangBot 连接器 (Input + Output)
    echo "启动 LangBot 连接器..."
    bash connector/langbot/langbot_start.sh > "$LOG_DIR/langbot.log" 2>&1 &
    LANGBOT_PID=$!
    echo "LangBot 连接器 PID: $LANGBOT_PID" >> "$PIDS_FILE"
    
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
    echo "使用 './stop.sh' 停止所有服务"
    echo "使用 './status.sh --detailed' 查看服务状态"
    
    # 等待用户中断
    echo ""
    echo "按 Ctrl+C 停止所有服务..."
    trap './stop.sh; exit' INT
    wait
}

# 根据模式启动
case $MODE in
    dev)
        # 开发模式：启动 Agent + Ecloud + LangBot 连接器
        start_dev_mode
        ;;
    prod|production)
        # 生产模式：完整部署
        start_prod_mode
        ;;
    pm2)
        # PM2 模式：使用 PM2 管理服务
        start_pm2_mode
        ;;
    *)
        echo "错误: 未知模式 '$MODE'"
        echo "支持的模式: dev, prod, pm2"
        echo "使用 './start.sh --help' 查看帮助"
        exit 1
        ;;
esac
