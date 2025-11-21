# Coke-Max 详细架构分析文档
>
> 本文档基于 `coke-max/` 目录的实际代码进行深入分析，遵循《Luoyun Project 详细架构分析文档》的章节与格式。
>
> 文档版本：v1.0
>
---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构设计](#2-整体架构设计)
3. [目录结构详解](#3-目录结构详解)
4. [核心模块分析](#4-核心模块分析)
5. [数据流与消息流](#5-数据流与消息流)
6. [类关系图](#6-类关系图)
7. [数据库设计](#7-数据库设计)
8. [关键技术实现](#8-关键技术实现)
9. [部署与运维](#9-部署与运维)
10. [重构建议](#10-重构建议)

---

## 1. 项目概述

### 1.1 项目定位

Coke-Max 是 Luoyun/COKE 角色的强化实现，聚焦于对话回复与主动消息（提醒、关心）。在不改动平台连接器的前提下，通过智能体化编排实现：
- 识别用户任务并结构化提取（是否需要提醒、预计时长）
- 到时主动提醒并生成上下文相关的文案
- 根据不活跃状态主动 Check-in 关心用户

### 1.2 核心特性

- 对话编排智能体：主控聊天流程，统一从上下文产出消息
- 结构化输出：从回复里抽取任务、提醒意图与时长
- 主动消息：计时到点生成提醒文案；不活跃触发关心
- 短语块规范：所有输出均遵守 ≤10 字短语块，用 `<换行>` 分隔
- 后台轮询：守护线程周期检查到期提醒与不活跃用户

### 1.3 技术栈

- 语言：Python 3.x
- 智能体框架：`framework.agent.BaseAgent`、`framework.agent.llmagent.DouBaoLLMAgent`
- 大模型：`deepseek-v3-1-terminus`（通过 DouBaoLLMAgent 配置）
- 数据库：MongoDB（通过项目级 `mongo_db` 适配器）
- 并发与调度：`threading` 守护线程 + 轮询
- 日志：`logging`

---

## 2. 整体架构设计

### 2.1 架构分层

```
┌─────────────────────────────────────────────┐
│                Prompt 层                    │
│  system / personality / task / context     │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│               Agent 智能体层                │
│ CokeChat / CokeResponse / Proactive / ...  │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│            Scheduler 调度与轮询层           │
│ ReminderScheduler / BackgroundRunner        │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│                DAO / Mongo 访问             │
│ coke_reminders / coke_conversations / ...   │
└─────────────────────────────────────────────┘
                     ↕
┌─────────────────────────────────────────────┐
│             上层连接器与API（外部）         │
│  发送消息、拉取 pending reminders           │
└─────────────────────────────────────────────┘
```

### 2.2 核心设计模式

- Agent Pipeline：主控智能体编排子智能体，产出状态与上下文
- Context 传递：统一字典承载 `user_message`、`conversation_history`、AI 产出等
- 结构化输出：通过 JSON Schema 让 LLM 返回结构化字段并写入 `context`
- 守护线程轮询：到期提醒即时生成文案并入内存队列，标记数据库状态

---

## 3. 目录结构详解

### 3.1 根目录结构

```
coke-max/
├── agent/                      # 对话与主动消息的各类智能体
│   ├── coke_chat_agent.py      # 主控聊天编排
│   ├── coke_response_agent.py  # 文本回复生成（结构化输出）
│   ├── coke_proactive_agent.py # 主动消息：提醒 / check-in
│   ├── coke_checkin_agent.py   # 简短关心消息（≤30字）
│   └── coke_reminder_message_agent.py # 单条提醒文案生成
├── prompt/                     # 提示词模板集
│   ├── system_prompt.py
│   ├── personality_prompt.py
│   ├── task_prompt.py
│   └── context_prompt.py
├── scheduler/                  # 提醒调度与后台轮询
│   ├── reminder_scheduler.py
│   └── background_runner.py
├── role/
│   └── character_basics.txt    # 角色基本信息
└── __init__.py
```

### 3.2 各目录详细说明

- `agent/`：面向场景的智能体集合，统一遵循短语块输出与上下文写回
- `scheduler/`：面向提醒业务的 CRUD、到期筛选与后台守护线程
- `prompt/`：系统/人格/任务/上下文提示词，按场景拼装
- `role/`：角色元信息

---

## 4. 核心模块分析

- CokeChatAgent（主控聊天）
  - 入口编排，调用 `CokeResponseAgent`，最终产出 `AgentStatus.MESSAGE`
  - 代码：`coke-max/agent/coke_chat_agent.py:29-47`

- CokeResponseAgent（回复生成，结构化）
  - 继承 `DouBaoLLMAgent`，组装人格 + 任务提示词，定义 JSON Schema
  - 结构化字段：`response/has_task/task_description/task_duration_minutes/needs_reminder`
  - `_posthandle` 写入 `context`：`coke_response` 等
  - 代码：`coke-max/agent/coke_response_agent.py:46-87`, `90-110`

- CokeProactiveAgent（主动消息）
  - `message_type` 分支构建提醒/关心上下文，拼接人格提示词
  - 产出 `reminder_message` 或 `checkin_message`
  - 代码：`coke-max/agent/coke_proactive_agent.py:35-74`, `76-98`, `100-126`, `128-146`

- CokeCheckInAgent（不活跃关心）
  - 生成≤30字的关心消息，写入 `context['checkin_message']`
  - 代码：`coke-max/agent/coke_checkin_agent.py:37-69`, `71-78`

- CokeReminderMessageAgent（提醒文案）
  - 基于任务描述生成≤40字的提醒短文案
  - 代码：`coke-max/agent/coke_reminder_message_agent.py:34-68`, `70-77`

- ReminderScheduler（提醒调度）
  - 创建提醒：插入 `coke_reminders`（`status=pending`，ISO 时间）
  - 到期筛选：解析 ISO 字符串并与当前时间比较
  - 标记发送：更新 `status=sent` 与 `sent_at`
  - 代码：`coke-max/scheduler/reminder_scheduler.py:23-42`, `43-73`, `75-83`

- BackgroundReminderRunner（后台轮询）
  - 周期检查到期提醒 → 生成文案 → 入 `pending_reminders` 内存队列 → 标记已发
  - 检查不活跃用户（>4h）→ 1 小时节流 → 入队立即 Check-in
  - 队列清理：首次拉取 60 秒后过期清除
  - 代码：`coke-max/scheduler/background_runner.py:59-83`, `98-153`, `154-203`, `204-240`

---

## 5. 数据流与消息流

### 5.1 聊天回复流程

1. 上层连接器收集 `user_message` 与 `conversation_history`
2. 构造 `context`，调用 `CokeChatAgent.run()`
3. `CokeResponseAgent` 生成结构化回复并写回 `context['coke_response']`
4. `CokeChatAgent` 产出最终消息（短语块格式）

### 5.2 提醒消息流程

1. 业务侧根据 `needs_reminder` 与 `task_duration_minutes` 调用 `ReminderScheduler.create_reminder`
2. 后台 `BackgroundReminderRunner` 周期检查到期提醒
3. 到期时即时用 `CokeProactiveAgent` 生成提醒文案，加入 `pending_reminders`
4. 标记数据库提醒为 `sent`
5. 上层 API/连接器拉取 `pending_reminders` 并发送到平台

### 5.3 不活跃关心流程

1. 后台每轮检查 `user_activity` 集合的 `last_message_time`
2. 超过 4 小时且 1 小时内未关心 → 立即入队 Check-in 消息
3. 上层拉取后发送（同时更新 `last_checkin_time`）

---

## 6. 类关系图

```
BaseAgent (framework)
└── CokeChatAgent
    └── 调用 → CokeResponseAgent : DouBaoLLMAgent ↑
DouBaoLLMAgent (framework)
├── CokeResponseAgent
├── CokeProactiveAgent
├── CokeCheckInAgent
└── CokeReminderMessageAgent

ReminderScheduler ↔ MongoDB
BackgroundReminderRunner ↔ ReminderScheduler
BackgroundReminderRunner → CokeProactiveAgent（生成提醒文案）
```

---

## 7. 数据库设计

### 7.1 集合与字段

- `coke_reminders`
  - `user_id`：用户标识
  - `task_description`：任务描述
  - `reminder_time`：ISO 字符串（到点时间）
  - `created_at`：ISO 字符串
  - `status`：`pending | sent`
  - `message`：提醒文案（到点后生成）

- `coke_conversations`
  - 用于拼接最近上下文：`user/coke/timestamp` 等

- `user_activity`
  - `user_id`、`last_message_time`、`last_checkin_time`

### 7.2 索引建议

- `coke_reminders(user_id, reminder_time, status)` 复合索引，加速到期筛选与用户视图
- `coke_conversations(user_id, timestamp)` for 最近上下文聚合
- `user_activity(user_id)` 唯一索引，保证单记录管理

### 7.3 约束与一致性

- 时间统一采用 ISO 字符串；建议落地时规范时区（UTC+8 或 UTC）
- 发送标记与入队保持幂等（根据 `_id` 防重复）

---

## 8. 关键技术实现

- 结构化输出（回复识别任务）
  - JSON Schema 让 LLM 返回 `has_task/needs_reminder/task_duration_minutes`（`coke-max/agent/coke_response_agent.py:50-75`）
  - `_posthandle` 写回 `context`，并日志输出（`coke-max/agent/coke_response_agent.py:89-110`）

- 主动提醒文案生成
  - 到点时才生成，避免预先固定文案（`coke-max/scheduler/background_runner.py:65-83`）
  - 最近对话上下文注入（`coke-max/scheduler/background_runner.py:103-126`）

- 不活跃检测与节流
  - 4 小时不活跃触发；1 小时节流避免骚扰（`coke-max/scheduler/background_runner.py:154-199`）

- 内存队列与过期清理
  - 首次拉取后保留 60 秒，随后清理（`coke-max/scheduler/background_runner.py:227-239`）

- 短语块输出规范
  - 人格提示词统一限制 ≤10 字，每段 `<换行>`（`coke-max/prompt/personality_prompt.py:9-28`）

---

## 9. 部署与运维

- 运行后台提醒轮询
  - 注入 `mongo_db` 适配器，构造 `ReminderScheduler`
  - `BackgroundReminderRunner(reminder_scheduler, check_interval=30).start()` 启动守护线程

- 与上层集成
  - 上层连接器/服务定期调用 `get_pending_reminders_for_user(user_id)` 拉取队列并发送
  - 对话侧调用 `CokeChatAgent(context).run()` 获取 `context['coke_response']`

- 配置与密钥
  - 模型与提示词在代码内配置；API Key 由 `DouBaoLLMAgent` 内部统一管理（项目级配置）

- 监控与日志
  - 关键事件均有日志输出；建议在生产环境开启文件日志与指标埋点

---

## 10. 重构建议

- 配置化与解耦
  - 将模型名称、短语块限制、检查间隔抽取到配置文件
  - 统一上下文键命名约定（`coke_response/reminder_message/checkin_message`）

- 稳定性与一致性
  - 时间与时区统一封装；为到期筛选添加健壮解析与异常告警
  - `pending_reminders` 内存队列支持持久化或 Redis，避免进程丢失

- 体验与质量
  - 增加单元测试与集成测试：结构化输出解析、到期提醒流程、不活跃节流
  - 优化提醒生成的上下文检索策略（更丰富的最近对话聚合）

- 性能与扩展
  - 为提醒与不活跃检查增加批量处理与限流
  - 对集合增加必要索引与 TTL（如历史对话的归档策略）

---

以上分析覆盖 `coke-max/` 的组件边界、数据流与集成点，可直接作为后续重构与对接的技术依据。