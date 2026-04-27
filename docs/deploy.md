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
- `features`

生产部署还需要桥接与身份相关的运行时密钥：

- `COKE_WEB_ALLOWED_ORIGIN`：Coke 用户前端允许的浏览器来源，通常与 `DOMAIN_CLIENT` 保持一致
- `CLAWSCALE_IDENTITY_API_KEY`：ClawScale 身份服务调用密钥
- `CLAWSCALE_OUTBOUND_API_KEY`：ClawScale 出站服务调用密钥
- `CLAWSCALE_WECHAT_CHANNEL_API_KEY`：ClawScale 微信通道调用密钥

当前对外接口按这个契约部署和核验：

- Web：`/auth/*`、`/channels/wechat-personal`、`/account/subscription`
- Public API：`/api/auth/*`、`/api/customer/channels/wechat-personal/*`、`/api/customer/subscription`、`/api/customer/subscription/checkout`、`/api/public/subscription-checkout`、`/api/webhooks/stripe`
- Internal API：`/api/internal/*`
- Retired public entrypoints：`/login`、`/coke/login`、`/api/coke/auth/login` 已移除，部署后应返回 404

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

部署脚本现在会在同步前校验本地 `gateway/` checkout 是否和根仓库记录的 submodule commit 完全一致。
如果两者不一致，脚本会直接失败，避免把旧的 gateway/web 内容部署到线上。

脚本也会把根仓库和 `gateway/` 分两次同步，确保远端 `~/coke/gateway` 会被完整刷新，而不是混入旧目录结构。
同步完成后，脚本会核验新的 Web 入口和公共 API 结构，并确认已退役的公开入口 `/login`、`/coke/login` 和 `/api/coke/auth/login` 已经 404。

如果当前公网域名不是远端 `.env` 里已有的值，部署时应显式传入：

```bash
PUBLIC_BASE_URL=https://coke.ydyk123.top ./scripts/deploy-compose-to-gcp.sh --restart
```

当 `PUBLIC_BASE_URL` 被设置时，脚本会在远端 `.env` 中同步更新这些字段：

- `DOMAIN_CLIENT`
- `CORS_ORIGIN`
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_COKE_API_URL`

这样重建后的 gateway web bundle 会指向当前公网域名，而不是继续使用旧的前端/API 基础地址。
如果你改了域名或用了 `PUBLIC_BASE_URL` 自动更新，必须再核对 `COKE_WEB_ALLOWED_ORIGIN` 是否与同一个浏览器 origin 完全一致，否则 `coke-bridge` 的 CORS 会继续指向旧域名。

在服务器上准备 `.env`：

```bash
ssh gcp-coke 'cd ~/coke && cp deploy/env/coke.env.example .env'
```

然后按实际密钥编辑 `~/coke/.env`。

生产环境至少要补齐这些变量，Coke 的邮箱链路才算真正可用：

- `COKE_JWT_SECRET`：Coke 用户登录态签名密钥，和后台成员 `JWT_SECRET` 分开
- `DOMAIN_CLIENT`：邮件里的前端链接根地址，例如 `https://coke.keep4oforever.com`
- `NEXT_PUBLIC_API_URL`：gateway web bundle 使用的公开 API 目标
- `NEXT_PUBLIC_COKE_API_URL`：Coke 用户前端使用的公开 API 目标
- `RESEND_API_KEY`：邮件发送所需的 Resend API 密钥
- `EMAIL_FROM`：验证邮件和重置密码邮件的发件地址，建议使用已在 Resend 验证的域名，例如 `noreply@keep4oforever.com`
- `EMAIL_FROM_NAME`：发件人显示名，建议保持 `Coke`
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID`：续费链路必需

桥接与身份相关的运行时密钥也必须存在，否则 `coke-bridge` 和相关身份/出站调用会被错误配置：

- `COKE_WEB_ALLOWED_ORIGIN`：Coke 用户前端允许的浏览器来源
- 这个值必须与实际 public browser origin 完全一致，域名变更或 `PUBLIC_BASE_URL` 自动更新后要立即复核
- `CLAWSCALE_IDENTITY_API_KEY`
- `CLAWSCALE_OUTBOUND_API_KEY`
- `CLAWSCALE_WECHAT_CHANNEL_API_KEY`

如果只配置了账号注册而没有配置邮件发送，`/api/auth/register` 仍会创建账户，
但用户只能在 `/auth/verify-email` 页面通过“Resend verification email”完成验证。
公开页面的导航应指向 `/channels/wechat-personal` 和 `/account/subscription`，
而不是已退役的公开入口 `/login`、`/coke/login` 和 `/api/coke/auth/login`。

### 4.3 启动 Compose 栈

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans'
```

如果使用推荐部署脚本并带 `--restart`，它会在 `docker compose up -d --build --remove-orphans` 之后自动执行这些校验：

- 远端 `gateway/packages/web` 新首页源文件存在
- 远端 `gateway/packages/web/app/(customer)/auth/login/page.tsx`、`gateway/packages/web/app/(customer)/auth/register/page.tsx`、`gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx` 和 `gateway/packages/web/app/(customer)/account/subscription/page.tsx` 存在
- 远端 `gateway/packages/api/src/routes/customer-auth-routes.ts`、`gateway/packages/api/src/routes/customer-channel-routes.ts`、`gateway/packages/api/src/routes/customer-subscription-routes.ts` 和 `gateway/packages/api/src/index.ts` 存在
- `http://127.0.0.1:4041/health`
- `http://127.0.0.1:8090/bridge/healthz`
- 公网首页包含当前 Kap 监督定位文案
- 公网首页包含 `/channels/wechat-personal` 和 `/account/subscription` 的入口
- 公网 `/auth/login` 返回 `200`
- 公网 `/auth/register` 返回 `200`
- 公网已退役入口 `/login` 返回 `404`
- 公网已退役入口 `/coke/login` 返回 `404`
- 公网已退役入口 `/api/coke/auth/login` 返回 `404`

`docker-compose.prod.yml` 里包含一个一次性 `coke-bootstrap` 服务：

- 它会在空 MongoDB 上幂等写入 `default_character_alias`
- `coke-agent` 和 `coke-bridge` 都依赖它成功完成后再启动
- 日常重复执行 `docker compose up -d` 是安全的
- `coke-bridge` 生产环境通过 Gunicorn 启动，不再使用 Flask development server

如果只需要手动重跑 bootstrap：

```bash
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml run --rm coke-bootstrap'
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
ssh gcp-coke 'cd ~/coke && docker compose -f docker-compose.prod.yml logs --tail=20 coke-bootstrap'
ssh gcp-coke 'curl -sS http://127.0.0.1:4041/health'
ssh gcp-coke 'curl -sS http://127.0.0.1:8090/bridge/healthz'
curl -k https://coke.keep4oforever.com/health
curl -k https://coke.keep4oforever.com/bridge/healthz
```

如需把 Coke 用户注册、Stripe Checkout 支付、Webhook 落库和订阅状态切换整条链路全自动跑一遍，
可以直接使用 gateway 里的 smoke script：

```bash
pnpm --dir gateway install
pnpm --dir gateway/packages/api exec playwright install chromium
pnpm --dir gateway/packages/api coke:stripe:smoke
```

可选环境变量：

- `COKE_SMOKE_BASE_URL`：覆盖默认的 `https://coke.keep4oforever.com`
- `COKE_SMOKE_HEADLESS=false`：需要观察浏览器结账过程时可关闭 headless

脚本会自动创建临时测试用户、完成一笔 Stripe test card 支付，并把截图写到系统临时目录下的 `coke-stripe-smoke/`。

### 4.7 Evolution API manager 子路径挂载

如果 Evolution API 继续挂在现有域名子路径 `/evolution-api/` 下，而不是独立子域名，
需要先生成一个 patched `manager-dist/`，再重启 Evolution 容器。

原因是 Evolution 自带 manager 前端默认假设自己运行在根路径：

- `index.html` 静态资源写死为 `/assets/...`
- 前端路由默认 `basename` 为空
- 登录页默认服务器地址只会填当前 origin，不会自动带 `/evolution-api`

仓库里的补丁脚本会把这些路径改成兼容现有子路径的形式：

```bash
ssh gcp-coke 'rm -rf ~/evolution/manager-dist ~/evolution/manager-dist-upstream && mkdir -p ~/evolution'
ssh gcp-coke 'docker cp evolution-api:/evolution/manager/dist/. ~/evolution/manager-dist-upstream'
scp deploy/evolution/patch_manager_dist.sh gcp-coke:~/evolution/patch_manager_dist.sh
ssh gcp-coke 'bash ~/evolution/patch_manager_dist.sh ~/evolution/manager-dist-upstream ~/evolution/manager-dist'
```

然后确认 `~/evolution/.env` 里启用了 manager：

```bash
ssh gcp-coke "grep -n 'SERVER_DISABLE_MANAGER' ~/evolution/.env"
```

值应该是：

```bash
SERVER_DISABLE_MANAGER=false
```

最后同步新的 Nginx 配置并重启 Evolution：

```bash
scp deploy/nginx/coke.conf gcp-coke:~/coke/deploy/nginx/coke.conf
ssh gcp-coke "sudo cp ~/coke/deploy/nginx/coke.conf /etc/nginx/sites-available/coke"
ssh gcp-coke "sudo nginx -t && sudo systemctl reload nginx"
ssh gcp-coke 'cd ~/evolution && docker compose up -d --force-recreate evolution-api'
```

回归检查：

```bash
curl -I https://coke.keep4oforever.com/evolution-api/manager/
curl -I https://coke.keep4oforever.com/evolution-api/manager-assets/index-CO3NSIFj.js
curl -s https://coke.keep4oforever.com/evolution-api/manager/ | head
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
