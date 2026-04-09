#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

MODE="dev"
SKIP_INSTALL=false
FORCE_CLEAN=""

show_help() {
    cat <<'EOF'
Coke Project 启动脚本

用法:
  ./start.sh [选项]

选项:
  --mode, -m <mode>  运行模式: dev (默认), pm2, prod
  --force-clean      启动前清理 worker 锁
  --skip-install     跳过本地环境检查
  --help, -h         显示帮助

模式说明:
  dev   本地直接启动 Python worker
  pm2   用 PM2 管理本地 worker
  prod  用 Docker Compose 启动生产栈
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode|-m)
            MODE="$2"
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
            show_help
            exit 0
            ;;
        *)
            error "未知参数: $1"
            show_help
            exit 1
            ;;
    esac
done

check_python() {
    info "检查 Python 环境..."
    local python_cmd=""
    for cmd in python3.12 python3.11 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            python_cmd="$cmd"
            break
        fi
    done

    if [[ -z "$python_cmd" ]]; then
        error "未找到 Python 3.11+"
        exit 1
    fi

    local version
    version="$("$python_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    success "Python ${version} (${python_cmd})"
    export PYTHON_CMD="$python_cmd"
}

check_venv() {
    info "检查虚拟环境..."
    if [[ ! -f ".venv/bin/python" ]]; then
        warn "虚拟环境不存在，正在创建..."
        "$PYTHON_CMD" -m venv .venv
    fi
    source .venv/bin/activate
    success "虚拟环境已就绪"
}

install_python_deps() {
    info "检查 Python 依赖..."
    if ! .venv/bin/python -c "import pymongo, flask" >/dev/null 2>&1; then
        .venv/bin/pip install --upgrade pip >/dev/null
        .venv/bin/pip install -r requirements.txt >/dev/null
        if [[ -f "agent/requirements.txt" ]]; then
            .venv/bin/pip install -r agent/requirements.txt >/dev/null
        fi
        success "依赖安装完成"
    else
        success "依赖已安装"
    fi
}

check_system_deps() {
    info "检查系统依赖..."
    if ! command -v ffmpeg >/dev/null 2>&1; then
        warn "未找到 ffmpeg，如需语音处理请安装"
    else
        success "ffmpeg 已安装"
    fi
}

check_pm2() {
    info "检查 PM2..."
    if ! command -v node >/dev/null 2>&1; then
        error "PM2 模式需要 Node.js"
        exit 1
    fi
    if ! command -v pm2 >/dev/null 2>&1; then
        warn "PM2 未安装，正在安装..."
        npm install -g pm2 >/dev/null
    fi
    success "PM2 已就绪"
}

check_docker() {
    info "检查 Docker..."
    if ! command -v docker >/dev/null 2>&1; then
        error "未找到 Docker"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        error "Docker 未运行或当前用户无权限访问"
        exit 1
    fi
    success "Docker 已就绪"
}

check_config() {
    info "检查配置文件..."
    if [[ ! -f "conf/config.json" ]]; then
        error "缺少 conf/config.json"
        exit 1
    fi
    success "配置文件已存在"
}

ensure_directories() {
    mkdir -p logs agent/temp data/labels data/metadata
}

check_env_file() {
    if [[ ! -f ".env" ]]; then
        warn ".env 不存在，部分能力可能无法工作"
    fi
}

run_setup() {
    check_python
    check_venv
    install_python_deps
    check_system_deps
    check_config
    ensure_directories
    check_env_file

    case "$MODE" in
        pm2)
            check_pm2
            ;;
        prod|production)
            check_docker
            ;;
    esac
}

start_dev_mode() {
    info "启动本地 worker"
    exec bash agent/runner/agent_start.sh $FORCE_CLEAN
}

start_pm2_mode() {
    info "使用 PM2 启动 worker"
    pkill -f "agent_runner.py" >/dev/null 2>&1 || true
    pm2 start ecosystem.config.json --update-env
    pm2 save >/dev/null
    pm2 status
}

start_prod_mode() {
    info "使用 Docker Compose 启动生产栈"
    docker compose -f docker-compose.prod.yml up -d --build --remove-orphans
    docker compose -f docker-compose.prod.yml ps
}

if [[ "$SKIP_INSTALL" == "false" ]]; then
    run_setup
fi

case "$MODE" in
    dev)
        start_dev_mode
        ;;
    pm2)
        start_pm2_mode
        ;;
    prod|production)
        start_prod_mode
        ;;
    *)
        error "未知模式: $MODE"
        show_help
        exit 1
        ;;
esac
