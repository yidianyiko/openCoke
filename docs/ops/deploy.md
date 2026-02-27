# 部署与启动（Coke）

本指南覆盖最少可用部署：MongoDB、Python 依赖、后台服务与微信连接器（E云管家）。

## 1. 环境准备
- 系统：Linux（Debian/Ubuntu 推荐）
- Python：3.12+
- MongoDB：5.x+

安装与虚拟环境：
```
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置
编辑 `conf/config.json`：
- `default_character_alias`：角色别名（与 ecloud.wId 下键一致）
- `ecloud.Authorization`：E云管家 API 授权
- `ecloud.wId.<alias>`：E云登录态 wId

可选：在 `.env` 中放置敏感变量（脚本会自动加载）。

## 3. 启动后台服务
```
bash agent/runner/agent_start.sh
```
- 启动 Agno 后台服务与消息处理 workers
- 后台日志：`agent/runner/agent.log`
- 变量：
  - `AGENT_WORKERS`（默认 5）
  - `DISABLE_BACKGROUND_AGENTS`（默认启用背景任务）

## 4. 启动 E云连接器
E云用于收发微信消息：
```
bash connector/ecloud/ecloud_start.sh
```
- 读取 `conf/config.json` 的 `ecloud` 配置
- 发送日志：`connector/ecloud/ecloud.log`

回调地址配置（E云管家后台）：
- 将消息回调地址指向部署的输入服务（见 `connector/ecloud/ecloud_input.py` 暴露的 HTTP 服务）

## 5. 运行与验证
- 后台任务包括：提醒触发、主动消息（Future）、关系衰减、Hold 恢复等
- 主动消息通过统一入口触发：
  - `agent/runner/agent_background_handler.py` → `handle_pending_future_message()` → `handle_message(..., message_source='future')`
  - 没有独立的 FutureMessageWorkflow/触发服务类

## 6. 常用维护
- 清理锁（启动脚本自动）：`agent/runner/agent_start.sh --force-clean`
- 查看提醒：`dao/reminder_dao.py` 提供简单方法；也可用 mongo shell 查询
- 日志：
  - 核心：`agent/runner/agent.log`
  - 连接器：`connector/ecloud/ecloud.log`

