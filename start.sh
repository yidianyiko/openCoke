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

# 加载 .env 环境变量
source_env() {
    if [ -f "$SCRIPT_DIR/.env" ]; then
        set -a
        source "$SCRIPT_DIR/.env"
        set +a
    fi
}

# 检查 WhatsApp Evolution API 配置状态
check_whatsapp_setup() {
    info "检查 WhatsApp Evolution API 配置..."

    # 读取配置
    WHATSAPP_ENABLED=$(.venv/bin/python3 -c "
import json
import sys
sys.path.insert(0, '.')
try:
    with open('conf/config.json', 'r') as f:
        config = json.load(f)
    whatsapp = config.get('whatsapp', {})
    print('yes' if whatsapp.get('enabled', False) else 'no')
except:
    print('error')
" 2>/dev/null || echo "error")

    if [ "$WHATSAPP_ENABLED" = "no" ] || [ "$WHATSAPP_ENABLED" = "error" ]; then
        echo ""
        echo "=========================================="
        echo "📱 WhatsApp 未启用"
        echo "=========================================="
        echo ""
        echo "如需启用 WhatsApp，请按以下步骤操作："
        echo ""
        echo "1️⃣  配置环境变量 (.env 文件):"
        echo "   WHATSAPP_EVOLUTION_API_BASE=http://localhost:8082"
        echo "   WHATSAPP_EVOLUTION_API_KEY=<your-api-key>"
        echo "   WHATSAPP_EVOLUTION_INSTANCE=coke"
        echo "   WHATSAPP_EVOLUTION_WEBHOOK_URL=http://YOUR_SERVER_IP:8081/webhook/whatsapp"
        echo ""
        echo "2️⃣  启动 Evolution API:"
        echo "   ./start.sh --start-evolution"
        echo ""
        echo "3️⃣  启用 WhatsApp (conf/config.json):"
        echo '   "whatsapp": {"enabled": true, ...}'
        echo ""
        echo "4️⃣  重启服务:"
        echo "   ./start.sh --mode pm2"
        echo ""
        echo "=========================================="
        return 0
    fi

    # WhatsApp 已启用，检查 Evolution API 配置
    API_BASE=$(.venv/bin/python3 -c "
import json
import os
with open('conf/config.json', 'r') as f:
    config = json.load(f)
evolution = config.get('whatsapp', {}).get('evolution', {})
api_base = evolution.get('api_base', '')
# 解析环境变量
if api_base.startswith('\${') and api_base.endswith('}'):
    env_var = api_base[2:-1].split(':')[0]
    default = api_base[2:-1].split(':')[1] if ':' in api_base[2:-1] else ''
    api_base = os.environ.get(env_var, default)
elif api_base.startswith('\$'):
    api_base = os.environ.get(api_key[1:], '')
print(api_base)
" 2>/dev/null || echo "")

    API_KEY=$(.venv/bin/python3 -c "
import json
import os
with open('conf/config.json', 'r') as f:
    config = json.load(f)
evolution = config.get('whatsapp', {}).get('evolution', {})
api_key = evolution.get('api_key', '')
if api_key.startswith('\${') and api_key.endswith('}'):
    env_var = api_key[2:-1].split(':')[0]
    api_key = os.environ.get(env_var, '')
elif api_key.startswith('\$'):
    api_key = os.environ.get(api_key[1:], '')
print(api_key)
" 2>/dev/null || echo "")

    INSTANCE_NAME=$(.venv/bin/python3 -c "
import json
import os
with open('conf/config.json', 'r') as f:
    config = json.load(f)
evolution = config.get('whatsapp', {}).get('evolution', {})
instance = evolution.get('instance_name', '')
if instance.startswith('\${') and instance.endswith('}'):
    env_var = instance[2:-1].split(':')[0]
    default = instance[2:-1].split(':')[1] if ':' in instance[2:-1] else ''
    instance = os.environ.get(env_var, default)
elif instance.startswith('\$'):
    instance = os.environ.get(instance[1:], '')
print(instance)
" 2>/dev/null || echo "coke")

    echo "   API 地址: ${API_BASE:-未配置}"
    echo "   实例名称: ${INSTANCE_NAME:-coke}"

    # 检查 Evolution API 是否可访问
    if [ -z "$API_BASE" ]; then
        echo ""
        warn "Evolution API 地址未配置"
        echo ""
        echo "请在 .env 文件中配置:"
        echo "  WHATSAPP_EVOLUTION_API_BASE=http://localhost:8082"
        echo "  WHATSAPP_EVOLUTION_API_KEY=<your-api-key>"
        return 0
    fi

    # 检查 Evolution API 服务状态
    EVOLUTION_STATUS=$(curl -s "$API_BASE" 2>/dev/null || echo "")
    if [ -z "$EVOLUTION_STATUS" ]; then
        echo ""
        warn "Evolution API 服务不可访问: $API_BASE"
        echo ""
        echo "请先启动 Evolution API:"
        echo "  ./start.sh --start-evolution"
        echo ""
        return 0
    fi

    success "Evolution API 服务可访问"

    # 检查实例状态
    if [ -n "$INSTANCE_NAME" ] && [ -n "$API_KEY" ]; then
        INSTANCE_STATUS=$(curl -s -H "apikey: $API_KEY" \
            "$API_BASE/instance/connectionState/$INSTANCE_NAME" 2>/dev/null || echo "")

        if echo "$INSTANCE_STATUS" | grep -q '"state":"open"'; then
            success "WhatsApp 实例已连接 ✓"
            echo ""
            echo "=========================================="
            echo "✅ WhatsApp 已就绪"
            echo "=========================================="
            echo ""
            echo "您可以向 WhatsApp 发送消息进行测试！"
            echo ""
        elif echo "$INSTANCE_STATUS" | grep -q '"state":"close"'; then
            warn "WhatsApp 实例未连接"
            echo ""
            echo "请执行以下步骤完成连接："
            echo ""
            echo "1. 检查 Evolution API 日志获取二维码:"
            echo "   docker logs evolution_api -f"
            echo ""
            echo "2. 使用手机 WhatsApp 扫描二维码登录"
            echo ""
            echo "3. 扫码后，实例将自动连接"
            echo ""
            echo "4. 验证连接状态:"
            echo "   curl -H \"apikey: \$WHATSAPP_EVOLUTION_API_KEY\" \\"
            echo "        $API_BASE/instance/connectionState/$INSTANCE_NAME"
            echo ""
        elif echo "$INSTANCE_STATUS" | grep -q "instance not found"; then
            warn "WhatsApp 实例不存在"
            echo ""
            echo "请创建实例:"
            echo "  curl -X POST \"$API_BASE/instance/create\" \\"
            echo "    -H \"apikey: \$WHATSAPP_EVOLUTION_API_KEY\" \\"
            echo "    -H \"Content-Type: application/json\" \\"
            echo "    -d '{"
            echo "      \"instanceName\": \"$INSTANCE_NAME\","
            echo "      \"qrcode\": true,"
            echo "      \"integration\": \"WHATSAPP-BAILEYS\""
            echo "    }'"
            echo ""
            echo "然后查看日志获取二维码:"
            echo "  docker logs evolution_api -f"
            echo ""
            echo "使用手机 WhatsApp 扫描二维码登录"
            echo ""
        else
            warn "无法检查实例状态"
            echo "  响应: $INSTANCE_STATUS"
        fi
    else
        warn "API Key 或实例名称未配置"
        echo ""
        echo "请在 .env 文件中配置:"
        echo "  WHATSAPP_EVOLUTION_API_KEY=your-secret-key"
        echo "  WHATSAPP_EVOLUTION_INSTANCE=coke"
    fi

    echo "=========================================="
    echo ""
}

# 默认参数
MODE="dev"
SKIP_INSTALL=false
CHECK_PLATFORM=false
CHECK_WHATSAPP=false
START_EVOLUTION=false
STOP_EVOLUTION=false
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
        --check-whatsapp)
            CHECK_WHATSAPP=true
            SKIP_INSTALL=true  # 自动跳过环境检查
            shift
            ;;
        --start-evolution)
            START_EVOLUTION=true
            SKIP_INSTALL=true
            shift
            ;;
        --stop-evolution)
            STOP_EVOLUTION=true
            SKIP_INSTALL=true
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
            echo "  --check-whatsapp      检查 WhatsApp Evolution API 配置状态"
            echo "  --start-evolution     启动 Evolution API (WhatsApp Gateway)"
            echo "  --stop-evolution      停止 Evolution API (WhatsApp Gateway)"
            echo "  -w, --wid <wId>        更新 ecloud wId"
            echo "  -c, --character <name> 指定角色名称 (默认: qiaoyun)"
            echo "  --force-clean          强制清理所有锁"
            echo "  --skip-install         跳过环境检查和安装"
            echo "  --help, -h             显示此帮助信息"
            echo ""
            echo "模式说明:"
            echo "  dev   - 开发模式: 启动 Agent + Ecloud 连接器 (nohup)"
            echo "  prod  - 生产模式: 完整部署 (MongoDB + LangBot 核心 + Coke)"
            echo "  pm2   - PM2 模式: 使用 PM2 统一管理所有服务 (推荐)"
            echo ""
            echo "PM2 模式优势:"
            echo "  - 统一管理所有服务 (Agent + ecloud connectors)"
            echo "  - 自动重启崩溃的服务"
            echo "  - 日志管理和轮转"
            echo "  - 支持单独重启某个服务"
            echo "  - 实时监控和状态查看"
            echo ""
            echo "示例:"
            echo "  ./start.sh                    # 开发模式"
            echo "  ./start.sh --mode pm2         # PM2 模式 (推荐)"
            echo "  ./start.sh --check            # 启动前检查配置"
            echo "  ./start.sh --check-whatsapp   # 检查 WhatsApp 配置"
            echo "  ./start.sh --start-evolution  # 启动 Evolution API"
            echo "  ./start.sh --stop-evolution   # 停止 Evolution API"
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

# 检查 Docker
check_docker() {
    info "检查 Docker..."
    
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装"
        echo ""
        echo "  安装 Docker:"
        echo "    Ubuntu/Debian:"
        echo "      sudo apt-get update"
        echo "      sudo apt install -y docker.io"
        echo "      sudo usermod -aG docker \$USER"
        echo "      newgrp docker"
        echo "      sudo systemctl start docker"
        echo "      sudo systemctl enable docker"
        echo ""
        echo "    macOS:"
        echo "      brew install --cask docker"
        echo ""
        exit 1
    fi
    
    # 检查 Docker 是否运行
    if ! docker info &> /dev/null; then
        error "Docker 未运行或当前用户无权限"
        echo ""
        echo "  启动 Docker:"
        echo "    sudo systemctl start docker"
        echo ""
        echo "  添加用户到 docker 组（需重新登录生效）:"
        echo "    sudo usermod -aG docker \$USER"
        echo "    newgrp docker"
        echo ""
        exit 1
    fi
    
    DOCKER_VERSION=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    success "Docker $DOCKER_VERSION"
}

# 检查 MongoDB (通过 Docker 容器运行)
check_mongodb() {
    info "检查 MongoDB..."
    
    # 检查 MongoDB 容器是否存在
    if docker ps -a --format '{{.Names}}' | grep -q '^mongodb$'; then
        # 容器存在，检查是否运行中
        if docker ps --format '{{.Names}}' | grep -q '^mongodb$'; then
            success "MongoDB 容器已运行"
            return 0
        else
            # 容器存在但未运行，尝试启动
            warn "MongoDB 容器已停止，正在启动..."
            docker start mongodb
            if [ $? -eq 0 ]; then
                success "MongoDB 容器已启动"
                return 0
            else
                error "MongoDB 容器启动失败"
                echo "  请检查: docker logs mongodb"
                exit 1
            fi
        fi
    fi
    
    # 容器不存在，创建并启动
    warn "MongoDB 容器不存在，正在创建..."
    
    # 创建数据目录
    MONGO_DATA_DIR="$HOME/mongodb/data"
    mkdir -p "$MONGO_DATA_DIR"
    
    # 拉取并启动 MongoDB 容器
    docker pull mongo:5.0.5
    docker run -d \
        --name mongodb \
        -p 27017:27017 \
        -v "$MONGO_DATA_DIR":/data/db \
        mongo:5.0.5
    
    if [ $? -eq 0 ]; then
        success "MongoDB 容器创建并启动成功"
        echo "  数据目录: $MONGO_DATA_DIR"
        # 等待 MongoDB 启动
        sleep 3
    else
        error "MongoDB 容器创建失败"
        echo ""
        echo "  手动创建:"
        echo "    docker pull mongo:5.0.5"
        echo "    docker run -d --name mongodb -p 27017:27017 -v \$HOME/mongodb/data:/data/db mongo:5.0.5"
        echo ""
        exit 1
    fi
}

# 检查 Redis (通过 Docker 容器运行)
check_redis() {
    info "检查 Redis..."

    if docker ps -a --format '{{.Names}}' | grep -q '^redis$'; then
        if docker ps --format '{{.Names}}' | grep -q '^redis$'; then
            success "Redis 容器已运行"
            return 0
        else
            warn "Redis 容器已停止，正在启动..."
            docker start redis
            if [ $? -eq 0 ]; then
                success "Redis 容器已启动"
                return 0
            else
                error "Redis 容器启动失败"
                echo "  请检查: docker logs redis"
                exit 1
            fi
        fi
    fi

    warn "Redis 容器不存在，正在创建..."
    REDIS_DATA_DIR="$HOME/redis/data"
    mkdir -p "$REDIS_DATA_DIR"

    docker pull redis:7.2
    docker run -d \
        --name redis \
        -p 6379:6379 \
        -v "$REDIS_DATA_DIR":/data \
        redis:7.2 redis-server --appendonly yes

    if [ $? -eq 0 ]; then
        success "Redis 容器创建并启动成功"
        echo "  数据目录: $REDIS_DATA_DIR"
        sleep 2
    else
        error "Redis 容器创建失败"
        echo ""
        echo "  手动创建:"
        echo "    docker pull redis:7.2"
        echo "    docker run -d --name redis -p 6379:6379 -v \\$HOME/redis/data:/data redis:7.2 redis-server --appendonly yes"
        echo ""
        exit 1
    fi
}

# 检查并启动 Evolution API (WhatsApp Gateway)
check_evolution_api() {
    # 检查 WhatsApp 是否启用
    WHATSAPP_ENABLED=$(.venv/bin/python3 -c "
import json
try:
    with open('conf/config.json', 'r') as f:
        config = json.load(f)
    print('yes' if config.get('whatsapp', {}).get('enabled', False) else 'no')
except:
    print('no')
" 2>/dev/null || echo "no")

    if [ "$WHATSAPP_ENABLED" != "yes" ]; then
        info "WhatsApp 未启用，跳过 Evolution API"
        return 0
    fi

    info "检查 Evolution API..."

    # 加载 .env 获取 API Key
    source_env

    if [ -z "$WHATSAPP_EVOLUTION_API_KEY" ]; then
        warn "WHATSAPP_EVOLUTION_API_KEY 未在 .env 中配置，跳过 Evolution API"
        return 0
    fi

    # 检查 docker-compose.evolution.yml 是否存在
    if [ ! -f "$SCRIPT_DIR/docker-compose.evolution.yml" ]; then
        warn "docker-compose.evolution.yml 不存在，跳过 Evolution API"
        return 0
    fi

    # 检查容器是否已运行
    if docker ps --format '{{.Names}}' | grep -q '^evolution_api$'; then
        # 检查 API 是否响应
        API_BASE="${WHATSAPP_EVOLUTION_API_BASE:-http://localhost:8082}"
        if curl -s "$API_BASE" > /dev/null 2>&1; then
            success "Evolution API 已运行 ($API_BASE)"
            return 0
        fi
    fi

    # 启动 Evolution API
    info "启动 Evolution API (Docker Compose)..."
    docker compose -f "$SCRIPT_DIR/docker-compose.evolution.yml" up -d 2>&1 | tail -5

    # 等待服务就绪（最多 30 秒）
    API_BASE="${WHATSAPP_EVOLUTION_API_BASE:-http://localhost:8082}"
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s "$API_BASE" > /dev/null 2>&1; then
            success "Evolution API 已就绪 ($API_BASE)"
            return 0
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
        sleep 1
    done

    echo ""
    warn "Evolution API 启动超时，请检查: docker logs evolution_api"
}

# 停止 Evolution API
stop_evolution_api() {
    if [ -f "$SCRIPT_DIR/docker-compose.evolution.yml" ]; then
        info "停止 Evolution API..."
        source_env
        docker compose -f "$SCRIPT_DIR/docker-compose.evolution.yml" down
        success "Evolution API 已停止"
    else
        warn "docker-compose.evolution.yml 不存在"
    fi
}

# 启动 Evolution API（强制启动，不检查 WhatsApp 是否启用）
start_evolution_api() {
    source_env

    if [ -z "$WHATSAPP_EVOLUTION_API_KEY" ]; then
        error "WHATSAPP_EVOLUTION_API_KEY 未在 .env 中配置"
        echo "  请先在 .env 中配置 API Key"
        exit 1
    fi

    if [ ! -f "$SCRIPT_DIR/docker-compose.evolution.yml" ]; then
        error "docker-compose.evolution.yml 不存在"
        exit 1
    fi

    info "启动 Evolution API (Docker Compose)..."
    docker compose -f "$SCRIPT_DIR/docker-compose.evolution.yml" up -d

    # 等待服务就绪
    API_BASE="${WHATSAPP_EVOLUTION_API_BASE:-http://localhost:8082}"
    MAX_RETRIES=30
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s "$API_BASE" > /dev/null 2>&1; then
            success "Evolution API 已就绪 ($API_BASE)"
            echo ""
            echo "管理界面: $API_BASE/manager"
            return 0
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
        sleep 1
    done

    echo ""
    warn "Evolution API 启动超时，请检查: docker logs evolution_api"
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
    mkdir -p agent/temp  # 临时文件目录 (语音/图片处理)
    
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

# 检查角色是否已初始化
check_character_init() {
    info "检查角色初始化状态..."
    
    VENV_PYTHON=".venv/bin/python"
    
    # 检查角色是否存在于数据库
    CHARACTER_EXISTS=$($VENV_PYTHON -c "
import sys
sys.path.insert(0, '.')
try:
    from dao.user_dao import UserDAO
    dao = UserDAO()
    chars = dao.find_characters({'name': '$CHARACTER'})
    print('yes' if chars else 'no')
except Exception as e:
    print('error')
" 2>/dev/null || echo "error")
    
    if [ "$CHARACTER_EXISTS" = "yes" ]; then
        success "角色 '$CHARACTER' 已初始化"
    elif [ "$CHARACTER_EXISTS" = "no" ]; then
        warn "角色 '$CHARACTER' 未初始化"
        echo ""
        echo "  首次部署需要初始化角色数据:"
        echo "    1. 编辑角色配置: nano agent/role/prepare_character.py"
        echo "    2. 执行初始化: python agent/role/prepare_character.py"
        echo "    3. 获取角色 ID: python dao/get_special_users.py"
        echo "    4. 将角色 ID 填入 conf/config.json"
        echo ""
        read -p "是否继续启动？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        # 数据库连接失败等错误，不阻塞启动
        warn "无法检查角色状态（数据库可能未运行）"
    fi
}

# 检查端口转发规则（可选）
check_port_forward() {
    info "检查端口转发规则..."
    
    # 检查 iptables 规则是否存在
    if command -v iptables &> /dev/null; then
        if sudo iptables -t nat -L PREROUTING -n 2>/dev/null | grep -q "redir ports 8080"; then
            success "端口转发 80→8080 已配置"
        else
            warn "端口转发 80→8080 未配置"
            echo "  如需通过 80 端口访问（而非 8080），执行:"
            echo "    sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080"
            echo "  （此步骤可选，仅在需要 80 端口时配置）"
        fi
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
    check_docker
    check_system_deps
    install_python_deps
    check_mongodb
    check_redis
    check_evolution_api
    check_pm2
    check_config
    ensure_directories
    check_env_file
    check_character_init
    check_port_forward
    
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


# 单独检查 WhatsApp 配置（可选）
if [ "$CHECK_WHATSAPP" = true ]; then
    # 激活虚拟环境（如果存在）
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    check_whatsapp_setup
    exit 0
fi

# 单独启动 Evolution API
if [ "$START_EVOLUTION" = true ]; then
    start_evolution_api
    exit 0
fi

# 单独停止 Evolution API
if [ "$STOP_EVOLUTION" = true ]; then
    stop_evolution_api
    exit 0
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


    # 保存主进程 PID
    echo $$ > "$PID_FILE"

    echo ""
    echo "=========================================="
    echo "所有服务已在后台启动"
    echo "  Agent PID: $AGENT_PID"
    echo "  Ecloud PID: $ECLOUD_PID"
    echo "=========================================="
    echo ""
    echo "查看日志:"
    echo "  Agent:  tail -f agent/runner/agent.log"
    echo "  Ecloud: tail -f connector/ecloud/ecloud.log"
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

    # 启动 Evolution API（如果 WhatsApp 已启用）
    check_evolution_api
    echo ""

    # 使用 PM2 启动所有服务
    echo "1. 启动所有服务 (PM2)..."
    pm2 start ecosystem.config.json
    pm2 save
    
    echo ""
    echo "=========================================="
    echo "PM2 模式启动完成"
    echo "=========================================="
    echo ""
    pm2 status
    echo ""
    echo "服务列表:"
    echo "  - coke-agent      (Agent 服务)"
    echo "  - ecloud-input    (E云管家 webhook，端口 8080)"
    echo "  - ecloud-output   (E云管家消息发送)"
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
    echo "  pm2 restart coke-agent     # 重启 Agent"
    echo "  pm2 restart ecloud-input   # 重启 ecloud input"
    echo "  pm2 restart ecloud-output  # 重启 ecloud output"
    echo ""
    echo "查看实时日志:"
    echo "  pm2 logs --lines 100       # 所有服务"
    echo "  pm2 logs coke-agent        # 单个服务"
    echo "=========================================="
    echo ""

    # 检查 WhatsApp Evolution API 配置
    check_whatsapp_setup
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
    
    echo ""
    echo "=== 所有服务已启动 ==="
    echo "PID 文件: $PIDS_FILE"
    echo "日志目录: $LOG_DIR"
    echo ""
    echo "服务端口分配:"
    echo "  - Coke 主服务: 8080"
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
