# LangBot 多平台接入使用文档

## 架构概述（方案 A：混合模式）

```
接收路径：飞书用户 → LangBot (WebSocket) → Coke webhook → Agent
发送路径：Coke → 飞书 API (直接调用) → 飞书用户
```

### 设计理念

- **接收使用 LangBot**：利用其统一的多平台接入能力
- **发送绕过 LangBot**：因为 Lark adapter 的 `send_message()` 是空实现
- **其他平台仍用 LangBot API**：Telegram、Discord 等如果支持主动发送，继续使用 LangBot API

---

## 配置说明

### 1. LangBot 配置

访问 `http://服务器IP:5300` 配置 LangBot：

#### 飞书机器人配置

```json
{
  "adapter": "lark",
  "enable": true,
  "app_id": "cli_a9e2c9da8cf85cd4",
  "app_secret": "w8xxkD4CrIKO6blg25tTbbMfoGQ3oRFi",
  "bot_name": "coke-test",
  "enable-webhook": false  // 使用 WebSocket 长连接模式
}
```

#### Webhook 配置（用于接收消息）

- URL: `http://127.0.0.1:8081/langbot/webhook`
- Enabled: `true`

#### API Key（用于发送其他平台消息）

从 WebUI 中创建 API Key，记录下来。

### 2. Coke 配置

在 `conf/config.json` 中添加：

```json
{
  "langbot": {
    "enabled": true,
    "base_url": "http://127.0.0.1:5300",
    "api_key": "lbk_xxxxxxxxxxxxxxxxxxx",
    "webhook_port": 8081,
    "default_character_alias": "qiaoyun",
    "single_server_mode": true,
    "feishu": {
      "app_id": "cli_a9e2c9da8cf85cd4",
      "app_secret": "w8xxkD4CrIKO6blg25tTbbMfoGQ3oRFi"
    }
  }
}
```

**配置说明**：
- `base_url`: LangBot 服务地址
- `api_key`: LangBot API 密钥（用于其他平台）
- `webhook_port`: Coke webhook 端口
- `feishu.app_id`: 飞书应用 ID
- `feishu.app_secret`: 飞书应用密钥

---

## 启动服务

### 方法 1：使用启动脚本（推荐）

```bash
cd ~/workspace/coke-poke
bash start.sh
```

这将启动：
- Agent 服务
- langbot_input（接收 LangBot webhook）
- langbot_output（发送消息到各平台）

### 方法 2：手动启动

```bash
# 1. 启动 Agent
bash agent/runner/agent_start.sh

# 2. 启动 langbot_input
source .venv/bin/activate
nohup python3 connector/langbot/langbot_input.py > /tmp/langbot_input.log 2>&1 &

# 3. 启动 langbot_output
source .venv/bin/activate
nohup python3 connector/langbot/langbot_output.py > /tmp/langbot_output.log 2>&1 &
```

---

## 消息流程详解

### 1. 接收消息（飞书 → Coke）

```
飞书用户发送消息
  ↓
LangBot (WebSocket 接收)
  ↓
LangBot 推送到 Coke webhook (http://127.0.0.1:8081/langbot/webhook)
  ↓
langbot_input.py 接收并转换格式
  ↓
插入 MongoDB inputmessages 集合
  ↓
Agent 处理消息
```

### 2. 发送消息（Coke → 飞书）

```
Agent 生成回复
  ↓
插入 MongoDB outputmessages 集合
  ↓
langbot_output.py 轮询 pending 消息
  ↓
检测平台类型：
  - 如果是 LarkAdapter → 直接调用飞书 API
  - 其他平台 → 调用 LangBot Service API
  ↓
飞书用户收到消息 ✅
```

---

## 平台标识

metadata 中的 `langbot_adapter` 字段决定发送方式：

| Adapter 名称 | 发送方式 | 说明 |
|-------------|---------|------|
| `LarkAdapter` | 飞书 API 直接调用 | LangBot adapter 不支持主动发送 |
| `TelegramAdapter` | LangBot Service API | 如果支持主动发送 |
| `DiscordAdapter` | LangBot Service API | 如果支持主动发送 |

---

## 调试指南

### 查看日志

```bash
# LangBot 接收日志
tail -f /tmp/langbot_input.log

# Coke 发送日志
tail -f /tmp/langbot_output.log

# Agent 处理日志
tail -f agent/runner/agent.log
```

### 常见问题

#### 1. 消息接收不到

检查：
- LangBot 是否运行：`pm2 status`
- Webhook 是否配置：LangBot WebUI → Webhooks
- langbot_input 是否运行：`ps aux | grep langbot_input`

#### 2. 消息发送失败

检查：
- 飞书凭证是否配置正确
- langbot_output 是否运行
- MongoDB 中 outputmessage 的 status 字段

```bash
# 查看失败的发送
docker exec coke-mongo mongosh --quiet mymongo --eval '
  db.outputmessages.find({status: "failed"}).sort({created_at: -1}).limit(5)
'
```

#### 3. 收到了 LangBot 的 "Pipeline skipped" 日志

这是正常的！表示 webhook 正确配置，Coke 接管了消息处理。

---

## 添加新平台

### 示例：添加 Telegram

1. 在 LangBot WebUI 中配置 Telegram bot
2. 在 `characters` 配置中添加平台：

```json
{
  "qiaoyun": {
    "platforms": {
      "langbot_TelegramAdapter": {
        "id": "telegram_user_id",
        "nickname": "用户昵称"
      }
    }
  }
}
```

3. 无需修改代码，langbot_output 会自动检测并使用 LangBot Service API 发送

---

## 架构优势

### ✅ 多平台扩展
只需配置 LangBot，无需修改 Coke 代码

### ✅ 统一接入
所有平台都通过 `/langbot/webhook` 接入

### ✅ 灵活发送
根据平台能力选择最优发送方式

### ✅ 解耦
Coke 专注 AI 逻辑，LangBot 专注平台适配

---

## 技术限制

### ❌ 架构不对称
- 接收：通过 LangBot
- 发送：部分绕过 LangBot

### ❌ 配置分散
- LangBot WebUI 配置接收
- Coke config.json 配置发送

### ❌ 无法使用 LangBot 高级特性
- 流式回复（通过 `reply_message`）
- 卡片消息更新
- 消息编辑

**如果需要这些特性，建议考虑方案 B（直接集成飞书 SDK）**

---

## 文件说明

```
connector/langbot/
├── langbot_input.py      # 接收 LangBot webhook
├── langbot_output.py     # 发送消息（智能路由）
├── langbot_adapter.py    # 消息格式转换
├── langbot_api.py        # LangBot Service API 客户端
└── feishu_api.py         # 飞书 API 客户端（直接调用）
```

---

## 版本历史

- v1.0 (2025-01-15): 初始实现，支持飞书通过混合模式
- 已知问题：LangBot Lark adapter 的 `send_message()` 是空实现

---

## 相关链接

- [LangBot 文档](https://docs.langbot.app)
- [飞书开放平台](https://open.feishu.cn)
- [Coke 项目文档](./README.md)
