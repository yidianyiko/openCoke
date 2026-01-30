# LangBot 生产环境部署指南

## 架构概述

```
┌─────────────────┐    HTTP API     ┌─────────────────┐
│   LangBot 服务   │ ←──────────────→ │   Coke 服务      │
│   (独立服务器)    │                 │                 │
│                 │    Webhook      │                 │
│  - 消息接收      │ ──────────────→ │ - langbot_input │
│  - 平台适配      │                 │ - langbot_output│
│  - 消息发送      │                 │ - MongoDB       │
└─────────────────┘                 └─────────────────┘
```

## 1. LangBot 服务部署

### 1.1 服务器要求
- 独立服务器或容器
- 公网 IP (用于接收平台 webhook)
- 端口开放：5300 (API 服务)

### 1.2 LangBot 配置
```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 5300
  },
  "api": {
    "keys": ["lbk_production_key_here"]
  },
  "adapters": {
    "qq_official": {...},
    "telegram": {...},
    "wechat": {...}
  }
}
```

## 2. Coke 服务配置

### 2.1 配置文件更新 (conf/config.json)
```json
{
  "langbot": {
    "enabled": true,
    "base_url": "http://langbot-server:5300",  // LangBot 服务器地址
    "api_key": "lbk_production_key_here",      // 生产环境 API Key
    "webhook_port": 8081,                      // Coke 接收 webhook 的端口
    "default_character_alias": "qiaoyun"
  }
}
```

### 2.2 网络配置
- Coke 服务器需要能访问 LangBot 服务器的 5300 端口
- LangBot 服务器需要能访问 Coke 服务器的 8081 端口 (webhook)

## 3. 部署步骤

### 3.1 LangBot 服务器部署
```bash
# 1. 部署 LangBot 服务
docker run -d \
  --name langbot \
  -p 5300:5300 \
  -v /path/to/langbot/config:/app/config \
  langbot:latest

# 2. 配置各平台适配器
# 3. 设置 webhook URL 指向 Coke 服务器
```

### 3.2 Coke 服务器部署
```bash
# 1. 更新配置文件
vim conf/config.json

# 2. 启动 LangBot 连接器
bash connector/langbot/langbot_start.sh

# 3. 验证服务状态
curl http://localhost:8081/langbot/webhook -X POST -d '{}'
```

## 4. 生产环境测试

### 4.1 移除 Mock 依赖
生产环境中需要：

1. **配置真实的 LangBot 服务地址**
2. **使用真实的 API Key**
3. **配置真实的平台适配器**

### 4.2 测试流程
```bash
# 1. 测试 API 连通性
curl -H "X-API-Key: lbk_production_key" \
     -H "Content-Type: application/json" \
     -d '{"target_type":"person","target_id":"test_user","message_chain":[{"type":"Plain","text":"test"}]}' \
     http://langbot-server:5300/api/v1/platform/bots/bot-uuid/send_message

# 2. 测试 webhook 接收
curl -X POST http://coke-server:8081/langbot/webhook \
     -H "Content-Type: application/json" \
     -d '{"event_type":"bot.person_message","data":{...}}'

# 3. 端到端测试
python scripts/langbot_insert_pending_output.py \
  --bot-uuid "production-bot-uuid" \
  --target-type "person" \
  --target-id "test-user-id" \
  --message "Hello from production!"
```

## 5. 监控和日志

### 5.1 日志文件
- LangBot 连接器：`connector/langbot/langbot.log`
- LangBot 服务：根据 LangBot 配置

### 5.2 健康检查
```bash
# Coke 服务健康检查
curl http://localhost:8081/langbot/webhook

# LangBot 服务健康检查  
curl http://langbot-server:5300/healthz
```

## 6. 安全考虑

1. **API Key 管理**：使用环境变量或密钥管理服务
2. **网络隔离**：限制服务器间的网络访问
3. **HTTPS**：生产环境使用 HTTPS
4. **防火墙**：只开放必要端口

## 7. 故障排查

### 7.1 常见问题
- 网络连通性：检查防火墙和路由
- API Key 错误：验证密钥配置
- 消息格式错误：检查适配器转换逻辑

### 7.2 调试命令
```bash
# 查看连接器日志
tail -f connector/langbot/langbot.log

# 检查待发消息
mongo mymongo --eval "db.outputmessages.find({platform:'langbot',status:'pending'})"

# 测试 API 连接
python -c "
from connector.langbot.langbot_api import LangBotAPI
api = LangBotAPI('http://langbot-server:5300', 'your-api-key')
print(api.send_message('bot-uuid', 'person', 'test-user', [{'type':'Plain','text':'test'}]))
"
```