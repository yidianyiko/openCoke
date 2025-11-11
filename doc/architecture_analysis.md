# Luoyun_project 架构设计说明书

## 1. 架构概述
- 系统定位与业务目标：
  - 面向企业与个人的智能助手中枢，统一接入微信/ecloud、GeWeChat 以及本地终端，提供文本/语音/图片等多模态能力。
  - 通过 Agent 链路完成“查询改写 → 语义检索 → 回复生成 → 细化与事后分析”，支持日常任务自动化与内容生产。
  - 以 MongoDB 为持久化与调度基座，保证消息有序处理与结果可靠送达。
- 架构设计原则与约束：
  - 简单单体优先：后端为 Python 单体服务，分为入站、核心处理、出站三类进程，避免过早复杂化。
  - 异步与幂等：通过会话级分布式锁与消息状态机控制并发与重入，保证事务性与最终一致性。
  - 可观测性与安全：统一日志，关键外部服务以环境变量管理密钥；后续可扩展签名校验、速率限制与指标采集。
  - 松耦合适配：各平台消息以适配层标准化，内部以统一的 Input/OutputMessage 结构驱动处理与发送。
- 关键术语与概念：
  - Connector：平台接入层，包含入站控制器与出站发送器（ecloud、GeWeChat、Terminal）。
  - Adapter：消息标准化与反向适配（`connector/ecloud/ecloud_adapter.py`）。
  - Handler：核心处理调度器（`qiaoyun/runner/qiaoyun_handler.py:44`），负责选取待处理消息、构建上下文、调用 Agent 并落库结果。
  - Agent：执行特定任务的处理单元（重写、检索、生成、细化、事后分析），同步/异步基类见 `framework/agent/base_agent.py:40/169`。
  - Context：会话上下文聚合（`qiaoyun/runner/context.py:18`），包含关系、历史与当日信息。
  - InputMessage/OutputMessage：标准化入/出站消息结构（写库见 `connector/ecloud/ecloud_input.py:159`、`qiaoyun/util/message_util.py:174`）。
  - 状态机：`pending/handling/handled/failed/hold`（推进与清理见 `qiaoyun/runner/qiaoyun_handler.py:260-336`）。

## 2. 架构视图
- 逻辑视图（组件与交互）：
  ```mermaid
  flowchart LR
    EC[Ecloud 平台] -->|HTTP POST /message| IN[入站控制器<br/>Flask]
    IN --> AD[适配器<br/>Std 化]
    AD --> IM[(MongoDB<br/>inputmessages)]
    IM --> HD[核心 Handler]
    HD --> CTX[上下文构建]
    CTX --> AG1[重写 Agent]
    AG1 --> AG2[检索 Agent]
    AG2 --> AG3[回复生成 Agent]
    AG3 --> AG4[细化/事后分析]
    AG4 --> OM[(MongoDB<br/>outputmessages)]
    OM --> OUT[出站发送器]
    OUT --> EC
    subgraph 外部服务
      LLM[LLM/Ark/DashScope]
      V2T[语音识别 NLS]
      T2V[语音合成]
      IMG[图像生成/识别]
      OSS[对象存储]
    end
    AG2 --> LLM
    AG3 --> LLM
    OUT --> T2V
    OUT --> OSS
    IN -.-> GeW[GeWeChat 通道]
    GeW -->|输入/输出| HD
  ```
- 端到端序列图（ecloud 主链路）：
  ```mermaid
  sequenceDiagram
    participant EC as Ecloud 平台
    participant IN as 入站(Flask)
    participant AD as 适配器
    participant DB as MongoDB
    participant HD as Handler
    participant AG as Agent 链
    participant OUT as 出站发送
    EC->>IN: POST /message
    IN->>AD: 原始消息
    AD->>DB: insert inputmessages
    HD->>DB: 选取 pending + 会话加锁
    HD->>AG: 构建上下文并触发处理
    AG->>DB: insert outputmessages
    OUT->>DB: 轮询到期 pending
    OUT->>EC: 发送文本/语音/图片
    OUT->>DB: 标记 handled/failed
  ```
- 开发视图（代码结构与模块组织）：
  - `connector/ecloud`：`ecloud_input.py:14` Flask 应用、`ecloud_output.py:30` 出站轮询、`ecloud_adapter.py:54/170` 标准化/反适配、`ecloud_api.py` 平台调用。
  - `connector/gewechat`：`gewechat_connector.py:61/83` 输入输出处理，内部集合命名为 `input_messages`/`output_messages`。
  - `qiaoyun/runner`：`qiaoyun_handler.py:44` 主处理、`qiaoyun_background_handler.py` 后台、`context.py:18` 上下文、`qiaoyun_runner.py` 并发调度入口。
  - `qiaoyun/agent`：聊天与背景/日常 Agent（重写/检索/生成/细化/事后分析）。
  - `dao`：`mongo.py:25/109/247/290` CRUD、向量检索与组合搜索；`lock.py:21/75` 会话锁。
  - `framework/agent` 与 `framework/tool`：Agent 基类、LLM 客户端、语音/图像/搜索等工具。
  - `entity/message.py`：消息结构；`util/*`：Embedding/OSS/时间等工具。
- 部署视图（物理方案）：
  - 进程划分：
    - 入站服务：`python connector/ecloud/ecloud_input.py`（默认端口 `8080`）。
    - 核心处理：`python -m qiaoyun.runner.qiaoyun_runner`（并发主/后台处理）。
    - 出站发送：`python connector/ecloud/ecloud_output.py`（异步轮询）。
  - 外部依赖：`MongoDB`（文档建议 `docker run mongo:5.0.5`）、LLM 平台（Ark/DashScope）、阿里云 NLS/OSS。
  - 网络与端口：入站暴露 HTTP，核心处理与出站内部通信依赖 Mongo；与平台的调用通过公网 API。
  - 可选容器化：当前仓库未提供 Dockerfile/Compose/K8s；可按进程拆分为三个容器，统一配置与日志。
- 数据视图（存储与处理）：
  - 集合：`users`、`conversations`、`relations`、`dailynews`、`embeddings`、`inputmessages`、`outputmessages`、`locks`；GeWeChat 使用 `input_messages`/`output_messages`。
  - 索引：向量库文本/稀疏索引（`dao/mongo.py:118-127`）；锁集合唯一索引（`dao/lock.py:18-19`）。
  - 处理流程：入站写 `inputmessages` → Handler 读取并加锁 → Agent 链生成结果 → 写 `outputmessages` → 出站轮询发送并状态更新。

## 3. 技术选型
- 核心技术栈说明：
  - 语言与运行时：Python 3.11。
  - Web/接口：Flask（轻量、生态成熟）。
  - 数据库：MongoDB + `pymongo`（灵活 Schema，易于消息与上下文存储）。
  - 异步与调度：`asyncio`（轮询与并发处理）。
  - LLM 与推理：火山方舟 Ark、阿里云 DashScope（本地化与稳定性），仓库中亦包含 OpenAI 适配。
  - 语音/图像：阿里云 NLS SDK、`pydub`/`silk-python`/`pilk`；图片生成与识别工具封装于 `framework/tool` 与 `qiaoyun/tool`。
  - 对象存储：阿里云 OSS。
- 框架与工具选择理由：
  - Flask 满足入站控制器需求，易于快速暴露路由与中间件。
  - MongoDB 在会话/消息/向量等多类型数据上具备高自由度，结合锁与状态机满足最终一致性。
  - Ark/DashScope 提供国内可用的 LLM 能力，延迟与成本可控；NLS 与 OSS 是语音与媒体的标准配套。
  - 单体 + 进程化拆分更易部署与运维，降低资源与编排复杂度。
- 关键技术决策点：
  - 无独立 MQ，改用 Mongo 状态与时间戳驱动调度；简化架构但需要严格状态推进与重试机制。
  - 会话级锁保证同一会话的消息串行处理，减少上下文竞争与顺序错乱。
  - 适配层统一消息结构，降低平台差异导致的上游复杂度。
  - Agent 链可插拔扩展，允许在不同场景增/减环节（如细化/事后分析）。
- 技术债务说明：
  - 配置与启动：缺少统一的 `conf/config.json` 示例、启动脚本与容器化清单；需补充样例与部署自动化。
  - 命名与封装：GeWeChat 集合命名与主线不一致，且独立 Mongo 封装，建议统一。
  - 可观测性：缺少指标/追踪与失败告警；建议接入 Prometheus/ELK 并完善重试策略。
  - API 规范：未提供 OpenAPI/Swagger；建议定义入站/内部接口规范以便联调与测试。
  - 安全：入站路由缺少签名校验与速率限制；建议按环境配置白名单与签名。

## 目录结构
toolName: view_folder
            
status: success
          
/home/ydyk/workspace/active-projects/coke
          

        
            
toolName: file_search
            
status: success
          
file_pattern: /*
          
**总体划分**
- `connector/` 平台接入层：ecloud、GeWeChat、Terminal 入/出站控制器与消息适配
- `qiaoyun/` 核心业务域：处理调度、上下文、Agent 链、多模态工具
- `framework/` 通用能力层：Agent 基类与 LLM/语音/图像/搜索工具
- `dao/` 数据访问层：MongoDB 封装、锁、会话与用户数据访问
- `entity/` 领域实体：消息结构与持久化
- `util/` 通用工具：Embedding、OSS、时间等
- `conf/` 配置管理：环境配置读取与合并
- `doc/` 文档：架构、部署与数据库说明
- 依赖与脚本：`requirements.txt`、`qiaoyun/requirements.txt`

**接入层 connector/**
- `connector/ecloud/` 微信 ecloud 通道
  - `ecloud_input.py` 入站控制器（Flask 路由）`connector/ecloud/ecloud_input.py:14`
  - `ecloud_output.py` 出站轮询与发送 `connector/ecloud/ecloud_output.py:20`
  - `ecloud_adapter.py` 标准化与反适配
  - `ecloud_api.py` 平台 API 封装
- `connector/gewechat/` GeWeChat 通道
  - `gewechat_connector.py` 输入/输出处理与集合访问
  - `common/` 通道常量、模型名枚举（含 OpenAI 模型标识）
  - `gewechat_channel.py`、`reply.py`、`context.py` 辅助逻辑
- `connector/terminal/` 终端通道
  - `terminal_input.py`、`terminal_output.py` 本地测试入/出站

**核心域 qiaoyun/**
- `qiaoyun/runner/`
  - `qiaoyun_handler.py` 主处理流程与状态推进 `qiaoyun/runner/qiaoyun_handler.py:44`
  - `context.py` 会话上下文构建 `qiaoyun/runner/context.py:18`
  - `qiaoyun_background_handler.py` 后台处理
  - `qiaoyun_runner.py` 并发调度入口
- `qiaoyun/agent/` 业务 Agent
  - 聊天链路：改写/检索/生成/细化/事后分析 `qiaoyun/agent/qiaoyun_chat_agent.py:33`
  - `daily/` 日常任务型 Agent
  - `background/` 背景与未来响应 Agent
- `qiaoyun/tool/` 多模态工具
  - `voice.py` 语音生成与发送
  - `image.py` 图片生成与上传
- `qiaoyun/util/`
  - `message_util.py` 出站消息写库与上下文封装 `qiaoyun/util/message_util.py:174`

**通用能力 framework/**
- `framework/agent/`
  - `base_agent.py` Agent 状态枚举与同步/异步基类 `framework/agent/base_agent.py:40`、`framework/agent/base_agent.py:169`
  - `llmagent/` 单轮 LLM Agent 封装、Ark/DashScope 适配
- `framework/tool/`
  - `voice2text/` 阿里云 NLS 语音识别
  - `text2voice/` 语音合成（含 minimax 封装）
  - `text2image/` 文生图工具
  - `image2text/` 图像识别（含 Ark 封装）
  - `search/aliyun.py` 兼容 OpenAI 调用阿里云搜索

**数据访问 dao/**
- `mongo.py` CRUD 与向量检索、组合搜索 `dao/mongo.py:25`、`dao/mongo.py:247`、`dao/mongo.py:290`
- `lock.py` 会话级分布式锁（唯一索引）`dao/lock.py:18`、`dao/lock.py:21`
- `conversation_dao.py` 会话读写与创建
- `user_dao.py` 用户与角色数据访问

**领域实体 entity/**
- `message.py` 标准化输入/输出消息结构与集合操作

**工具与配置**
- `util/` Embedding、OSS、时间工具等
- `conf/config.py` 读取 `conf/config.json` 并按环境覆盖
- `requirements.txt`、`qiaoyun/requirements.txt` 依赖管理
- `doc/architecture_analysis.md` 架构说明书（已更新）、部署与数据库文档

**入口与运行**
- 入站服务：`python connector/ecloud/ecloud_input.py`
- 核心处理：`python -m qiaoyun.runner.qiaoyun_runner`
- 出站发送：`python connector/ecloud/ecloud_output.py`

## 附：运行与运维要点
- 启动命令：
  - 入站：`python connector/ecloud/ecloud_input.py`
  - 核心处理：`python -m qiaoyun.runner.qiaoyun_runner`
  - 出站：`python connector/ecloud/ecloud_output.py`
- 关键环境变量与配置：
  - `ARK_API_KEY`、`DASHSCOPE_API_KEY`、OSS/NLS 相关密钥；
  - `CONF` 指向环境配置（默认 `dev`）；`DISABLE_DAILY_TASKS` 控制繁忙期任务。
- 数据维护：定期清理临时目录 `qiaoyun/temp/*`、检查出站失败队列、整理对象存储残留。

本说明书依据当前仓库代码与文档编制，内容完整、逻辑清晰，可作为设计/开发/部署的统一参考。

