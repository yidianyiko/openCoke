# Evolution API Docker 管理集成到 start.sh

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 start.sh 自动管理 Evolution API Docker Compose 生命周期，API Key 从 .env 读取，不硬编码。

**Architecture:** docker-compose.evolution.yml 通过环境变量引用 WHATSAPP_EVOLUTION_API_KEY；start.sh 在启动前 source .env，提供 check/start/stop 三个操作；check_whatsapp_setup 修复 API 路径适配 v2.x。

**Tech Stack:** Bash, Docker Compose, Evolution API v2.2.x

---

### Task 1: docker-compose.evolution.yml 改用环境变量

**Files:**
- Modify: `docker-compose.evolution.yml:27`

**Step 1: 替换硬编码 API Key 为环境变量引用**

将 `AUTHENTICATION_API_KEY=5a9d52ff...` 改为 `AUTHENTICATION_API_KEY=${WHATSAPP_EVOLUTION_API_KEY}`。

Docker Compose 会自动从当前 shell 环境中读取变量，start.sh 在调用前会 source .env。

```yaml
    environment:
      - SERVER_PORT=8082
      - AUTHENTICATION_API_KEY=${WHATSAPP_EVOLUTION_API_KEY}
```

**Step 2: 验证**

```bash
source .env && docker compose -f docker-compose.evolution.yml config | grep AUTHENTICATION
```

Expected: 输出中显示实际的 key 值（非变量名）

**Step 3: Commit**

```bash
git add docker-compose.evolution.yml
git commit -m "refactor(docker): use env var for Evolution API key"
```

---

### Task 2: start.sh 新增 source_env 辅助函数

**Files:**
- Modify: `start.sh` (在颜色输出定义之后，约第 29 行后)

**Step 1: 添加 source_env 函数**

在 `error()` 函数定义之后添加：

```bash
# 加载 .env 环境变量
source_env() {
    if [ -f "$SCRIPT_DIR/.env" ]; then
        set -a
        source "$SCRIPT_DIR/.env"
        set +a
    fi
}
```

`set -a` / `set +a` 确保 source 的变量自动 export，供 docker compose 子进程使用。

**Step 2: Commit**

```bash
git add start.sh
git commit -m "feat(start): add source_env helper function"
```

---

### Task 3: start.sh 新增 check_evolution_api 函数

**Files:**
- Modify: `start.sh` (在 `check_redis()` 函数之后，约第 617 行后)

**Step 1: 添加 Evolution API Docker Compose 管理函数**

```bash
# 检查并启动 Evolution API (WhatsApp)
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
```

**Step 2: Commit**

```bash
git add start.sh
git commit -m "feat(start): add Evolution API Docker Compose management"
```

---

### Task 4: start.sh 新增 --start-evolution / --stop-evolution 参数

**Files:**
- Modify: `start.sh` 参数解析部分（约第 235-312 行）

**Step 1: 添加新变量和参数解析**

在默认参数部分（约第 230 行）新增：

```bash
START_EVOLUTION=false
STOP_EVOLUTION=false
```

在 `while` 循环的 `case` 中添加：

```bash
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
```

**Step 2: 在参数解析后、启动模式前添加处理逻辑**

在 `CHECK_WHATSAPP` 处理块（约第 807-814 行）之后添加：

```bash
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
```

**Step 3: 更新 help 输出**

在 `--help` 的选项列表中添加：

```bash
            echo "  --start-evolution     启动 Evolution API (WhatsApp)"
            echo "  --stop-evolution      停止 Evolution API (WhatsApp)"
```

在示例部分添加：

```bash
            echo "  ./start.sh --start-evolution  # 启动 Evolution API"
            echo "  ./start.sh --stop-evolution   # 停止 Evolution API"
```

**Step 4: Commit**

```bash
git add start.sh
git commit -m "feat(start): add --start-evolution and --stop-evolution flags"
```

---

### Task 5: 修复 check_whatsapp_setup 函数

**Files:**
- Modify: `start.sh:30-223` (`check_whatsapp_setup` 函数)

**Step 1: 修复步骤 1 提示中的端口和 Docker 命令**

将未启用时的提示从 docker run 改为 docker compose：

```bash
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
```

**Step 2: 修复 API 路径（v2 无 /v1 前缀）**

将所有 `$API_BASE/v1/instance/` 改为 `$API_BASE/instance/`：

- 第 164 行: `$API_BASE/v1/instance/connectionState/` → `$API_BASE/instance/connectionState/`
- 第 195 行: `$API_BASE/v1/instance/create` → `$API_BASE/instance/create`

**Step 3: 修复 Evolution API 未运行时的提示**

将 docker run 提示改为：

```bash
        echo "请先启动 Evolution API:"
        echo "  ./start.sh --start-evolution"
```

**Step 4: Commit**

```bash
git add start.sh
git commit -m "fix(start): update WhatsApp check for Evolution API v2 and Docker Compose"
```

---

### Task 6: PM2 模式集成 Evolution API 自动启动

**Files:**
- Modify: `start.sh` `start_pm2_mode` 函数（约第 924 行）

**Step 1: 在 PM2 启动服务之前添加 Evolution API 检查**

在 `start_pm2_mode` 函数中，"使用 PM2 启动所有服务" 之前（约第 1008 行前）添加：

```bash
    # 启动 Evolution API（如果 WhatsApp 已启用）
    check_evolution_api
    echo ""
```

**Step 2: run_setup 中添加 Evolution API 检查**

在 `run_setup` 函数中，`check_redis` 之后添加：

```bash
    check_evolution_api
```

**Step 3: Commit**

```bash
git add start.sh
git commit -m "feat(start): auto-start Evolution API in PM2 and setup modes"
```

---

### Task 7: 端对端验证

**Step 1: 验证 --help 输出**

```bash
./start.sh --help
```

Expected: 显示 `--start-evolution` 和 `--stop-evolution` 选项

**Step 2: 验证 --start-evolution**

```bash
./start.sh --start-evolution
```

Expected: Docker Compose 启动，显示 "Evolution API 已就绪"

**Step 3: 验证 --check-whatsapp**

```bash
./start.sh --check-whatsapp
```

Expected: 显示正确的端口 8082 和 API 路径

**Step 4: 验证 --stop-evolution**

```bash
./start.sh --stop-evolution
```

Expected: Docker Compose 停止

**Step 5: 最终 Commit**

```bash
git add -A
git commit -m "feat(start): complete Evolution API Docker Compose integration"
```
