# 部署与启动

本仓库当前保留两类常用启动方式：

1. `./start.sh`
2. `bash agent/runner/agent_start.sh`

前者适合本地或单机整体启动，后者适合只拉起 Python worker。

## 1. 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

基础依赖：

- Python 3.12+
- MongoDB
- Redis（启用 stream 模式时需要）

## 2. 配置

- 敏感信息放在 `.env`
- 运行时配置放在 `conf/config.json`
- `conf/config.json` 支持 `${ENV_VAR}` 占位

常见配置项：

- `default_character_alias`
- `characters`
- `ecloud`
- `mongodb`
- `redis`
- `whatsapp`
- `access_control`
- `features`

## 3. 启动

### 方式 A: 顶层启动脚本

```bash
./start.sh
```

可用参数参考：

```bash
./start.sh --help
./start.sh --mode prod --check
```

### 方式 B: 仅启动 Python worker

```bash
bash agent/runner/agent_start.sh
```

清理残留锁后启动：

```bash
bash agent/runner/agent_start.sh --force-clean
```

## 4. 日志与排障

- 主日志：`agent/runner/agent.log`
- ecloud 连接器日志：`connector/ecloud/ecloud.log`

常见排查项：

- `.env` 是否已加载
- `conf/config.json` 中的 MongoDB / Redis / connector 配置是否正确
- 锁是否残留，必要时使用 `--force-clean`
- Redis stream 模式不可用时，worker 是否回退到 Mongo polling

## 5. 连接器说明

- 微信 ecloud 入口保留在 `connector/ecloud/`
- WhatsApp 相关适配器位于 `connector/adapters/whatsapp/`
- 终端测试工具位于 `connector/terminal/`

如果只需要核验 Python 主流程，优先使用 `agent_start.sh`。
