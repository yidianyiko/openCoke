# LangBot 单服务器部署方案

## 架构概述

```
单服务器部署架构:
┌─────────────────────────────────────────────────────────────┐
│                    服务器 (IP: xxx.xxx.xxx.xxx)              │
├─────────────────────────────────────────────────────────────┤
│  进程1: LangBot 核心服务                                      │
│  - 端口: 5300                                               │
│  - 功能: 消息路由、平台适配、API 服务                          │
│                                                             │
│  进程2: Coke 主服务                                          │
│  - 端口: 8080 (主服务)                                       │
│  - 功能: AI 对话、业务逻辑                                    │
│                                                             │
│  进程3: LangBot Input Handler                                │
│  - 端口: 8081                                               │
│  - 功能: 接收 LangBot webhook                                │
│                                                             │
│  进程4: LangBot Output Handler                               │
│  - 无端口 (后台轮询)                                          │
│  - 功能: 发送消息到 LangBot                                   │
│                                                             │
│  进程5: MongoDB                                              │
│  - 端口: 27017                                              │
│  - 功能: 数据存储                                            │
└─────────────────────────────────────────────────────────────┘
```

## 1. 端口分配方案

| 服务组件 | 端口 | 用途 | 访问方式 |
|---------|------|------|----------|
| LangBot 核心服务 | 5300 | API 服务 | 内部调用 |
| Coke 主服务 | 8080 | Web 服务 | 外部访问 |
| LangBot Webhook | 8081 | 接收消息 | LangBot 回调 |
| MongoDB | 27017 | 数据库 | 内部调用 |

## 2. 进程管理脚本

### 2.1 统一启动脚本

```bash
# 创建脚本 scripts/deploy_single_server.sh
```

### 2.2 服务停止脚本
```bash
# 统一停止脚本（自动检测部署模式）
./stop.sh
```

### 2.3 状态检查脚本
```bash
# 基础状态检查
./status.sh

# 详细状态检查（包含端口和连通性测试）
./status.sh --detailed
```

## 3. 配置文件调整

### 3.1 更新 conf/config.json
```json
{
  "langbot": {
    "enabled": true,
    "base_url": "http://127.0.0.1:5300",      // 本地 LangBot 服务
    "api_key": "lbk_single_server_key",       // 单服务器 API Key
    "webhook_port": 8081,                     // Webhook 接收端口
    "default_character_alias": "qiaoyun",
    "single_server_mode": true                // 标识单服务器模式
  }
}
```

### 3.2 环境变量配置 (.env)
```bash
# LangBot 配置
LANGBOT_BASE_URL=http://127.0.0.1:5300
LANGBOT_API_KEY=lbk_single_server_key
LANGBOT_WEBHOOK_PORT=8081

# MongoDB 配置
MONGODB_HOST=127.0.0.1
MONGODB_PORT=27017
MONGODB_NAME=mymongo

# 日志配置
LOG_LEVEL=INFO
LOG_DIR=./logs
```

## 4. 部署操作步骤

### 4.1 生产环境部署
```bash
# 1. 确保 LangBot 核心服务已在端口 5300 运行
# 提示: 可以使用 PM2 模式自动启动，或手动启动：
#   cd langbot-workdir && uvx langbot@latest

# 2. 准备环境
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 检查数据库中的 LangBot 平台配置（重要！）
python scripts/check_langbot_platform.py

# 如果检查失败，需要先配置平台信息：
# python add_feishu_platform.py  # 为角色添加飞书平台

# 4. 启动 Coke 相关服务（生产模式）
./start.sh --mode prod --check

# 5. 检查服务状态（支持详细模式）
./status.sh --detailed

# 6. 测试消息发送（可选）
python scripts/langbot_insert_pending_output.py \
  --bot-uuid "production-bot-uuid" \
  --target-type "person" \
  --target-id "test-user" \
  --text "Hello from single server!"
```

## 5. 进程管理

### 5.1 进程列表
```bash
# 查看所有相关进程
ps aux | grep -E "(langbot|mongo|agent_start)"

# 查看端口占用
netstat -tlnp | grep -E "(5300|8080|8081|27017)"
```

### 5.2 日志管理
```bash
# 查看所有日志
tail -f logs/*.log

# 查看特定服务日志
tail -f logs/langbot_input.log
tail -f logs/langbot_output.log
tail -f logs/langbot_core.log
```

## 6. 监控和维护

### 6.1 健康检查脚本
```bash
#!/bin/bash
# 健康检查脚本 scripts/health_check.sh

# 检查所有必要端口
ports=(5300 8081 27017)
for port in "${ports[@]}"; do
    if ! lsof -ti:$port > /dev/null; then
        echo "ERROR: Port $port is not in use"
        exit 1
    fi
done

# 检查 API 连通性
if ! curl -s http://localhost:5300/healthz > /dev/null; then
    echo "ERROR: LangBot API not responding"
    exit 1
fi

echo "All services healthy"
```

### 6.2 自动重启脚本
```bash
#!/bin/bash
# 自动重启脚本 scripts/auto_restart.sh

while true; do
    if ! bash scripts/health_check.sh; then
        echo "Services unhealthy, restarting..."
        bash scripts/stop_single_server.sh
        sleep 5
        bash scripts/deploy_single_server.sh
    fi
    sleep 60
done
```

## 7. 优势和注意事项

### 7.1 优势
- **简化部署**：所有服务在一台服务器上，便于管理
- **降低成本**：减少服务器资源需求
- **网络延迟低**：服务间通信无网络延迟
- **调试方便**：所有日志集中在一处

### 7.2 注意事项
- **资源竞争**：多个进程共享 CPU 和内存
- **单点故障**：服务器故障影响所有服务
- **端口冲突**：需要合理分配端口
- **扩展限制**：难以独立扩展单个服务

### 7.3 生产环境建议
- 使用 systemd 或 supervisor 管理进程
- 配置日志轮转避免磁盘空间不足
- 设置监控告警
- 定期备份 MongoDB 数据
- 使用反向代理 (nginx) 统一入口

## 8. 故障排查

### 8.1 常见问题
1. **端口冲突**：检查端口占用情况
2. **进程僵死**：使用 kill -9 强制终止
3. **日志文件过大**：配置日志轮转
4. **内存不足**：监控系统资源使用
5. **LangBot 平台未配置**：运行 `python scripts/check_langbot_platform.py` 检查

### 8.1.1 LangBot 平台配置问题

如果消息无法发送，可能是用户/角色缺少 LangBot 平台配置：

```bash
# 检查配置
python scripts/check_langbot_platform.py

# 如果角色缺少配置，添加平台
python add_feishu_platform.py

# 手动在 MongoDB 中添加配置示例：
# db.users.updateOne(
#   { name: "qiaoyun", is_character: true },
#   { $set: {
#       "platforms.langbot_feishu": {
#         "id": "qiaoyun-feishu",
#         "account": "qiaoyun-feishu",
#         "bot_uuid": "your-bot-uuid-here"
#       }
#     }
#   }
# )
```

### 8.2 调试命令
```bash
# 查看进程树
pstree -p | grep -E "(langbot|mongo|python)"

# 查看系统资源
htop
df -h
free -h

# 测试网络连接
curl -v http://localhost:5300/healthz
curl -v -X POST http://localhost:8081/langbot/webhook -d '{}'
```