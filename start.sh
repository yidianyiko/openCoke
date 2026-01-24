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

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 默认参数
MODE="dev"
SKIP_INSTALL=false
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
        --skip-install)
            SKIP_INSTALL=true
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
            echo "  --skip-install         跳过环境检查和安装"
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

# ==========================================
# 环境检查与安装
# ==========================================

# 检查 Python 版本
check_python() {
    info "检查 Python 环境..."
    
    # 查找 Python
    PYTHON_CMD=""
    for cmd in python3.12 python3.11 python3 python; do
        if command -v $cmd &> /dev/null; then
            PYTHON_CMD=$cmd
            break
        fi
    done
    
    if [ -z "$PYTHON_CMD" ]; then
        error "未找到 Python。请安装 Python 3.11 或更高版本"
        echo ""
        echo "安装建议:"
        echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3.12 python3.12-venv"
        echo "  macOS:         brew install python@3.12"
        echo "  或使用 pyenv:  pyenv install 3.12"
        exit 1
    fi
    
    # 检查版本
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
        error "Python 版本过低: $PYTHON_VERSION (需要 >= 3.11)"
        echo ""
        echo "请安装 Python 3.11 或更高版本"
        exit 1
    fi
    
    success "Python $PYTHON_VERSION ($PYTHON_CMD)"
    export PYTHON_CMD
}

# 检查并创建虚拟环境
check_venv() {
    info "检查虚拟环境..."
    
    VENV_VALID=false
    
    # 检查虚拟环境是否存在且完整
    if [ -d ".venv" ] && [ -f ".venv/bin/activate" ] && [ -f ".venv/bin/python" ]; then
        VENV_VALID=true
    fi
    
    if [ "$VENV_VALID" = false ]; then
        if [ -d ".venv" ]; then
            warn "虚拟环境不完整，正在重新创建..."
            rm -rf .venv
        else
            warn "虚拟环境不存在，正在创建..."
        fi
        
        $PYTHON_CMD -m venv .venv
        if [ $? -ne 0 ]; then
            error "创建虚拟环境失败"
            echo ""
            echo "可能的解决方案:"
            echo "  Ubuntu/Debian: sudo apt install python3.12-venv python3.12-full"
            exit 1
        fi
        success "虚拟环境已创建: .venv"
        # 标记需要安装依赖
        export NEED_INSTALL_DEPS=true
    else
        success "虚拟环境已存在: .venv"
    fi
    
    # 激活虚拟环境
    source .venv/bin/activate
    if [ $? -ne 0 ]; then
        error "无法激活虚拟环境"
        exit 1
    fi
}

# 安装 Python 依赖
install_python_deps() {
    info "检查 Python 依赖..."
    
    # 确保使用虚拟环境中的 pip
    VENV_PIP=".venv/bin/pip"
    VENV_PYTHON=".venv/bin/python"
    
    if [ ! -x "$VENV_PIP" ]; then
        error "虚拟环境中的 pip 不存在"
        exit 1
    fi
    
    # 检查核心依赖是否已安装
    MISSING_DEPS=false
    for pkg in pymongo flask agno pydantic; do
        if ! $VENV_PYTHON -c "import $pkg" 2>/dev/null; then
            MISSING_DEPS=true
            break
        fi
    done
    
    if [ "$MISSING_DEPS" = true ] || [ "$NEED_INSTALL_DEPS" = true ]; then
        warn "安装 Python 依赖..."
        $VENV_PIP install --upgrade pip -q
        $VENV_PIP install -r requirements.txt -q
        if [ $? -ne 0 ]; then
            error "依赖安装失败"
            exit 1
        fi
        
        # 安装 agent 特定依赖
        if [ -f "agent/requirements.txt" ]; then
            $VENV_PIP install -r agent/requirements.txt -q
        fi
        
        # 安装本地阿里云 NLS SDK（语音识别）
        if [ -d "alibabacloud-nls-python-sdk-dev" ]; then
            info "安装阿里云 NLS SDK..."
            $VENV_PIP install -e alibabacloud-nls-python-sdk-dev -q
        fi
        
        success "Python 依赖安装完成"
    else
        success "Python 依赖已安装"
    fi
}

# 检查系统依赖
check_system_deps() {
    info "检查系统依赖..."
    
    MISSING_SYSTEM_DEPS=""
    
    # 检查 ffmpeg (音频处理需要)
    if ! command -v ffmpeg &> /dev/null; then
        MISSING_SYSTEM_DEPS="$MISSING_SYSTEM_DEPS ffmpeg"
    fi
    
    if [ -n "$MISSING_SYSTEM_DEPS" ]; then
        warn "缺少系统依赖:$MISSING_SYSTEM_DEPS"
        echo "  请安装缺少的依赖:"
        echo "    Ubuntu/Debian: sudo apt install$MISSING_SYSTEM_DEPS"
        echo "    macOS:         brew install$MISSING_SYSTEM_DEPS"
        echo ""
        echo "  该依赖用于音频处理（语音转换），如不需要可忽略"
    else
        success "系统依赖已安装"
    fi
}

# 检查 MongoDB (生产模式需要)
check_mongodb() {
    if [ "$MODE" = "dev" ]; then
        # 开发模式可以使用远程 MongoDB
        return 0
    fi
    
    info "检查 MongoDB..."
    
    # 检查 mongod 是否运行
    if pgrep -x "mongod" > /dev/null; then
        MONGO_VERSION=$(mongod --version 2>/dev/null | head -1 | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
        success "MongoDB 已运行 (v$MONGO_VERSION)"
        return 0
    fi
    
    # 检查是否可连接到 MongoDB
    if command -v mongosh &> /dev/null; then
        if mongosh --eval "db.runCommand({ping:1})" --quiet 2>/dev/null; then
            success "MongoDB 可连接"
            return 0
        fi
    elif command -v mongo &> /dev/null; then
        if mongo --eval "db.runCommand({ping:1})" --quiet 2>/dev/null; then
            success "MongoDB 可连接"
            return 0
        fi
    fi
    
    # MongoDB 未运行
    warn "MongoDB 未运行或未安装"
    echo "  生产/PM2 模式需要 MongoDB"
    echo ""
    echo "  安装建议 (Ubuntu 22.04+):"
    echo "    # 导入 MongoDB GPG 密钥"
    echo "    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor"
    echo "    # 添加源"
    echo "    echo \"deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse\" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list"
    echo "    # 安装"
    echo "    sudo apt update && sudo apt install -y mongodb-org"
    echo "    # 启动"
    echo "    sudo systemctl start mongod && sudo systemctl enable mongod"
    echo ""
    echo "  或者使用 Docker:"
    echo "    docker run -d -p 27017:27017 --name mongodb mongo:7"
    echo ""
    
    # 不退出，让用户决定是否继续
    read -p "是否继续启动？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
}

# 检查 PM2 (仅 pm2 模式需要)
check_pm2() {
    if [ "$MODE" != "pm2" ]; then
        return 0
    fi
    
    info "检查 PM2..."
    
    if ! command -v pm2 &> /dev/null; then
        warn "PM2 未安装，正在安装..."
        
        # 检查 Node.js
        if ! command -v node &> /dev/null; then
            error "Node.js 未安装。PM2 模式需要 Node.js"
            echo ""
            echo "安装建议:"
            echo "  Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
            echo "  macOS:         brew install node"
            echo "  或使用 nvm:    nvm install 20"
            exit 1
        fi
        
        npm install -g pm2
        if [ $? -ne 0 ]; then
            error "PM2 安装失败"
            echo "请尝试: sudo npm install -g pm2"
            exit 1
        fi
    fi
    
    PM2_VERSION=$(pm2 --version)
    success "PM2 $PM2_VERSION"
}

# 检查配置文件
check_config() {
    info "检查配置文件..."
    
    if [ ! -f "conf/config.json" ]; then
        if [ -f "conf/config.example.json" ]; then
            warn "配置文件不存在，从示例创建..."
            cp conf/config.example.json conf/config.json
            success "已创建 conf/config.json，请根据需要编辑配置"
            echo ""
            echo "  编辑配置: nano conf/config.json"
            echo ""
        else
            error "配置文件和示例配置都不存在"
            exit 1
        fi
    else
        success "配置文件已存在: conf/config.json"
    fi
}

# 创建必要的目录
ensure_directories() {
    info "检查目录结构..."
    
    mkdir -p logs
    mkdir -p agent/runner
    mkdir -p data/labels
    mkdir -p data/metadata
    
    success "目录结构已就绪"
}

# 检查 .env 文件
check_env_file() {
    if [ ! -f ".env" ]; then
        warn ".env 文件不存在"
        echo "  如需配置环境变量，请创建 .env 文件"
        echo "  示例: cp .env.example .env  (如果有)"
    fi
}

# 执行环境检查和安装
run_setup() {
    echo ""
    echo "=========================================="
    echo "环境检查与安装"
    echo "=========================================="
    
    check_python
    check_venv
    check_system_deps
    install_python_deps
    check_mongodb
    check_pm2
    check_config
    ensure_directories
    check_env_file
    
    echo ""
    success "环境准备完成!"
    echo "=========================================="
    echo ""
}

# 首次安装或非跳过模式时执行环境检查
if [ "$SKIP_INSTALL" = false ]; then
    run_setup
else
    info "跳过环境检查 (--skip-install)"
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
fi

# 部署前检查（可选）
if [ "$CHECK_PLATFORM" = true ]; then
    echo ""
    echo "运行部署前检查..."
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
    
    # 检查并更新 ecosystem.config.json 中的路径
    info "检查 PM2 配置..."
    
    # 查找 uvx 路径
    UVX_PATH=$(command -v uvx 2>/dev/null || echo "")
    if [ -z "$UVX_PATH" ]; then
        # 尝试常见位置
        for path in "$HOME/.local/bin/uvx" "$HOME/.cargo/bin/uvx" "/usr/local/bin/uvx"; do
            if [ -x "$path" ]; then
                UVX_PATH="$path"
                break
            fi
        done
    fi
    
    if [ -z "$UVX_PATH" ]; then
        warn "uvx 未安装，正在安装..."
        # 安装 uv (包含 uvx)
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        UVX_PATH="$HOME/.local/bin/uvx"
        
        if [ ! -x "$UVX_PATH" ]; then
            error "uvx 安装失败"
            echo "  请手动安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
    fi
    success "uvx 路径: $UVX_PATH"
    
    # 动态更新 ecosystem.config.json 中的 uvx 路径
    VENV_PYTHON=".venv/bin/python"
    if [ -x "$VENV_PYTHON" ]; then
        $VENV_PYTHON - "$UVX_PATH" <<'PYUPDATE'
import json
import sys

uvx_path = sys.argv[1]

with open("ecosystem.config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 更新 langbot-core 的 script 路径
for app in config.get("apps", []):
    if app.get("name") == "langbot-core":
        old_path = app.get("script", "")
        app["script"] = uvx_path
        if old_path != uvx_path:
            print(f"  更新 langbot-core script: {old_path} -> {uvx_path}")
        break

with open("ecosystem.config.json", "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
PYUPDATE
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
