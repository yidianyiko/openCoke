# 部署与启动

当前仓库推荐分为两类运行方式：

1. 本地开发：`./start.sh` 或 `bash agent/runner/agent_start.sh`
2. 生产部署：`docker-compose.prod.yml` + 主机 Nginx + systemd

生产环境不再使用 PM2 作为正式运行面。

## 1. 本地开发环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

基础依赖：

- Python 3.12+
- MongoDB
- Redis

## 2. 本地开发配置

- 敏感信息放在 `.env`
- 运行时配置放在 `conf/config.json`
- `conf/config.json` 支持 `${ENV_VAR}` 占位

常见配置项：

- `default_character_alias`
- `characters`
- `group_chat`
- `mongodb`
- `redis`
- `clawscale_bridge`
- `access_control`
- `features`

## 3. 本地开发启动

### 方式 A: 顶层启动脚本

```bash
./start.sh
./start.sh --mode pm2
```

### 方式 B: 仅启动 Python worker

```bash
bash agent/runner/agent_start.sh
bash agent/runner/agent_start.sh --force-clean
```

## 4. 生产部署

### 4.1 生产部署文件

- `docker-compose.prod.yml`
- `deploy/config/coke.config.json`
- `deploy/env/coke.env.example`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`

### 4.2 服务器准备

保留主机上的：

- Docker / Docker Compose
- Nginx
- TLS 证书

清理旧 Coke 运行态：

```bash
./scripts/reset-gcp-coke.sh
```

同步生产部署文件：

```bash
./scripts/deploy-compose-to-gcp.sh
```

在服务器上准备 `.env`：

```bash
ssh gcp-coke 'cd ~/coke && cp deploy/env/coke.env.example .env'
```

然后按实际密钥编辑 `~/coke/.env`。

### 4.3 启动 Compose 栈

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans'
```

### 4.4 安装 Nginx 配置

```bash
ssh gcp-coke "sudo cp ~/coke/deploy/nginx/coke.conf /etc/nginx/sites-available/coke"
ssh gcp-coke "sudo ln -sf /etc/nginx/sites-available/coke /etc/nginx/sites-enabled/coke"
ssh gcp-coke "sudo nginx -t && sudo systemctl reload nginx"
```

### 4.5 安装 systemd 单元

```bash
ssh gcp-coke "sudo cp ~/coke/deploy/systemd/coke-compose.service /etc/systemd/system/coke-compose.service"
ssh gcp-coke "sudo systemctl daemon-reload"
ssh gcp-coke "sudo systemctl enable coke-compose.service"
```

### 4.6 核验

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml ps'
ssh gcp-coke 'curl -sS http://127.0.0.1:4041/health'
ssh gcp-coke 'curl -sS http://127.0.0.1:8090/bridge/healthz'
curl -k https://coke.keep4oforever.com/health
curl -k https://coke.keep4oforever.com/bridge/healthz
```

## 5. 日志与排障

- 主日志：`agent/runner/agent.log`
- Compose 服务状态：`docker compose -f docker-compose.prod.yml ps`
- Compose 服务日志：`docker compose -f docker-compose.prod.yml logs <service>`

常见排查项：

- `.env` 是否已加载
- `conf/config.json` 或 `deploy/config/coke.config.json` 中的 MongoDB / Redis / bridge 配置是否正确
- 锁是否残留，必要时使用 `--force-clean`
- Redis stream 模式不可用时，worker 是否回退到 Mongo polling

## 6. 运行面说明

当前正式部署只保留：

- `mongo`
- `redis`
- `postgres`
- `coke-agent`
- `coke-bridge`
- `gateway`

如果只需要核验 Python 主流程，优先使用 `agent_start.sh`。
