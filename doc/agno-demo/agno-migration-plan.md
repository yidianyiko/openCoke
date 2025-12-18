# Agent 框架迁移方案：从自研框架到 Agno

> 版本：v1.8  
> 日期：2025-12-04  
> 作者：架构组  
> 状态：评审中

---

## 目录

1. [概述](#1-概述)
2. [原系统需求分析](#2-原系统需求分析)
3. [现有架构分析](#3-现有架构分析)
4. [目标架构设计](#4-目标架构设计)
5. [概要设计](#5-概要设计)
6. [详细设计](#6-详细设计)
7. [迁移计划](#7-迁移计划)
8. [风险评估与应对](#8-风险评估与应对)
9. [附录](#9-附录)

---

## 1. 概述

### 1.1 背景

当前系统采用自研的 Agent 框架，包含 `BaseAgent`、`BaseSingleRoundLLMAgent` 等基础组件。
随着业务复杂度增加，自研框架在以下方面面临挑战：

- 维护成本高，Bug 修复周期长
- 缺乏成熟的 Agent 编排能力
- 模型切换不够灵活
- 缺少内置的 Memory、Knowledge 等高级能力

### 1.2 目标

将 Framework 层和 Agent 层迁移至 [Agno](https://docs.agno.com) 框架，实现：

- 减少自研代码维护成本
- 提升系统稳定性
- 获得更灵活的模型切换能力
- 为未来扩展 Memory、Knowledge 等能力奠定基础

### 1.3 范围

| 层级 | 迁移策略 |
|------|----------|
| Connector 层 | **保留** - 不在本次迁移范围 |
| Runner 层 | **适配** - 修改 Agent 调用方式 |
| Agent 层 | **重构** - 迁移至 Agno Agent/Team |
| Framework 层 | **替换** - 由 Agno 框架替代 |

### 1.4 约束条件

- 使用 Agno 原生支持的模型 (DeepSeek)，不再使用火山引擎
- 暂不支持 voice2text / text2voice 功能
- Connector 层保持不变


---

## 2. 原系统需求分析

### 2.1 功能需求清单

在进行架构重构前，必须明确原系统支持的功能需求，确保迁移后不影响现有功能。

> 完整需求清单参见

#### 2.1.1 消息处理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-001 | 消息接收 | 接收微信消息并标准化存储到 MongoDB | Connector 层保留 | ✅ 保留 |
| FR-002 | 消息发送 | 轮询 MongoDB 并通过 ecloud API 发送消息 | Connector 层保留 | ✅ 保留 |
| FR-003 | 文本消息处理 | 接收和发送文本消息 | Connector 层保留 | ✅ 保留 |
| FR-004 | 语音消息接收 | 接收语音消息并转文字（voice2text） | Tool 封装 | ✅ 支持 |
| FR-005 | 语音消息发送 | 文字转语音并发送（text2voice，MiniMax） | Tool 封装 | ✅ 支持 |
| FR-006 | 图片消息接收 | 接收图片并识别内容（image2text，豆包视觉模型） | Tool 封装 | ✅ 支持 |
| FR-007 | 图片消息发送 | 发送图片消息（从相册或生成） | Tool 封装 | ✅ 支持 |
| FR-008 | 引用消息处理 | 解析和处理微信引用消息 | Connector 层保留 | ✅ 支持 |
| FR-009 | 消息打断 | 新消息到达时中断当前处理，避免对话上下文割裂（详见 FR-009 详细说明） | Runner 层控制 | ✅ 迁移 |

#### 2.1.2 对话处理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-010 | 问题重写 | 对用户输入进行语义理解和查询重写 | Agent 重写 | ✅ 迁移 |
| FR-011 | 上下文检索 | 向量检索角色设定、用户资料、知识库 | Tool 封装 | ✅ 迁移 |
| FR-012 | 对话生成 | 基于角色人设生成多模态回复 | Agent 重写 | ✅ 迁移 |
| FR-013 | 回复优化 | R1/DeepSeek 模型优化回复质量 | 不迁移 | ❌ 取消（随机触发机制不稳定，迁移后主模型质量已足够） |
| FR-014 | 后处理分析 | 总结对话，更新用户/角色记忆 | Agent 重写 | ✅ 迁移 |
| FR-015 | 对话历史管理 | 维护和截断对话历史（最大50轮） | DAO 层保留 | ✅ 保留 |
| FR-016 | 分段消息发送 | 支持将回复拆分为多条消息发送 | Runner 层保留 | ✅ 支持 |

#### 2.1.3 提醒管理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-017 | 提醒识别 | 从用户消息中识别提醒意图（LLM+规则） | Agent 重写 | ✅ 迁移 |
| FR-018 | 提醒创建 | 创建新的提醒任务 | Tool 封装 | ✅ 迁移 |
| FR-019 | 提醒更新 | 修改提醒时间/内容/周期 | Tool 封装 | ✅ 迁移 |
| FR-020 | 提醒删除 | 取消/删除提醒 | Tool 封装 | ✅ 迁移 |
| FR-021 | 提醒列表 | 查看用户的提醒列表 | Tool 封装 | ✅ 迁移 |
| FR-022 | 提醒触发 | 定时触发提醒并发送消息 | 独立服务保留 | ✅ 迁移 |
| FR-023 | 周期提醒 | 支持每日/每周/每月/每年/间隔分钟周期 | DAO 层保留 | ✅ 迁移 |
| FR-024 | 相对时间解析 | 解析"30分钟后"、"明天"等相对时间 | Util 层保留 | ✅ 支持 |

#### 2.1.4 关系管理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-025 | 亲密度管理 | 维护用户与角色的亲密度（0-100） | DAO 层保留 | ✅ 迁移 |
| FR-026 | 信任度管理 | 维护用户与角色的信任度（0-100） | DAO 层保留 | ✅ 迁移 |
| FR-027 | 反感度管理 | 维护用户与角色的反感度（0-100） | DAO 层保留 | ✅ 迁移 |
| FR-028 | 关系衰减 | 定期降低亲密度/信任度（约8.4小时一次） | 独立服务保留 | ✅ 支持 |
| FR-029 | 用户拉黑 | 反感度达到100时拉黑用户 | DAO 层保留 | ✅ 支持 |
| FR-030 | 用户昵称管理 | 记录用户真名和昵称 | DAO 层保留 | ✅ 支持 |
| FR-031 | 用户印象描述 | 维护角色对用户的印象描述 | DAO 层保留 | ✅ 支持 |

#### 2.1.5 角色状态模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-032 | 角色状态管理 | 维护角色当前位置、行动、状态 | DAO 层保留 | ✅ 支持 |
| FR-033 | 忙闲状态 | 根据日程脚本切换空闲/繁忙/睡觉状态 | 独立服务保留 | ✅ 支持 |
| FR-034 | 消息Hold | 角色繁忙时暂存消息，空闲后处理 | Runner 层保留 | ✅ 支持 |
| FR-035 | 角色目标管理 | 维护角色的长期/短期目标和态度 | DAO 层保留 | ✅ 支持 |

#### 2.1.6 主动消息模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-036 | 未来消息规划 | 规划角色未来主动发送的消息 | Agent 重写 | ✅ 支持 |
| FR-037 | 主动消息触发 | 定时触发角色主动消息（约1.5小时检查） | 独立服务保留 | ✅ 支持 |
| FR-038 | 主动消息生成 | 基于上下文生成主动消息内容 | Agent 重写 | ✅ 支持 |
| FR-039 | 主动消息频率控制 | 防止过度骚扰用户的频率限制 | DAO 层保留 | ✅ 支持 |

#### 2.1.7 每日任务模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-040 | 每日新闻搜索 | 搜索与角色兴趣相关的新闻资讯 | 不迁移 | ❌ 取消（本次迁移不包含每日任务模块） |
| FR-041 | 知识学习 | 从新闻中提取知识点存入知识库 | 不迁移 | ❌ 取消（本次迁移不包含每日任务模块） |
| FR-042 | 每日剧本生成 | 生成角色每日活动时间表 | 不迁移 | ❌ 取消（本次迁移不包含每日任务模块） |
| FR-043 | 图片生成 | 基于活动剧本生成角色照片（LibLib） | 不迁移 | ❌ 取消（本次迁移不包含每日任务模块） |
| FR-044 | 朋友圈文案生成 | 为生成的照片生成朋友圈文案 | 不迁移 | ❌ 取消（本次迁移不包含每日任务模块） |

#### 2.1.8 图片处理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-045 | 图片识别 | 使用豆包视觉模型识别图片内容 | Tool 封装 | ✅ 支持 |
| FR-046 | 文生图 | 使用 LibLib API 生成角色照片 | Tool 封装 | ✅ 支持 |
| FR-047 | 图片上传 | 上传图片到 OSS 并获取URL | Util 层保留 | ✅ 支持 |
| FR-048 | 图片下载 | 从URL下载图片到本地 | Util 层保留 | ✅ 支持 |
| FR-049 | 相册管理 | 维护角色的照片库（向量检索） | 不迁移 | ❌ 取消（本次迁移不包含相册检索功能） |
| FR-050 | 照片发送频率控制 | 防止重复发送相同照片 | DAO 层保留 | ✅ 支持 |

#### 2.1.9 语音处理模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-051 | 语音转文字 | 阿里云 ASR 实时语音识别 | Tool 封装 | ✅ 支持 |
| FR-052 | 文字转语音 | MiniMax T2A 语音合成 | Tool 封装 | ✅ 支持 |
| FR-053 | 语音情感 | 支持多种情感色彩（高兴/悲伤/愤怒等） | Tool 封装 | ✅ 支持 |
| FR-054 | 音频格式转换 | PCM/SILK/WAV 格式互转 | Util 层保留 | ✅ 支持 |

#### 2.1.10 知识库模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-055 | 向量存储 | 使用阿里云 Embedding 存储知识 | DAO 层保留 | ✅ 支持 |
| FR-056 | 向量检索 | 基于语义相似度检索知识 | Tool 封装 | ✅ 支持 |
| FR-057 | 角色全局设定 | 存储角色公开人物设定 | DAO 层保留 | ✅ 支持 |
| FR-058 | 角色私有设定 | 存储角色与特定用户的私有设定 | DAO 层保留 | ✅ 支持 |
| FR-059 | 用户资料 | 存储用户个人资料 | DAO 层保留 | ✅ 支持 |
| FR-060 | 角色知识 | 存储角色的知识和技能 | DAO 层保留 | ✅ 支持 |
| FR-061 | 角色照片库 | 存储角色照片及描述 | DAO 层保留 | ✅ 支持 |

#### 2.1.11 管理功能模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-062 | 硬编码指令 | 管理员特殊指令（朋友圈/删除/重新生成） | Runner 层保留 | ✅ 支持 |
| FR-063 | 朋友圈发布 | 发布照片到微信朋友圈 | Tool 封装 | ✅ 支持 |
| FR-064 | 照片删除 | 删除指定照片 | Tool 封装 | ✅ 支持 |
| FR-065 | 每日任务重新生成 | 重新生成当日任务 | 不迁移 | ❌ 取消（依赖每日任务模块） |

#### 2.1.12 系统基础模块

| 需求编号 | 功能模块 | 功能描述 | 迁移策略 | 迁移后支持 |
|----------|----------|----------|----------|------------|
| FR-066 | 会话锁管理 | MongoDB 分布式锁防止并发冲突 | DAO 层保留 | ✅ 保留 |
| FR-067 | 错误重试 | Agent 执行失败时自动重试 | Agno 内置 | ✅ Agno 内置 |
| FR-068 | 多连接器支持 | 支持 ecloud/terminal 多种连接器 | Connector 层保留 | ✅ 保留 |
| FR-069 | 配置管理 | JSON 配置文件管理 | Conf 层保留 | ✅ 保留 |

### 2.2 非功能需求

| 需求编号 | 类型 | 描述 | 迁移后支持 |
|----------|------|------|------------|
| NFR-001 | 性能 | 消息响应 P99 < 20s | ✅ 需验证 |
| NFR-002 | 可用性 | 系统错误率 < 1% | ✅ 需验证 |
| NFR-003 | 可扩展性 | 支持多角色、多用户并发 | ✅ 保留 |
| NFR-004 | 可维护性 | 代码结构清晰，易于扩展 | ✅ 改善 |
| NFR-005 | 安全性 | 用户拉黑机制、管理员权限控制 | ✅ 保留 |

### 2.3 需求迁移策略汇总

| 迁移策略 | 涉及需求数 | 说明 |
|----------|-----------|------|
| Connector 层保留 | 5 | 消息收发相关，不涉及 Agent 框架 |
| Runner 层保留 | 4 | 消息打断、分段发送、消息Hold、硬编码指令 |
| DAO 层保留 | 17 | 数据存储相关，不涉及 Agent 框架 |
| Util 层保留 | 4 | 工具函数，不涉及 Agent 框架 |
| Conf 层保留 | 1 | 配置管理 |
| 独立服务保留 | 4 | 定时任务服务（提醒触发、关系衰减、主动消息、忙闲状态） |
| Agent 重写 | 6 | 需要迁移到 Agno Agent（问题重写、对话生成、后处理分析、提醒识别、未来消息规划、主动消息生成） |
| Tool 封装 | 9 | 需要封装为 Agno Tool |
| Agno 内置 | 1 | 错误重试 |
| 不迁移 | 8 | 回复优化 FR-013、每日任务模块 FR-040~044、相册管理 FR-049、每日任务重新生成 FR-065 |

### 2.4 需求影响评估

#### 2.4.1 FR-009 消息打断机制详细说明

**业务场景**：

用户在微信上和 AI 角色聊天时，可能在系统处理消息期间发送多条消息：

```
用户: 你好 (消息1)
[系统开始处理消息1，需要 5-15 秒]
用户: 在吗？ (消息2，在处理消息1期间发送)
用户: 我想问你一件事 (消息3)
```

**没有打断机制的问题**：
- 系统会先回复消息1，然后再处理消息2、消息3
- 用户会收到一个针对"你好"的回复，然后才收到针对后续消息的回复
- 这会导致**对话上下文断裂**，用户体验很差

**打断机制的效果**：
- 检测到消息2到来时，放弃对消息1的回复生成
- 将消息1、2、3 合并为一个上下文一起处理
- 用户收到一个连贯的、针对所有消息的回复

**原系统实现方式**：
- 使用生成器模式，`QiaoyunChatAgent._execute()` 在回复生成后 yield 一次
- Runner 层在消费生成器时，每次 yield 后检测是否有新消息到达
- Runner 层在发送每条消息后也检测新消息
- 检测到新消息时设置 ROLLBACK 状态，中断当前处理
- 已发送的消息不会被撤回，但后续处理（如 PostAnalyze）会被跳过

> **注意**：原系统的打断粒度实际上是 5-15 秒（整个 LLM 调用时间），因为 yield 只在回复生成后执行一次，而不是每个子 Agent 执行后都 yield。

**迁移后实现方式**：
- 在 Workflow 步骤间添加新消息检测点
- Runner 层在发送每条消息后检测新消息
- 通过 RunResponse 的 metadata 传递打断状态
- PostAnalyze 等后处理步骤可被跳过，与原有行为一致

#### 2.4.2 其他需重点验证的需求

1. **FR-067 错误重试**：依赖 Agno 内置重试机制，需验证行为一致性
2. **NFR-001 性能**：引入新框架可能影响延迟，需进行性能基准测试

**需要新增 Agno Tool 的功能：**

| Tool 名称 | 对应需求 | 功能描述 |
|-----------|----------|----------|
| voice2text_tool | FR-004, FR-051 | 语音转文字 |
| text2voice_tool | FR-005, FR-052, FR-053 | 文字转语音（含情感） |
| image2text_tool | FR-006, FR-045 | 图片识别 |
| image_send_tool | FR-007 | 发送图片消息 |
| image_generate_tool | FR-046 | 文生图（LibLib API） |
| context_retrieve_tool | FR-011, FR-056 | 向量检索（角色设定、用户资料、知识库） |
| reminder_tool | FR-018~021 | 提醒管理（统一 Tool，支持 create/update/delete/list 操作） |
| moments_tool | FR-063 | 朋友圈发布 |
| album_tools | FR-064 | 照片删除 |

> **注意**：每日任务相关 Tool（album_search_tool、daily_task_regenerate_tool）已取消，不在本次迁移范围。

**需要新增/重写 Agno Agent 的功能：**

| Agent 名称 | 对应需求 | 功能描述 |
|------------|----------|----------|
| QueryRewriteAgent | FR-010 | 问题重写 |
| ChatResponseAgent | FR-012 | 对话生成 |
| PostAnalyzeAgent | FR-014 | 后处理分析 |
| ReminderDetectAgent | FR-017 | 提醒识别 |
| FutureMessagePlanAgent | FR-036 | 未来消息规划 |
| ProactiveMessageAgent | FR-038 | 主动消息生成 |

> **注意**：ChatResponseRefineAgent（FR-013）和每日任务相关 Agent（FR-041~044）已取消，不在本次迁移范围。


---

## 3. 现有架构分析

### 3.1 消息状态机（核心机制）

原系统的核心是基于生成器的消息状态机，这是迁移时必须重点关注的部分。

**状态定义：**

| 状态 | 含义 | 触发条件 |
|------|------|----------|
| READY | 初始状态 | Agent 创建时 |
| RUNNING | 执行中 | 开始执行 |
| MESSAGE | 有消息输出 | 生成回复时 yield |
| SUCCESS | 执行成功 | 正常完成 |
| FAILED | 执行失败 | 异常且重试耗尽 |
| RETRYING | 重试中 | 异常但未达重试上限 |
| ROLLBACK | 被打断 | 检测到新消息 |
| CLEAR | 清除状态 | 特殊清理场景 |
| FINISHED | 最终完成 | 流程结束 |

**状态流转图：**

```
READY → RUNNING → MESSAGE → SUCCESS → FINISHED
           ↓         ↓
        FAILED   ROLLBACK (新消息打断)
           ↓
       RETRYING → RUNNING (重试)
```

**关键设计点：**

1. **生成器模式**：通过 `yield` 实现流式状态输出，Runner 层可实时响应
2. **消息打断**：Runner 层在消费生成器时检测新消息，触发 ROLLBACK
3. **重试机制**：`max_retries` 控制重试次数，失败后进入 RETRYING 状态

### 3.2 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     Connector 层                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ ecloud_input│    │   Adapter   │    │ecloud_output│         │
│  │  (Flask)    │───▶│ 消息格式转换 │◀───│  (轮询发送)  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                                      ▲                │
│         ▼                                      │                │
│  ┌──────────────────────────────────────────────────┐          │
│  │              inputmessages / outputmessages       │          │
│  │                    (MongoDB 消息队列)              │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Runner 层                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  context_prepare() → 构建统一 Context                    │   │
│  │  main_handler() → 消费 Agent 生成器，处理响应             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 层                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  QiaoyunChatAgent.run() → 生成器 Pipeline                │   │
│  │                                                          │   │
│  │  yield from QueryRewriteAgent(context).run()            │   │
│  │  yield from ContextRetrieveAgent(context).run()         │   │
│  │  yield from ChatResponseAgent(context).run()            │   │
│  │  yield from PostAnalyzeAgent(context).run()             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Framework 层                                  │
│  ┌─────────────┐  ┌─────────────────────┐                      │
│  │ BaseAgent   │  │ BaseSingleRoundLLM  │                      │
│  │ 生命周期管理 │  │ Prompt渲染/LLM调用   │                      │
│  └─────────────┘  └─────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 各层职责分析

#### 3.3.1 Connector 层

| 组件 | 文件 | 职责 |
|------|------|------|
| ecloud_input | `connector/ecloud/ecloud_input.py` | Flask 服务接收微信消息，标准化后存入 MongoDB |
| ecloud_output | `connector/ecloud/ecloud_output.py` | 轮询 MongoDB，调用 ecloud API 发送消息 |
| ecloud_adapter | `connector/ecloud/ecloud_adapter.py` | ecloud 消息格式与标准格式互转 |
| base_connector | `connector/base_connector.py` | 抽象基类，定义 input/output handler |

**数据流：**
- 输入：微信消息 → Flask → 标准化 → MongoDB `inputmessages`
- 输出：MongoDB `outputmessages` → 轮询 → ecloud API → 微信

#### 3.3.2 Runner 层

| 组件 | 文件 | 职责 |
|------|------|------|
| context | `qiaoyun/runner/context.py` | 构建 context (user, character, conversation, relation) |
| qiaoyun_handler | `qiaoyun/runner/qiaoyun_handler.py` | 消息消费主循环、锁管理、Agent 调度、响应处理 |

**核心流程：**
```python
async def main_handler():
    # 1. 获取待处理消息
    top_messages = read_top_inputmessages(...)
    
    # 2. 获取/创建 conversation 并上锁
    lock = lock_manager.acquire_lock(...)
    
    # 3. 构建 context
    context = context_prepare(user, character, conversation)
    
    # 4. 调用 Agent Pipeline
    c = QiaoyunChatAgent(context)
    results = c.run()
    
    # 5. 处理 Agent 输出
    for result in results:
        if result["status"] == AgentStatus.MESSAGE.value:
            send_message_via_context(...)
    
    # 6. 更新 conversation 和 relation
```


#### 3.3.3 Agent 层

| Agent | 文件 | 基类 | 职责 |
|-------|------|------|------|
| QiaoyunChatAgent | `qiaoyun/agent/qiaoyun_chat_agent.py` | BaseAgent | Pipeline 编排，串联各子 Agent |
| QiaoyunQueryRewriteAgent | `qiaoyun/agent/qiaoyun_query_rewrite_agent.py` | DouBaoLLMAgent | 问题重写，生成检索 query |
| QiaoyunContextRetrieveAgent | `qiaoyun/agent/qiaoyun_context_retrieve_agent.py` | BaseAgent | 向量检索 + 关键词检索 |
| QiaoyunChatResponseAgent | `qiaoyun/agent/qiaoyun_chat_response_agent.py` | DouBaoLLMAgent | 生成多模态回复 |
| QiaoyunChatResponseRefineAgent | `qiaoyun/agent/qiaoyun_chat_response_refine_agent.py` | DouBaoLLMAgent | R1 模型优化回复 |
| QiaoyunPostAnalyzeAgent | `qiaoyun/agent/qiaoyun_post_analyze_agent.py` | DouBaoLLMAgent | 总结对话，更新记忆 |
| DetectedRemindersAgent | `qiaoyun/agent/qiaoyun_detected_reminders_agent.py` | BaseAgent | 提醒检测与处理 |

**Pipeline 执行流程：**
```
QueryRewrite → ContextRetrieve → ChatResponse → [Refine] → PostAnalyze
     ↓              ↓                 ↓                        ↓
  生成检索词      检索上下文        生成回复              更新记忆
```

#### 3.3.4 Framework 层

| 组件 | 文件 | 职责 |
|------|------|------|
| BaseAgent | `framework/agent/base_agent.py` | 生命周期管理 (prehandle→execute→posthandle)、状态机、重试 |
| BaseSingleRoundLLMAgent | `framework/agent/llmagent/base_singleroundllmagent.py` | Prompt 模板渲染、LLM 调用、输出解析 |
| DouBaoLLMAgent | `framework/agent/llmagent/doubao_llmagent.py` | 火山引擎 Doubao 模型适配 |

**BaseAgent 状态机：**
```
READY → RUNNING → MESSAGE → SUCCESS/FAILED → FINISHED
                    ↓
                 ROLLBACK (新消息打断)
```

### 3.4 现有问题分析

| 问题 | 影响 | 严重程度 |
|------|------|----------|
| 自研框架维护成本高 | 需要持续投入人力修复 Bug | 高 |
| 状态机逻辑复杂 | 难以理解和调试 | 中 |
| 模型切换不灵活 | 更换模型需要修改代码 | 中 |
| 缺乏标准化的 Agent 编排 | Pipeline 扩展困难 | 中 |
| Prompt 模板与代码耦合 | 修改 Prompt 需要改代码 | 低 |


---

## 4. 目标架构设计

### 4.1 Agno 框架简介

Agno 是一个生产级 Agent 框架，提供：

- **Agent**：声明式 Agent 定义，内置生命周期管理
- **Team**：多 Agent 协作编排
- **Workflow**：复杂流程编排
- **Tools**：可扩展的工具系统
- **Models**：统一的多模型接口 (OpenAI, Claude, DeepSeek, Gemini 等)
- **Memory**：用户记忆持久化
- **Knowledge**：RAG 知识库管理
- **AgentOS**：生产级运行时

### 4.2 目标架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     Connector 层 (保留不变)                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ ecloud_input│    │   Adapter   │    │ecloud_output│         │
│  │  (Flask)    │───▶│ 消息格式转换 │◀───│  (轮询发送)  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                                      ▲                │
│         ▼                                      │                │
│  ┌──────────────────────────────────────────────────┐          │
│  │              inputmessages / outputmessages       │          │
│  │                    (MongoDB 消息队列)              │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Runner 层 (适配修改)                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  context_prepare() → 构建 Agno session_state            │   │
│  │  main_handler() → 调用 Agno Team，处理 RunResponse      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agno Agent/Team 层 (新建)                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  QiaoyunTeam = Team(                                     │   │
│  │      mode="coordinate",                                  │   │
│  │      members=[                                           │   │
│  │          QueryRewriteAgent,                              │   │
│  │          ChatResponseAgent,                              │   │
│  │          PostAnalyzeAgent,                               │   │
│  │      ],                                                  │   │
│  │      tools=[context_retrieve_tool, reminder_tool],       │   │
│  │  )                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agno Framework (替换自研)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ agno.agent  │  │ agno.models │  │ agno.tools  │             │
│  │ Agent 基类  │  │ DeepSeek    │  │ Tool 装饰器 │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 技术选型

| 组件 | 现有方案 | 目标方案 |
|------|----------|----------|
| Agent 基类 | 自研 BaseAgent | `agno.agent.Agent` |
| LLM 调用 | 自研 BaseSingleRoundLLMAgent | `agno.models.deepseek.DeepSeek` |
| Agent 编排 | 手动 yield from | `agno.team.Team` |
| 输出格式 | JSON Schema | Pydantic `response_model` |
| 状态传递 | context dict | Agno `session_state` |
| 重试机制 | 自研 | Agno 内置 |

### 4.4 session_state 兼容性验证（迁移前必做）

> **PoC 测试状态**：✅ 已通过  
> **执行时间**：2025-12-04  
> **Agno 版本**：2.3.6

现有系统使用深度嵌套的 dict 结构作为 context，在迁移到 Agno 的 `session_state` 前，需要验证兼容性。

#### 4.4.1 现有 Context 的三个核心用途

| 用途 | 说明 | Agno 兼容性 |
|------|------|-------------|
| 跨 Agent 状态传递 | 让后续 Agent 访问前序 Agent 的处理结果 | ✅ 完全兼容 |
| Prompt 模板渲染 | 将动态数据注入到 Prompt 中 | ⚠️ 需确保字段完整 |
| 持久化数据修改 | Agent 执行中修改数据，最后统一持久化 | ⚠️ 需验证嵌套修改 |

#### 4.4.2 PoC 测试结果

| 测试场景 | 验证内容 | 结果 |
|---------|---------|------|
| 嵌套 dict 修改传递 | 在 Workflow 中修改 `session_state["a"]["b"]["c"]`，验证返回值是否包含修改 | ✅ 通过 |
| Agent session_state 基本功能 | 初始化、访问、修改嵌套字段 | ✅ 通过 |
| 多 Workflow 状态传递 | PrepareWorkflow → ChatWorkflow → PostAnalyzeWorkflow 顺序执行 | ✅ 通过 |
| ObjectId 序列化 | ObjectId 转字符串后 JSON 序列化和 Workflow 传递 | ✅ 通过 |
| 完整对话流程模拟 | 端到端流程含消息打断检测点 | ✅ 通过 |
| 大对象传递 | 传入包含 50 条历史对话的 session_state | ✅ 通过 |

**验证结论**：
- session_state 支持任意深度的嵌套字典修改和传递
- 多个 Workflow 顺序执行时状态正确累积
- ObjectId 转字符串后可正常使用，DAO 层无需修改
- 消息打断机制可以在 Runner 层通过分段执行实现

#### 4.4.3 风险消除确认

| 风险项 | 原评估 | 验证后状态 |
|-------|--------|-----------|
| session_state 兼容性问题 | 中风险 | ✅ 已消除 |
| ObjectId 序列化问题 | 高风险 | ✅ 已消除 |
| 消息打断机制降级 | 中风险 | ✅ 方案可行 |
| 大对象传递性能 | 中风险 | ✅ 已消除 |

#### 4.4.4 ObjectId 序列化问题分析与解决方案

**问题分析**：

现有系统的 context 中包含 MongoDB 的 `bson.ObjectId` 类型：
- `context["user"]["_id"]` - 用户 ID
- `context["character"]["_id"]` - 角色 ID
- `context["conversation"]["_id"]` - 会话 ID
- `context["relation"]["_id"]` - 关系 ID

Agno 的 session_state 在以下场景可能需要 JSON 序列化：
1. 持久化到数据库
2. 在 Agent 间传递
3. 日志记录

**解决方案**：

在 `context_prepare()` 中统一将 ObjectId 转换为字符串：

```python
# qiaoyun/runner/context.py

def context_prepare(user, character, conversation):
    context = {
        "user": user,
        "character": character,
        "conversation": conversation
    }
    
    # ... 现有逻辑 ...
    
    # ObjectId 序列化处理（新增）
    context = _convert_objectid_to_str(context)
    
    return context

def _convert_objectid_to_str(obj):
    """递归将 dict 中的 ObjectId 转换为字符串"""
    from bson import ObjectId
    
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_objectid_to_str(item) for item in obj]
    else:
        return obj
```

**影响评估**：

| 影响点 | 处理方式 |
|--------|----------|
| DAO 层查询 | **无需修改** - DAO 层代码已做兼容处理，接收字符串 ID 时会自动转换为 ObjectId |
| 日志记录 | 无影响，字符串更易读 |
| 数据持久化 | 无影响，MongoDB 会自动处理 |

> **已确认**：经代码分析，DAO 层（conversation_dao.py、user_dao.py、reminder_dao.py、mongo.py）的所有方法在接收 ID 参数时，都会尝试将字符串转换为 ObjectId，因此 **DAO 层代码不需要修改**。

**决策**：在 Phase 1 基础设施准备阶段完成此 PoC 测试，确认通过后再继续后续迁移。


---

## 5. 概要设计

### 5.1 模块划分

迁移后的代码结构：

```
project/
├── connector/                    # 保留不变
│   ├── ecloud/
│   └── base_connector.py
│
├── qiaoyun/
│   ├── runner/                   # 适配修改
│   │   ├── context.py           # 小改：输出兼容 session_state
│   │   └── qiaoyun_handler.py   # 改：调用 Agno Team
│   │
│   ├── agno_agent/              # 新建：Agno Agent 实现
│   │   ├── __init__.py
│   │   ├── agents/              # 各 Agent 定义
│   │   │   ├── query_rewrite_agent.py
│   │   │   ├── chat_response_agent.py
│   │   │   └── post_analyze_agent.py
│   │   ├── tools/               # Tool 定义
│   │   │   ├── context_retrieve_tool.py
│   │   │   └── reminder_tool.py
│   │   ├── schemas/             # Pydantic 响应模型
│   │   │   ├── query_rewrite_schema.py
│   │   │   ├── chat_response_schema.py
│   │   │   └── post_analyze_schema.py
│   │   └── team.py              # Team 编排
│   │
│   ├── prompt/                   # 保留：Prompt 模板
│   └── agent/                    # 废弃：迁移完成后删除
│
├── framework/                    # 废弃：由 Agno 替代
│   └── agent/
│
└── dao/                          # 保留不变
```

### 5.2 组件映射关系

#### 5.2.1 Framework 层组件映射

| 现有组件 | 迁移后组件 | 迁移方式 |
|----------|------------|----------|
| `BaseAgent` | `agno.agent.Agent` | 替换 |
| `BaseSingleRoundLLMAgent` | `agno.models.deepseek.DeepSeek` | 替换 |
| `DouBaoLLMAgent` | `agno.models.deepseek.DeepSeek` | 替换 |

#### 5.2.2 Agent 层组件映射

| 现有组件 | 迁移后组件 | 迁移方式 | 对应需求 |
|----------|------------|----------|----------|
| `QiaoyunChatAgent` | `QiaoyunChatWorkflow` | 重写 | Pipeline 编排 |
| `QiaoyunQueryRewriteAgent` | `QueryRewriteAgent` | 重写 | FR-010 |
| `QiaoyunContextRetrieveAgent` | `context_retrieve_tool` | 重写为 Tool | FR-011 |
| `QiaoyunChatResponseAgent` | `ChatResponseAgent` | 重写 | FR-012 |
| `QiaoyunChatResponseRefineAgent` | - | 不迁移 | FR-013（已取消） |
| `QiaoyunPostAnalyzeAgent` | `PostAnalyzeAgent` | 重写 | FR-014 |
| `DetectedRemindersAgent` | `ReminderDetectAgent` + `reminder_tool` | 重写 | FR-017~FR-021 |

#### 5.2.3 新增 Agent 组件

| Agent 名称 | 功能描述 | 对应需求 |
|------------|----------|----------|
| `FutureMessagePlanAgent` | 规划角色未来主动发送的消息 | FR-036 |
| `ProactiveMessageAgent` | 基于上下文生成主动消息内容 | FR-038 |

> **注意**：每日任务相关 Agent（KnowledgeLearningAgent、DailyScriptAgent、MomentsTextAgent）已取消，不在本次迁移范围。

#### 5.2.4 新增 Tool 组件

> 完整 Tool 列表参见 [2.4.2 节](#242-其他需重点验证的需求) 的"需要新增 Agno Tool 的功能"表格。

### 5.3 数据流设计

#### 5.3.1 输入数据流

```
MongoDB inputmessages
        ↓
    Runner 层
        ↓ context_prepare()
    session_state = {
        "user": {...},
        "character": {...},
        "conversation": {...},
        "relation": {...},
        "input_messages_str": "...",
        "chat_history_str": "...",
    }
        ↓
    Agno Team.run(message, session_state)
```

#### 5.3.2 输出数据流

```
    Agno Team.run() 返回 RunResponse
        ↓
    response.content → 多模态响应列表
        ↓
    Runner 层处理
        ↓ send_message_via_context()
    MongoDB outputmessages
        ↓
    Connector 层发送
```

### 5.4 接口设计

#### 5.4.1 Runner → Agno Team 接口

```python
# 输入
team.run(
    message: str,                    # 用户输入消息
    session_state: dict,             # context 数据
) -> RunResponse

# 输出
RunResponse:
    content: List[Content]           # 响应内容列表
    session_state: dict              # 更新后的 context
```

#### 5.4.2 Agno Agent 响应模型

```python
# QueryRewriteAgent 输出
class QueryRewriteResponse(BaseModel):
    InnerMonologue: str
    CharacterSettingQueryQuestion: str
    CharacterSettingQueryKeywords: str
    UserProfileQueryQuestion: str
    UserProfileQueryKeywords: str
    CharacterKnowledgeQueryQuestion: str
    CharacterKnowledgeQueryKeywords: str

# ChatResponseAgent 输出
class ChatResponse(BaseModel):
    InnerMonologue: str
    MultiModalResponses: List[MultiModalResponse]
    ChatCatelogue: str
    RelationChange: RelationChangeModel
    FutureResponse: FutureResponseModel

# PostAnalyzeAgent 输出
class PostAnalyzeResponse(BaseModel):
    CharacterPublicSettings: str
    CharacterPrivateSettings: str
    UserSettings: str
    UserRealName: str
    RelationDescription: str
    # ...
```


---

## 6. 详细设计

### 6.1 Connector 层 (保留)

**变更：无**

Connector 层与 Agent 框架解耦，通过 MongoDB 消息队列进行通信，无需修改。

### 6.2 Runner 层 (适配修改)

#### 6.2.0 状态机迁移方案

**核心问题：** 原系统的状态机通过生成器实现，Agno 使用 RunResponse 返回结果，需要在 Runner 层和 Workflow 层做适配。

**迁移对照表：**

| 原状态 | 原处理方式 | Agno 处理方式 | 迁移说明 |
|--------|-----------|---------------|----------|
| MESSAGE | `yield` 输出消息 | `response.content` | 从 RunResponse 提取内容 |
| ROLLBACK | Runner 检测新消息后设置 | Workflow 步骤间 + Runner 层检测 | 两层检测机制 |
| FAILED | 异常 + 重试耗尽 | 捕获异常 | Agno 内置重试，外层捕获最终异常 |
| RETRYING | 自动重试 | Agno 内置 | 无需额外处理 |
| SUCCESS | 正常完成 | `response` 正常返回 | 检查 response 非空 |
| FINISHED | 流程结束 | 方法返回 | 自然结束 |

#### 6.2.0.1 消息打断机制迁移方案 (FR-009)

**设计目标**：保留原有的打断机制，避免对话上下文割裂。

**设计原则**：
- **Workflow 不访问数据库**：Workflow 专注于业务逻辑编排，消息打断是流程控制逻辑
- **Runner 层控制打断**：消息检测逻辑保留在 Runner 层，与原系统一致
- **分段执行**：将流程拆分为多个阶段，每个阶段返回后 Runner 层检测新消息

**方案设计**：Runner 层控制 + 分段执行

```
Runner 层执行流程:
  1. 调用 Phase 1: QueryRewrite + ReminderDetect + ContextRetrieve (快速阶段)
  2. 检测新消息 → 如果有，返回 rollback
  3. 调用 Phase 2: ChatResponse (耗时阶段)
  4. 发送消息，每条消息后检测新消息
  5. 如果没有被打断，调用 Phase 3: PostAnalyze
```

**打断粒度分析**：

| 阶段 | 耗时估计 | 打断检测 | 打断后行为 |
|------|---------|---------|-----------|
| Phase 1 (QueryRewrite + ReminderDetect + ContextRetrieve) | 2-4秒 | 无 | - |
| **检测点 1** | - | Runner 层同步检测 | 丢弃，返回 rollback |
| Phase 2 (ChatResponse) | 3-10秒 | 无 | - |
| **检测点 2** | - | 每条消息发送后检测 | 停止发送，跳过 PostAnalyze |
| Phase 3 (PostAnalyze) | 2-5秒 | 无 | 可被跳过 |

**最坏情况打断延迟**：约 3-10 秒（ChatResponse 执行时间）

**与原系统对比**：

| 指标 | 原系统 | 新方案 |
|------|--------|--------|
| 打断粒度 | 每次 yield（~5-15秒） | 阶段间检测（~3-10秒） |
| 实现复杂度 | 生成器模式 | 分段调用 |
| Workflow 职责 | - | 纯业务逻辑，不访问数据库 |
| 可测试性 | 较难 | 易于单元测试 |

> **注意**：原系统的打断粒度实际上也是 5-15 秒（整个 LLM 调用时间），因为 yield 只在回复生成后执行一次。新方案的打断粒度与原系统基本一致。

**打断后的处理**：

与原有逻辑保持一致：
- 已发送的消息不会被撤回
- 已处理的输入消息和已发送的回复都记录到历史
- PostAnalyze 等后处理步骤被跳过
- 新消息会在下一轮处理时看到完整的历史上下文

#### 6.2.1 context.py 修改

**变更点：** 确保 `context_prepare()` 输出兼容 Agno `session_state`，统一将 ObjectId 转换为字符串

```python
# qiaoyun/runner/context.py

def context_prepare(user, character, conversation) -> dict:
    """
    构建 context，兼容 Agno session_state
    
    Returns:
        dict: 可直接作为 Agno session_state 使用
    """
    context = {
        "user": user,
        "character": character,
        "conversation": conversation,
    }
    
    # ... 现有逻辑保持不变 ...
    
    # ObjectId 序列化处理（新增）
    context = _convert_objectid_to_str(context)
    
    return context

def _convert_objectid_to_str(obj):
    """递归将 dict 中的 ObjectId 转换为字符串"""
    from bson import ObjectId
    
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_objectid_to_str(item) for item in obj]
    else:
        return obj
```

#### 6.2.2 qiaoyun_handler.py 修改

**变更点：** 替换 Agent 调用方式，Runner 层控制消息打断和分段执行

```python
# qiaoyun/runner/qiaoyun_handler.py

# 新增导入
from qiaoyun.agno_agent.workflows.prepare_workflow import PrepareWorkflow
from qiaoyun.agno_agent.workflows.chat_workflow import ChatWorkflow
from qiaoyun.agno_agent.workflows.post_analyze_workflow import PostAnalyzeWorkflow

prepare_workflow = PrepareWorkflow()
chat_workflow = ChatWorkflow()
post_analyze_workflow = PostAnalyzeWorkflow()

async def main_handler():
    # ... 1-3 步保持不变：获取消息、上锁、构建 context ...
    
    context = context_prepare(user, character, conversation)
    
    is_failed = False
    is_rollback = False
    resp_messages = []
    
    # ... 处理拉黑、硬指令、繁忙状态等逻辑保持不变 ...
    
    else:
        # ========== Phase 1: 准备阶段（QueryRewrite + ReminderDetect + ContextRetrieve）==========
        try:
            prepare_response = prepare_workflow.run(
                input=context["conversation"]["conversation_info"]["input_messages_str"],
                session_state=context,
            )
            context = prepare_response.session_state or context
            
            # ===== 检测点 1：在生成回复前检测新消息 =====
            if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                is_rollback = True
                logger.info("roll back as new incoming message before chat response")
            
            if not is_rollback:
                # ========== Phase 2: 生成回复 ==========
                chat_response = chat_workflow.run(
                    input=context["conversation"]["conversation_info"]["input_messages_str"],
                    session_state=context,
                )
                context = chat_response.session_state or context
                
                # 处理回复内容
                resp = chat_response.content or {}
                multimodal_responses = resp.get("MultiModalResponses", [])
                context["MultiModalResponses"] = multimodal_responses  # 供 PostAnalyze 使用
                
                # 发送消息
                for idx, multimodal_response in enumerate(multimodal_responses):
                    # ... 消息发送逻辑保持不变 ...
                    
                    # ===== 检测点 2：每条消息发送后检测新消息 =====
                    if is_new_message_coming_in(str(user["_id"]), str(character["_id"]), platform):
                        is_rollback = True
                        logger.info("roll back as new incoming message during sending")
                        break
                
                # ========== Phase 3: 后处理（如果没有被打断）==========
                if not is_rollback and len(resp_messages) > 0:
                    post_analyze_workflow.run(session_state=context)
        
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            logger.error(traceback.format_exc())
            is_failed = True
    
    # ... 后续更新 conversation 和 relation 的逻辑保持不变 ...
```

#### 6.2.3 状态处理对照

| 现有状态 | Agno 处理方式 |
|----------|---------------|
| `AgentStatus.MESSAGE` | `response.content` 非空 |
| `AgentStatus.FAILED` | 捕获异常 |
| `AgentStatus.ROLLBACK` | Workflow metadata + Runner 层检测 |
| `AgentStatus.SUCCESS` | `response` 正常返回 |


### 6.3 Agent 层 (重构)

#### 6.3.1 目录结构

```
qiaoyun/agno_agent/
├── __init__.py
├── agents/                              # Agent 定义
│   ├── __init__.py
│   ├── query_rewrite_agent.py           # FR-010 问题重写
│   ├── chat_response_agent.py           # FR-012 对话生成
│   ├── post_analyze_agent.py            # FR-014 后处理分析
│   ├── reminder_detect_agent.py         # FR-017 提醒识别
│   ├── future_message_plan_agent.py     # FR-036 未来消息规划
│   └── proactive_message_agent.py       # FR-038 主动消息生成
├── tools/                               # Tool 定义
│   ├── __init__.py
│   ├── voice_tools.py                   # FR-004/051 语音转文字, FR-005/052/053 文字转语音
│   ├── image_tools.py                   # FR-006/045 图片识别, FR-007 图片发送
│   ├── context_retrieve_tool.py         # FR-011/056 向量检索
│   └── reminder_tools.py                # FR-018~021 提醒 CRUD
├── schemas/                             # Pydantic 响应模型
│   ├── __init__.py
│   ├── query_rewrite_schema.py
│   ├── chat_response_schema.py
│   ├── post_analyze_schema.py
│   ├── reminder_schema.py
│   └── future_message_schema.py
└── workflows/                           # Workflow 编排
    ├── __init__.py
    ├── prepare_workflow.py              # 准备阶段（QueryRewrite + ReminderDetect + ContextRetrieve）
    ├── chat_workflow.py                 # 回复生成
    ├── post_analyze_workflow.py         # 后处理分析
    └── proactive_message_workflow.py    # 主动消息流程
```

#### 6.3.2 Pydantic Schema 定义

> 注：以下仅展示关键字段，完整实现参见代码文件

| Schema | 文件 | 关键字段 |
|--------|------|----------|
| QueryRewriteResponse | `schemas/query_rewrite_schema.py` | InnerMonologue, CharacterSettingQuery*, UserProfileQuery*, CharacterKnowledgeQuery* |
| ChatResponse | `schemas/chat_response_schema.py` | InnerMonologue, MultiModalResponses, RelationChange, FutureResponse |
| PostAnalyzeResponse | `schemas/post_analyze_schema.py` | CharacterPublicSettings, UserSettings, RelationDescription, Dislike |

**ChatResponse 结构示例：**

```python
class ChatResponse(BaseModel):
    InnerMonologue: str                    # 角色内心独白
    MultiModalResponses: List[dict]        # [{type: "text"|"photo", content: "..."}]
    RelationChange: RelationChangeModel    # {Closeness: float, Trustness: float}
    FutureResponse: FutureResponseModel    # {FutureResponseTime, FutureResponseAction}
```


#### 6.3.3 Agent 定义

每个 Agent 使用 Agno 的声明式定义，核心配置如下：

| Agent | 文件 | 关键配置 |
|-------|------|----------|
| query_rewrite_agent | `agents/query_rewrite_agent.py` | model=DeepSeek, response_model=QueryRewriteResponse |
| chat_response_agent | `agents/chat_response_agent.py` | model=DeepSeek, response_model=ChatResponse |
| post_analyze_agent | `agents/post_analyze_agent.py` | model=DeepSeek, response_model=PostAnalyzeResponse |

**Agent 定义模板：**

```python
from agno.agent import Agent
from agno.models.deepseek import DeepSeek

agent = Agent(
    id="agent-id",
    name="Agent名称",
    model=DeepSeek(id="deepseek-chat"),
    instructions=[...],           # 复用现有 Prompt
    response_model=ResponseSchema, # Pydantic 模型
    markdown=False,
)
```

**Prompt 迁移说明：**
- `instructions` 为静态指令，复用现有 `SYSTEMPROMPT_*` 和 `TASKPROMPT_*`
- 动态内容（角色信息、历史对话等）通过 `message` 参数传入


#### 6.3.4 Tool 定义

**Tool 迁移策略分类：**

根据现有代码分析，将 Tool 分为三类：

##### 类别 A：可直接复用现有函数（薄封装）

这些 Tool 的核心逻辑已在现有代码中实现，只需用 Agno `@tool` 装饰器封装即可。

| Tool | 现有实现位置 | 功能 | 对应需求 |
|------|-------------|------|----------|
| text2voice | `qiaoyun/tool/voice.py` → `qiaoyun_voice()` | 文字转语音（MiniMax T2A） | FR-005, FR-052, FR-053 |
| image_generate | `qiaoyun/tool/image.py` → `generate_qiaoyun_image()` | 文生图（LibLib API） | FR-046 |
| image_send | `qiaoyun/tool/image.py` → `upload_image()` | 发送图片消息 | FR-007 |
| voice2text | `util/voice.py` → 阿里云 ASR | 语音转文字 | FR-004, FR-051 |

**封装示例（直接复用）：**

```python
# tools/voice_tools.py
from agno.tools import tool
from qiaoyun.tool.voice import qiaoyun_voice

@tool(description="将文字转换为语音消息，支持情感色彩")
def text2voice_tool(text: str, emotion: str = "无") -> list:
    """
    文字转语音
    
    Args:
        text: 要转换的文字
        emotion: 情感色彩 (无/高兴/悲伤/愤怒/害怕/惊讶/厌恶/魅惑)
    
    Returns:
        [(url, voice_length), ...] 语音文件URL和时长列表
    """
    return qiaoyun_voice(text, emotion)
```

```python
# tools/image_tools.py
from agno.tools import tool
from qiaoyun.tool.image import generate_qiaoyun_image, generate_qiaoyun_image_save, upload_image

@tool(description="根据描述生成角色照片")
def image_generate_tool(prompt: str, img_count: int = 1, sub_mode: str = "半身照") -> list:
    """
    文生图
    
    Args:
        prompt: 图片描述
        img_count: 生成数量
        sub_mode: 照片类型 (半身照/全身照)
    
    Returns:
        生成的图片路径列表
    """
    task_id = generate_qiaoyun_image(prompt, img_count, mode=0, sub_mode=sub_mode)
    origin_paths, saved_paths = generate_qiaoyun_image_save(task_id)
    return saved_paths

@tool(description="上传照片并获取可发送的URL")
def image_send_tool(photo_id: str) -> str:
    """
    上传图片到 OSS 并获取 URL
    
    Args:
        photo_id: 照片ID（embeddings 表中的 _id）
    
    Returns:
        图片的签名URL
    """
    return upload_image(photo_id)
```

##### 类别 B：需要封装但逻辑复杂

> **决策已确认**：以下 Tool 的实现方案已确定。

| Tool | 现有实现 | 复杂度 | 决策 |
|------|---------|--------|------|
| context_retrieve | `QiaoyunContextRetrieveAgent` | 高 | ✅ 封装为 Tool，复用 Agent 的 `_execute()` 逻辑 |
| reminder_tool | `DetectedRemindersAgent` + `ReminderDAO` | 中 | ✅ 封装为统一 Tool，通过 action 参数区分 CRUD 操作 |

**context_retrieve_tool 封装方案（复用现有 Agent 逻辑）：**

```python
# tools/context_retrieve_tool.py
from agno.tools import tool
from qiaoyun.agent.qiaoyun_context_retrieve_agent import QiaoyunContextRetrieveAgent

@tool(description="检索角色设定、用户资料、知识库")
def context_retrieve_tool(
    character_setting_query: str = "",
    user_profile_query: str = "",
    character_knowledge_query: str = "",
    character_id: str = "",
    user_id: str = ""
) -> dict:
    """
    向量检索工具，检索角色全局设定、角色私有设定、用户资料、角色知识
    
    Args:
        character_setting_query: 角色设定检索问题
        user_profile_query: 用户资料检索问题
        character_knowledge_query: 角色知识检索问题
        character_id: 角色ID
        user_id: 用户ID
    
    Returns:
        检索结果 dict，包含 character_global, character_private, user, character_knowledge 等字段
    """
    # 复用现有 Agent 的核心逻辑
    context = {
        "query_rewrite": {
            "CharacterSettingQueryQuestion": character_setting_query,
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": user_profile_query,
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": character_knowledge_query,
            "CharacterKnowledgeQueryKeywords": "",
        },
        "character": {"_id": character_id},
        "user": {"_id": user_id}
    }
    agent = QiaoyunContextRetrieveAgent(context)
    for result in agent.run():
        if result["status"] == "finished":
            return result["resp"]
    return {}
```

**reminder_tool 封装方案（统一 Tool，复用 ReminderDAO）：**

```python
# tools/reminder_tool.py
from agno.tools import tool
from dao.reminder_dao import ReminderDAO
from util.time_util import parse_relative_time, str2timestamp
import uuid

@tool(description="提醒管理工具，支持创建、更新、删除、查询提醒")
def reminder_tool(
    action: str,
    user_id: str,
    reminder_id: str = None,
    title: str = None,
    trigger_time: str = None,
    action_template: str = None,
    recurrence_type: str = "none"
) -> dict:
    """
    提醒管理统一工具
    
    Args:
        action: 操作类型 ("create" | "update" | "delete" | "list")
        user_id: 用户ID
        reminder_id: 提醒ID（update/delete 时必填）
        title: 提醒标题（create/update 时使用）
        trigger_time: 触发时间（支持相对时间如"30分钟后"或绝对时间）
        action_template: 提醒文案模板
        recurrence_type: 周期类型 (none/daily/weekly/monthly)
    
    Returns:
        操作结果
    """
    reminder_dao = ReminderDAO()
    
    try:
        if action == "create":
            timestamp = parse_relative_time(trigger_time) or str2timestamp(trigger_time)
            if not timestamp:
                return {"ok": False, "error": "无法解析时间"}
            
            reminder_doc = {
                "user_id": user_id,
                "reminder_id": str(uuid.uuid4()),
                "title": title,
                "action_template": action_template or f"提醒：{title}",
                "next_trigger_time": timestamp,
                "recurrence": {"enabled": recurrence_type != "none", "type": recurrence_type},
                "status": "confirmed"
            }
            rid = reminder_dao.create_reminder(reminder_doc)
            return {"ok": bool(rid), "reminder_id": rid}
        
        elif action == "update":
            if not reminder_id:
                return {"ok": False, "error": "更新操作需要提供 reminder_id"}
            update_fields = {}
            if title:
                update_fields["title"] = title
            if trigger_time:
                timestamp = parse_relative_time(trigger_time) or str2timestamp(trigger_time)
                if timestamp:
                    update_fields["next_trigger_time"] = timestamp
            if action_template:
                update_fields["action_template"] = action_template
            if recurrence_type:
                update_fields["recurrence"] = {"enabled": recurrence_type != "none", "type": recurrence_type}
            
            success = reminder_dao.update_reminder(reminder_id, update_fields)
            return {"ok": success}
        
        elif action == "delete":
            if not reminder_id:
                return {"ok": False, "error": "删除操作需要提供 reminder_id"}
            success = reminder_dao.delete_reminder(reminder_id)
            return {"ok": success}
        
        elif action == "list":
            reminders = reminder_dao.get_user_reminders(user_id)
            return {"ok": True, "reminders": reminders}
        
        else:
            return {"ok": False, "error": f"不支持的操作类型: {action}"}
    
    finally:
        reminder_dao.close()
```

##### Tool 迁移优先级

| 优先级 | Tool | 类别 | 理由 |
|--------|------|------|------|
| P0（必须） | context_retrieve_tool | B | 核心对话流程依赖 |
| P0（必须） | reminder_tool | B | 提醒功能依赖（统一 CRUD 操作） |
| P1（重要） | text2voice_tool | A | 语音回复依赖，可直接复用 |
| P1（重要） | voice2text_tool | A | 语音消息处理依赖，可直接复用 |
| P1（重要） | image2text_tool | A | 图片识别依赖，可直接复用 |
| P1（重要） | image_send_tool | A | 图片发送依赖，可直接复用 |
| P2（一般） | image_generate_tool | A | 文生图功能，可直接复用 |
| P2（一般） | moments_tool | A | 朋友圈发布功能 |
| P2（一般） | album_tools | A | 照片删除功能 |

> **注意**：每日任务相关 Tool（news_search_tool、album_search_tool、daily_task_tool）已取消，不在本次迁移范围。


#### 6.3.5 Workflow 编排

使用自定义 Workflow 类实现流程控制，替代原有的 `yield from` 链式调用。

**设计原则**：
- Workflow 不访问数据库，专注于业务逻辑编排
- Tool 必须通过 Agent 调用，不能在 Workflow 中直接调用
- 消息打断由 Runner 层控制，Workflow 只返回业务结果
- **不使用 Agno 原生的 Step-based Workflow**，因为需要在 Runner 层控制分段执行和打断检测

**为什么不使用 Agno 原生 Step-based Workflow？**

| 方式 | 执行控制 | 打断检测 | 适用场景 |
|------|---------|---------|---------|
| Agno Step-based | 自动执行所有 Step | ❌ 无法在 Step 间插入 | 无需中间控制的流程 |
| 自定义 run() | Runner 层手动调用 | ✅ 可在调用间检测 | 需要打断机制的流程 |

##### 6.3.5.1 Agent 模块级预创建 (agents.py)

所有 Agent 在模块级别预创建，避免每次调用时的实例化开销：

```python
# qiaoyun/agno_agent/agents.py

from agno.agent import Agent
from agno.models.deepseek import DeepSeek
from agno.run import RunContext

from qiaoyun.agno_agent.schemas.query_rewrite_schema import QueryRewriteResponse
from qiaoyun.agno_agent.schemas.chat_response_schema import ChatResponse
from qiaoyun.agno_agent.schemas.post_analyze_schema import PostAnalyzeResponse
from qiaoyun.agno_agent.tools.reminder_tools import reminder_tool
from qiaoyun.agno_agent.tools.context_retrieve_tool import context_retrieve_tool
from qiaoyun.prompt.system_prompt import SYSTEMPROMPT_小说越狱

# ========== 动态 instructions 函数 ==========

def get_query_rewrite_instructions(run_context: RunContext) -> str:
    """动态渲染 QueryRewrite 的 system prompt"""
    session_state = run_context.session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        import logging
        logging.warning(f"Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱

def get_chat_response_instructions(run_context: RunContext) -> str:
    """动态渲染 ChatResponse 的 system prompt"""
    session_state = run_context.session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        import logging
        logging.warning(f"Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱

def get_post_analyze_instructions(run_context: RunContext) -> str:
    """动态渲染 PostAnalyze 的 system prompt"""
    session_state = run_context.session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        import logging
        logging.warning(f"Prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱

# ========== 模块级预创建 Agent ==========

query_rewrite_agent = Agent(
    id="query-rewrite-agent",
    name="QueryRewriteAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=get_query_rewrite_instructions,
    response_model=QueryRewriteResponse,
    markdown=False,
)

reminder_detect_agent = Agent(
    id="reminder-detect-agent",
    name="ReminderDetectAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[reminder_tool],
    instructions="检测用户消息中的提醒意图，如果有提醒需求则调用 reminder_tool 创建提醒",
    markdown=False,
)

context_retrieve_agent = Agent(
    id="context-retrieve-agent",
    name="ContextRetrieveAgent",
    model=DeepSeek(id="deepseek-chat"),
    tools=[context_retrieve_tool],
    instructions="根据问题重写结果检索相关上下文",
    markdown=False,
)

chat_response_agent = Agent(
    id="chat-response-agent",
    name="ChatResponseAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=get_chat_response_instructions,
    response_model=ChatResponse,
    markdown=False,
)

post_analyze_agent = Agent(
    id="post-analyze-agent",
    name="PostAnalyzeAgent",
    model=DeepSeek(id="deepseek-chat"),
    instructions=get_post_analyze_instructions,
    response_model=PostAnalyzeResponse,
    markdown=False,
)
```

##### 6.3.5.2 准备阶段 Workflow (prepare_workflow.py)

**功能**：执行 QueryRewrite + ReminderDetect + ContextRetrieve

```python
# qiaoyun/agno_agent/workflows/prepare_workflow.py

from typing import Any, Dict
from qiaoyun.agno_agent.agents import (
    query_rewrite_agent,
    reminder_detect_agent,
    context_retrieve_agent,
)
from qiaoyun.prompt.chat_taskprompt import TASKPROMPT_问题重写

class PrepareWorkflow:
    """准备阶段 Workflow：问题重写 + 提醒检测 + 上下文检索
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow，
    因为需要 Runner 层控制分段执行和打断检测。
    """
    
    userp_template = TASKPROMPT_问题重写  # user prompt 模板
    
    def run(self, input: str, session_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行准备阶段
        
        Args:
            input: 用户输入消息
            session_state: 上下文状态
            
        Returns:
            更新后的 session_state
        """
        session_state = session_state or {}
        
        # 1. 问题重写
        try:
            rendered_userp = self.userp_template.format(**session_state)
        except KeyError:
            rendered_userp = input
            
        qr_response = query_rewrite_agent.run(
            message=rendered_userp,
            session_state=session_state
        )
        if qr_response.content:
            session_state["query_rewrite"] = qr_response.content
        
        # 2. 提醒检测
        reminder_detect_agent.run(
            message=input,
            session_state=session_state
        )
        
        # 3. 上下文检索
        cr_response = context_retrieve_agent.run(
            message=str(session_state.get("query_rewrite", {})),
            session_state=session_state
        )
        if cr_response.content:
            session_state["context_retrieve"] = cr_response.content
        
        return session_state
```

##### 6.3.5.3 回复生成 Workflow (chat_workflow.py)

**功能**：基于准备阶段的结果生成回复

```python
# qiaoyun/agno_agent/workflows/chat_workflow.py

from typing import Any, Dict
from qiaoyun.agno_agent.agents import chat_response_agent
from qiaoyun.prompt.chat_taskprompt import TASKPROMPT_小说书写任务
from qiaoyun.prompt.chat_contextprompt import (
    CONTEXTPROMPT_时间,
    CONTEXTPROMPT_最近的历史对话,
    CONTEXTPROMPT_人物资料,
    CONTEXTPROMPT_用户资料,
)

class ChatWorkflow:
    """回复生成 Workflow
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow。
    """
    
    # user prompt 模板组合
    userp_template = (
    
        CONTEXTPROMPT_时间 +
        CONTEXTPROMPT_人物资料 +
        CONTEXTPROMPT_用户资料 +
        CONTEXTPROMPT_最近的历史对话
    )
    
    def run(self, input: str, session_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行回复生成
        
        Args:
            input: 用户输入消息
            session_state: 上下文状态（包含 query_rewrite 和 context_retrieve 结果）
            
        Returns:
            包含 content 和 session_state 的结果字典
        """
        session_state = session_state or {}
        
        # 渲染 user prompt
        try:
            rendered_userp = self.userp_template.format(**session_state)
        except KeyError as e:
            import logging
            logging.warning(f"User prompt 渲染缺少字段: {e}")
            rendered_userp = input
        
        # 调用 Agent 生成回复
        response = chat_response_agent.run(
            message=rendered_userp,
            session_state=session_state
        )
        
        # 提取回复内容
        content = response.content if response.content else {}
        
        return {
            "content": content,
            "session_state": session_state
        }
```

##### 6.3.5.4 后处理 Workflow (post_analyze_workflow.py)

**功能**：总结对话，更新用户/角色记忆

```python
# qiaoyun/agno_agent/workflows/post_analyze_workflow.py

from typing import Any, Dict
from qiaoyun.agno_agent.agents import post_analyze_agent
from qiaoyun.prompt.chat_taskprompt import TASKPROMPT_后处理分析
from qiaoyun.prompt.chat_contextprompt import CONTEXTPROMPT_最新聊天消息_双方

class PostAnalyzeWorkflow:
    """后处理 Workflow：总结对话，更新记忆
    
    注意：这是自定义 Workflow 类，不继承 Agno Workflow。
    """
    
    userp_template = TASKPROMPT_后处理分析 + CONTEXTPROMPT_最新聊天消息_双方
    
    def run(self, session_state: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行后处理分析
        
        Args:
            session_state: 上下文状态（需包含 MultiModalResponses）
            
        Returns:
            分析结果
        """
        session_state = session_state or {}
        
        # 渲染 user prompt
        try:
            rendered_userp = self.userp_template.format(**session_state)
        except KeyError as e:
            import logging
            logging.warning(f"User prompt 渲染缺少字段: {e}")
            rendered_userp = "请分析本次对话"
        
        # 调用 Agent 进行后处理分析
        response = post_analyze_agent.run(
            message=rendered_userp,
            session_state=session_state
        )
        
        return response.content if response.content else {}
```

**PostAnalyze 输入说明**：

PostAnalyze 需要 `context["MultiModalResponses"]` 作为输入，这个字段在 Runner 层设置：

```python
# Runner 层在发送消息后设置
context["MultiModalResponses"] = multimodal_responses
```

PostAnalyze 的 Prompt 模板 `CONTEXTPROMPT_最新聊天消息_双方` 会引用这个字段。

##### 6.3.5.5 主动消息 Workflow (proactive_message_workflow.py)

**对应需求：** FR-036, FR-037, FR-038, FR-039

> 主动消息 Workflow 由独立的定时服务调用，不在主对话流程中。


### 6.4 Framework 层 (替换)

#### 6.4.1 废弃组件

以下组件将被 Agno 框架替代，迁移完成后可删除：

| 文件 | 替代方案 |
|------|----------|
| `framework/agent/base_agent.py` | `agno.agent.Agent` |
| `framework/agent/llmagent/base_singleroundllmagent.py` | `agno.models.*` |
| `framework/agent/llmagent/doubao_llmagent.py` | `agno.models.deepseek.DeepSeek` |

#### 6.4.2 功能对照

| 自研功能 | Agno 替代 |
|----------|-----------|
| `BaseAgent._prehandle()` | Agent 内置 pre_hook |
| `BaseAgent._execute()` | Agent.run() 自动执行 |
| `BaseAgent._posthandle()` | Agent 内置 post_hook |
| `BaseAgent.run()` 生成器 | Agent.run() 返回 RunResponse |
| `AgentStatus` 状态机 | Agno 内置状态管理 |
| 重试机制 | Agno 内置重试 |
| Prompt 模板渲染 | instructions + session_state |
| JSON Schema 输出 | Pydantic response_model |

### 6.5 Prompt 迁移策略

#### 6.5.1 现有 Prompt 结构

现有系统使用 Python 字符串格式化的嵌套字典访问语法：

```python
# 现有方式：使用 {dict[key1][key2]} 模板语法
userp_template = """
## 上下文
{conversation[conversation_info][time_str]}

## 角色信息
{character[name]}

## 历史对话
{conversation[conversation_info][chat_history_str]}
"""

# 渲染方式
rendered_prompt = userp_template.format(**context)
```

#### 6.5.2 Agno 动态 instructions 研究

**研究结论**：Agno 支持动态 instructions，可以通过函数方式实现。

Agno 的 `instructions` 参数支持两种方式：
1. **静态字符串/列表**：直接传入固定的指令
2. **动态函数**：传入一个接收 `RunContext` 的函数，每次运行时动态生成指令

**动态 instructions 示例**：

```python
from agno.agent import Agent
from agno.run import RunContext

def get_instructions(run_context: RunContext):
    """根据 session_state 动态生成 instructions"""
    if not run_context.session_state:
        run_context.session_state = {}
    
    # 可以访问 session_state 中的任何数据
    user_name = run_context.session_state.get("user", {}).get("name", "用户")
    character_name = run_context.session_state.get("character", {}).get("name", "角色")
    
    return f"你是{character_name}，正在与{user_name}对话。请保持角色一致性。"

agent = Agent(
    instructions=get_instructions,  # 传入函数而非字符串
    model=DeepSeek(id="deepseek-chat"),
)
```

**但是**：动态 instructions 函数只能访问 `run_context.session_state`，无法直接使用我们现有的 `{dict[key1][key2]}` 模板语法。

#### 6.5.3 迁移方案选择

> **决策已确认**：采用组合方式（方案 D）

| 方案 | 说明 | 评估 |
|------|------|------|
| A（str.format + 动态函数）| 在动态函数中使用 str.format 渲染模板 | ⚠️ 可行但不够清晰 |
| B（迁移到 Jinja2）| 支持 `{{ value \| default('') }}` 语法 | ❌ 改动大 |
| C（纯 Agno 方式）| 完全重写 Prompt 为 Agno 风格 | ❌ 需重写 Prompt |
| D（组合方式）| system prompt 用动态函数，user prompt 在 Workflow 中渲染 | ✅ 选择 |

**组合方式详细说明**：

原系统的 Prompt 分为两部分：
- **system prompt**（`systemp_template`）：角色设定、行为规范等，相对固定
- **user prompt**（`userp_template`）：包含动态内容（时间、历史对话、检索结果等）

迁移后的处理方式：
- **system prompt** → 使用 Agno 动态 instructions 函数，在函数内部使用 str.format 渲染
- **user prompt** → 在 Workflow 中渲染后，通过 `message` 参数传入 Agent

**实现示例**：

```python
# system prompt 使用动态 instructions 函数
def get_chat_response_instructions(run_context: RunContext):
    from qiaoyun.prompt.system_prompt import SYSTEMPROMPT_小说越狱
    session_state = run_context.session_state or {}
    try:
        return SYSTEMPROMPT_小说越狱.format(**session_state)
    except KeyError as e:
        import logging
        logging.warning(f"System prompt 渲染缺少字段: {e}")
        return SYSTEMPROMPT_小说越狱

# Agent 定义
chat_response_agent = Agent(
    instructions=get_chat_response_instructions,  # 动态 system prompt
    model=DeepSeek(id="deepseek-chat"),
    response_model=ChatResponse,
)

# Workflow 中渲染 user prompt
class QiaoyunChatWorkflow(Workflow):
    userp_template = TASKPROMPT_小说书写任务 + CONTEXTPROMPT_时间 + ...
    
    def run(self, input: str, **kwargs):
        session_state = kwargs.get("session_state", {})
        
        # 渲染 user prompt
        rendered_userp = self.userp_template.format(**session_state)
        
        # 传入 Agent
        response = chat_response_agent.run(
            message=rendered_userp,  # 渲染后的 user prompt
            session_state=session_state
        )
```

**选择理由**：
1. Prompt 是经过调优的核心资产，不应轻易改动
2. 组合方式清晰地分离了 system prompt 和 user prompt 的处理
3. 与 Agno 的设计理念一致（instructions 对应 system prompt，message 对应 user prompt）
4. 迁移风险最小，后续有需要再逐步重构

#### 6.5.4 context_prepare() 默认值设置

**风险缓解措施：**

根据 Prompt 模板分析，需要在 `context_prepare()` 中为以下字段设置默认值：

**完整的默认值设置代码：**

```python
# qiaoyun/runner/context.py

def context_prepare(user, character, conversation):
    context = {
        "user": user,
        "character": character,
        "conversation": conversation
    }
    
    # ... 现有逻辑 ...
    
    # ========== 新增：Prompt 模板所需字段的默认值 ==========
    
    # 顶层字段默认值
    context.setdefault("repeated_input_notice", "")
    context.setdefault("news_str", "")
    context.setdefault("MultiModalResponses", [])
    
    # context_retrieve 相关字段（由 ContextRetrieveAgent 填充）
    context.setdefault("context_retrieve", {
        "character_global": "",
        "character_private": "",
        "user": "",
        "character_knowledge": "",
        "character_photo": "",
        "confirmed_reminders": ""
    })
    
    # query_rewrite 相关字段（由 QueryRewriteAgent 填充）
    context.setdefault("query_rewrite", {
        "CharacterSettingQueryQuestion": "",
        "CharacterSettingQueryKeywords": "",
        "UserProfileQueryQuestion": "",
        "UserProfileQueryKeywords": "",
        "CharacterKnowledgeQueryQuestion": "",
        "CharacterKnowledgeQueryKeywords": ""
    })
    
    # conversation.conversation_info 字段默认值
    conv_info = context["conversation"]["conversation_info"]
    conv_info.setdefault("time_str", "")
    conv_info.setdefault("chat_history_str", "")
    conv_info.setdefault("input_messages_str", "")
    conv_info.setdefault("chat_history", [])
    conv_info.setdefault("input_messages", [])
    conv_info.setdefault("photo_history", [])
    conv_info.setdefault("future", {"timestamp": None, "action": None})
    
    # user 字段默认值
    context["user"].setdefault("platforms", {}).setdefault("wechat", {
        "id": "",
        "nickname": "用户"
    })
    
    # character 字段默认值
    context["character"].setdefault("platforms", {}).setdefault("wechat", {
        "id": "",
        "nickname": "角色"
    })
    context["character"].setdefault("user_info", {
        "description": "",
        "status": {"place": "未知", "action": "未知"}
    })
    
    # relation 字段默认值
    context["relation"].setdefault("relationship", {
        "description": "",
        "closeness": 20,
        "trustness": 20,
        "dislike": 0,
        "status": "空闲"
    })
    context["relation"].setdefault("user_info", {
        "realname": "",
        "hobbyname": "",
        "description": ""
    })
    context["relation"].setdefault("character_info", {
        "longterm_purpose": "",
        "shortterm_purpose": "",
        "attitude": ""
    })
    
    # ObjectId 序列化处理
    context = _convert_objectid_to_str(context)
    
    return context

def _convert_objectid_to_str(obj):
    """递归将 dict 中的 ObjectId 转换为字符串"""
    from bson import ObjectId
    
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_objectid_to_str(item) for item in obj]
    else:
        return obj
```

**Prompt 模板字段依赖清单：**

| Prompt 模板 | 依赖字段 | 默认值设置 |
|-------------|----------|-----------|
| CONTEXTPROMPT_时间 | `conversation[conversation_info][time_str]` | ✅ |
| CONTEXTPROMPT_新闻 | `news_str` | ✅ |
| CONTEXTPROMPT_人物信息 | `character[platforms][wechat][nickname]`, `character[user_info][description]` | ✅ |
| CONTEXTPROMPT_人物资料 | `context_retrieve[character_global]`, `context_retrieve[character_private]` | ✅ |
| CONTEXTPROMPT_用户资料 | `user[platforms][wechat][nickname]`, `context_retrieve[user]` | ✅ |
| CONTEXTPROMPT_待办提醒 | `context_retrieve[confirmed_reminders]` | ✅ |
| CONTEXTPROMPT_人物知识和技能 | `context_retrieve[character_knowledge]` | ✅ |
| CONTEXTPROMPT_人物手机相册 | `context_retrieve[character_photo]` | ✅ |
| CONTEXTPROMPT_人物状态 | `character[user_info][status][place]`, `character[user_info][status][action]`, `relation[relationship][status]` | ✅ |
| CONTEXTPROMPT_当前目标 | `relation[character_info][longterm_purpose]`, `relation[character_info][shortterm_purpose]`, `relation[character_info][attitude]` | ✅ |
| CONTEXTPROMPT_当前的人物关系 | `relation[relationship][*]`, `relation[user_info][*]` | ✅ |
| CONTEXTPROMPT_最近的历史对话 | `conversation[conversation_info][chat_history_str]` | ✅ |
| CONTEXTPROMPT_最新聊天消息 | `conversation[conversation_info][input_messages_str]` | ✅ |
| CONTEXTPROMPT_初步回复 | `MultiModalResponses` | ✅ |
| CONTEXTPROMPT_规划行动 | `conversation[conversation_info][future][action]` | ✅ |
| NOTICE_重复消息处理 | `repeated_input_notice` | ✅ |

> **已确认**：所有 Prompt 模板变量都已在 `context_prepare()` 中设置默认值。
| NOTICE_重复消息处理 | `repeated_input_notice` |

#### 6.5.5 Agent 实例化方式

**决策：采用模块级预创建 + 动态 instructions 函数**

| 方案 | 说明 | 评估 |
|------|------|------|
| A（每次创建新实例） | 在 run() 中创建 Agent | ⚠️ 有实例化开销 |
| B（类级别预创建） | 在 Workflow 类中预创建 Agent | ❌ instructions 固定，无法动态渲染 |
| C（模块级预创建 + 动态函数） | 使用 Agno 动态 instructions | ✅ 推荐 |

> **实现代码**：详见 [6.3.5.1 Agent 模块级预创建](#6351-agent-模块级预创建-agentspy)

**关键点**：
- Agent 在模块级别预创建，避免每次调用的实例化开销
- 通过动态 instructions 函数实现 Prompt 渲染
- 预创建的 Agent 是无状态的，状态通过 session_state 传递

### 6.6 依赖配置

#### 6.6.1 新增依赖

```txt
# requirements.txt 新增
agno>=2.0.0
deepseek-sdk>=1.0.0  # 如果需要
pydantic>=2.0.0
```

#### 6.6.2 环境变量

```bash
# .env 新增
DEEPSEEK_API_KEY=your-api-key

# 可选：如果使用其他模型
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```


---

## 7. 迁移计划

### 7.1 阶段划分

```
Phase 1: 基础设施准备
    ↓
Phase 2: Schema 定义
    ↓
Phase 3: Tool 开发
    ↓
Phase 4: Agent 迁移
    ↓
Phase 5: Workflow 编排
    ↓
Phase 6: Runner 层适配
    ↓
Phase 7: 集成测试
    ↓
Phase 8: 发布上线
```

### 7.2 各阶段任务清单

#### Phase 1: 基础设施准备

| 任务 | 产出 |
|------|------|
| 安装 Agno 依赖 | requirements.txt 更新 |
| 配置 DeepSeek API | .env 配置 |
| 创建目录结构 | qiaoyun/agno_agent/ |
| 验证 Agno 基础功能 | 简单 Agent 测试通过 |

#### Phase 2: Schema 定义

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 定义 QueryRewriteResponse | schemas/query_rewrite_schema.py | FR-010 |
| 定义 ChatResponse | schemas/chat_response_schema.py | FR-012 |
| 定义 PostAnalyzeResponse | schemas/post_analyze_schema.py | FR-014 |
| 定义 ReminderSchema | schemas/reminder_schema.py | FR-017~021 |
| 定义 FutureMessageSchema | schemas/future_message_schema.py | FR-036 |

#### Phase 3: Tool 开发

**核心 Tool**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 实现 context_retrieve_tool | tools/context_retrieve_tool.py | FR-011, FR-056 |
| 实现 reminder_tools | tools/reminder_tools.py | FR-018~021 |

**语音 Tool**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 实现 voice2text_tool | tools/voice_tools.py | FR-004, FR-051 |
| 实现 text2voice_tool | tools/voice_tools.py | FR-005, FR-052, FR-053 |

**图片 Tool**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 实现 image2text_tool | tools/image_tools.py | FR-006, FR-045 |
| 实现 image_send_tool | tools/image_tools.py | FR-007 |
| 实现 image_generate_tool | tools/image_tools.py | FR-046 |

**其他 Tool**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 实现 album_tools | tools/album_tools.py | FR-064 |
| 实现 moments_tool | tools/moments_tool.py | FR-063 |

#### Phase 4: Agent 迁移

**核心对话 Agent**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 迁移 QueryRewriteAgent | agents/query_rewrite_agent.py | FR-010 |
| 迁移 ChatResponseAgent | agents/chat_response_agent.py | FR-012 |
| 迁移 PostAnalyzeAgent | agents/post_analyze_agent.py | FR-014 |

**提醒和主动消息 Agent**

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 迁移 ReminderDetectAgent | agents/reminder_detect_agent.py | FR-017 |
| 新建 FutureMessagePlanAgent | agents/future_message_plan_agent.py | FR-036 |
| 新建 ProactiveMessageAgent | agents/proactive_message_agent.py | FR-038 |

#### Phase 5: Workflow 编排

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 实现 QiaoyunChatWorkflow | workflows/chat_workflow.py | FR-009~012, FR-014, FR-017 |
| 实现 ProactiveMessageWorkflow | workflows/proactive_message_workflow.py | FR-036~039 |

#### Phase 6: Runner 层适配

| 任务 | 产出 | 对应需求 |
|------|------|----------|
| 修改 context.py | session_state 兼容 | - |
| 修改 qiaoyun_handler.py | Agno 调用集成 | FR-009 |
| 消息打断逻辑适配 | ROLLBACK 机制 | FR-009 |
| 分段消息发送适配 | 多消息处理 | FR-016 |
| 消息 Hold 逻辑适配 | 忙闲状态处理 | FR-034 |

#### Phase 7: 集成测试

| 测试类型 | 验证内容 |
|----------|----------|
| 消息处理模块测试 | FR-001~009 |
| 对话处理模块测试 | FR-010~016 |
| 提醒管理模块测试 | FR-017~024 |
| 关系管理模块测试 | FR-025~031 |
| 角色状态模块测试 | FR-032~035 |
| 主动消息模块测试 | FR-036~039 |
| 性能测试 | NFR-001 |
| 可用性测试 | NFR-002 |
| 异常场景测试 | 异常处理验证 |

#### Phase 8: 发布上线

| 任务 | 产出 |
|------|------|
| 部署新版本 | 生产环境更新 |
| 验证核心功能 | 功能正常 |
| 旧代码清理 | framework/ 和旧 agent/ 删除 |

### 7.4 回滚方案

使用 Git 进行版本管理和回滚，而非文件复制。

#### 7.4.1 Git 分支策略

```
main (生产稳定版)
  │
  ├── feature/agno-migration (迁移开发分支)
  │     ├── Phase 1 commit: 基础设施准备
  │     ├── Phase 2 commit: Schema 和 Tool 开发
  │     ├── Phase 3 commit: Agent 迁移
  │     ├── Phase 4 commit: Workflow 编排
  │     ├── Phase 5 commit: Runner 层适配
  │     └── Phase 6 commit: 集成测试修复
  │
  └── release/agno-v1.0 (发布分支)
```

#### 7.4.2 回滚操作

| 场景 | 回滚命令 | 说明 |
|------|----------|------|
| 开发阶段回滚 | `git checkout main` | 切回主分支继续旧逻辑 |
| 灰度阶段回滚 | `git revert <commit>` | 撤销特定提交 |
| 生产紧急回滚 | `git checkout <tag>` | 回退到上一个稳定 tag |

#### 7.4.3 关键 Tag 规划

```bash
# 迁移前打 tag
git tag -a v1.0-pre-agno -m "迁移前稳定版本"

# 迁移完成后打 tag
git tag -a v2.0-agno -m "Agno 迁移完成"
```

#### 7.4.4 功能开关（可选）

如需更细粒度的控制，可在代码中保留开关：

```python
# qiaoyun_handler.py
USE_AGNO = os.getenv("USE_AGNO", "true").lower() == "true"
```

但主要依赖 Git 进行版本管理，功能开关仅作为灰度期间的辅助手段。


---

## 8. 风险评估与应对

### 8.1 风险矩阵

| 风险 | 可能性 | 影响 | 风险等级 | 应对措施 | 决策状态 |
|------|--------|------|----------|----------|----------|
| session_state 兼容性问题 | 中 | 高 | 高 | Phase 1 做 PoC 验证（含嵌套修改测试） | ✅ 已确认测试方案（PoC 未开始） |
| ObjectId 序列化问题 | 高 | 中 | 高 | context_prepare() 中统一转字符串，DAO 层无需修改 | ✅ 已确认方案 |
| Prompt 迁移后效果下降 | 中 | 高 | 高 | 保留原 Prompt，使用组合方式（方案 D） | ✅ 已确认方案 |
| 消息打断机制降级 | 中 | 中 | 中 | 异步检测 + 提前终止（方案 D） | ✅ 已确认方案 |
| Agent 实例化性能 | 中 | 低 | 低 | 模块级预创建 + 动态 instructions | ✅ 已确认方案 |
| PostAnalyze 执行时机 | 低 | 中 | 低 | Runner 层控制，被打断时跳过 | ✅ 已确认方案 |
| Tool 开发工作量超预期 | 中 | 中 | 中 | 分类处理，优先复用；reminder_tool 统一为一个 Tool | ✅ 已确认方案 |
| Agno 框架 Bug | 低 | 中 | 中 | 使用 agno>=2.0.0，关注社区 | ✅ 已确认 |
| 性能下降 | 低 | 中 | 中 | 性能测试，必要时优化 | 暂不明确基准 |
| 迁移周期超期 | 中 | 低 | 中 | 预留缓冲时间 | - |
| 团队学习成本 | 低 | 低 | 低 | 提前培训，文档准备 | - |

### 8.2 详细风险分析

#### 8.2.1 Prompt 迁移风险

**风险描述：** 现有 Prompt 使用 `{context[...]}` 模板语法，迁移到 Agno 后需要调整为动态 message 构建，可能影响生成效果。

**应对措施：**
1. 保持 Prompt 内容不变，仅调整注入方式
2. 建立 A/B 测试机制，对比新旧效果
3. 准备 Prompt 调优迭代计划

#### 8.2.2 模型切换（已验证）

**决策：直接使用 DeepSeek 模型**

DeepSeek 模型已经过验证，确认可以满足业务需求：
1. DeepSeek 在角色扮演和中文对话方面表现优秀
2. JSON 输出格式稳定性已验证
3. 不再保留 Doubao 模型，简化迁移复杂度

**模型配置：**

```python
from agno.models.deepseek import DeepSeek

# 统一使用 DeepSeek
model = DeepSeek(id="deepseek-chat")
```

**上线后监控指标：**
- JSON 输出格式错误率 < 5%
- 用户负面反馈率 < 10%

#### 8.2.3 性能风险

**风险描述：** Agno 框架引入额外抽象层，可能影响响应延迟。

**应对措施：**
1. 迁移前后进行性能基准测试
2. 监控关键指标：首字延迟、总响应时间
3. 必要时优化 Tool 调用和检索逻辑

### 8.3 应急预案

| 场景 | 触发条件 | 应急措施 |
|------|----------|----------|
| 生成效果严重下降 | 用户投诉率 > 10% | 回滚到旧实现 |
| 系统不可用 | 错误率 > 5% | 回滚到旧实现 |
| 性能严重下降 | P99 延迟 > 30s | 回滚或降级 |
| 模型服务不可用 | DeepSeek API 故障 | 切换备用模型 |


---

## 9. 附录

### 9.1 Agno 框架核心概念

#### 9.1.1 Agent

```python
from agno.agent import Agent
from agno.models.deepseek import DeepSeek

agent = Agent(
    id="my-agent",                    # 唯一标识
    name="My Agent",                  # 显示名称
    model=DeepSeek(id="deepseek-chat"),  # LLM 模型
    instructions=["..."],             # 系统指令
    tools=[...],                      # 可用工具
    response_model=MySchema,          # Pydantic 响应模型
    markdown=False,                   # 是否 Markdown 格式
)

# 运行
response = agent.run(
    message="用户输入",
    session_state={"key": "value"},   # 状态传递
)
```

#### 9.1.2 Tool

```python
from agno.tools import tool

@tool(description="工具描述")
def my_tool(param1: str, param2: int) -> str:
    """
    工具函数
    
    Args:
        param1: 参数1描述
        param2: 参数2描述
    
    Returns:
        返回值描述
    """
    return "result"
```

#### 9.1.3 Team

```python
from agno.team import Team

team = Team(
    name="My Team",
    mode="coordinate",  # coordinate | route | collaborate
    members=[agent1, agent2, agent3],
    tools=[tool1, tool2],
    instructions=["团队指令"],
)

response = team.run(message="用户输入")
```

#### 9.1.4 Workflow

```python
from agno.workflow import Workflow, RunResponse

class MyWorkflow(Workflow):
    def run(self, message: str, session_state: dict = None) -> RunResponse:
        # 自定义流程逻辑
        result1 = self.agent1.run(message)
        result2 = self.agent2.run(result1.content)
        return RunResponse(content=result2.content)
```

### 9.2 现有代码关键片段

#### 9.2.1 BaseAgent 状态机

```python
class AgentStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    MESSAGE = "message"      # 有消息输出
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    ROLLBACK = "rollback"    # 新消息打断
    CLEAR = "clear"
    FINISHED = "finished"
```

#### 9.2.2 现有 Pipeline 调用

```python
# QiaoyunChatAgent._execute()
def _execute(self):
    # 问题重写
    c = QiaoyunQueryRewriteAgent(self.context)
    for result in c.run():
        if result["status"] == AgentStatus.FINISHED.value:
            self.context["query_rewrite"] = result["resp"]
    
    # 上下文检索
    c = QiaoyunContextRetrieveAgent(self.context)
    for result in c.run():
        if result["status"] == AgentStatus.FINISHED.value:
            self.context["context_retrieve"] = result["resp"]
    
    # 生成回复
    c = QiaoyunChatResponseAgent(self.context)
    for result in c.run():
        if result["status"] == AgentStatus.FINISHED.value:
            self.resp = result["resp"]
    
    self.status = AgentStatus.MESSAGE
    yield self.resp
    
    # 后处理
    c = QiaoyunPostAnalyzeAgent(self.context)
    for result in c.run():
        pass
```

### 9.3 测试用例清单

#### 9.3.1 Agent 单元测试

| 测试项 | 预期结果 | 对应需求 |
|--------|----------|----------|
| QueryRewriteAgent 输出格式 | 符合 Schema 定义 | FR-010 |
| ChatResponseAgent 输出格式 | 符合 Schema 定义 | FR-012 |
| PostAnalyzeAgent 输出格式 | 符合 Schema 定义 | FR-014 |
| ReminderDetectAgent 输出格式 | 符合 Schema 定义 | FR-017 |
| FutureMessagePlanAgent 输出格式 | 符合 Schema 定义 | FR-036 |
| ProactiveMessageAgent 输出格式 | 符合 Schema 定义 | FR-038 |

#### 9.3.2 Tool 单元测试

| 测试项 | 预期结果 | 对应需求 |
|--------|----------|----------|
| voice2text_tool 语音识别 | 返回正确文字 | FR-004, FR-051 |
| text2voice_tool 语音合成 | 返回音频URL | FR-005, FR-052 |
| text2voice_tool 情感语音 | 支持多种情感 | FR-053 |
| image2text_tool 图片识别 | 返回图片描述 | FR-006, FR-045 |
| image_send_tool 图片发送 | 发送成功 | FR-007 |
| image_generate_tool 文生图 | 返回图片URL | FR-046 |
| context_retrieve_tool 检索 | 返回正确格式 | FR-011, FR-056 |
| reminder_create_tool 创建提醒 | 创建成功 | FR-018 |
| reminder_update_tool 更新提醒 | 更新成功 | FR-019 |
| reminder_delete_tool 删除提醒 | 删除成功 | FR-020 |
| reminder_list_tool 查看提醒 | 返回列表 | FR-021 |
| photo_delete_tool 照片删除 | 删除成功 | FR-064 |
| moments_publish_tool 朋友圈发布 | 发布成功 | FR-063 |

#### 9.3.3 Workflow 集成测试

| 测试项 | 预期结果 | 对应需求 |
|--------|----------|----------|
| QiaoyunChatWorkflow 完整流程 | 各步骤正常执行 | FR-009~014 |
| QiaoyunChatWorkflow session_state 传递 | 状态正确更新 | - |
| QiaoyunChatWorkflow 消息打断 | ROLLBACK 正常 | FR-009 |
| ProactiveMessageWorkflow 完整流程 | 主动消息生成成功 | FR-036~039 |
| ProactiveMessageWorkflow 频率控制 | 超频时不发送 | FR-039 |

#### 9.3.4 端到端测试

| 测试项 | 预期结果 | 对应需求 |
|--------|----------|----------|
| 文本消息处理流程 | 输入→处理→输出正常 | FR-003 |
| 语音消息处理流程 | 语音→文字→回复正常 | FR-004, FR-005 |
| 图片消息处理流程 | 图片→识别→回复正常 | FR-006, FR-007 |
| 引用消息处理流程 | 引用解析正确 | FR-008 |
| 提醒创建流程 | 提醒创建成功 | FR-017~018 |
| 提醒触发流程 | 定时触发正常 | FR-022 |
| 主动消息流程 | 主动消息发送正常 | FR-037~038 |

#### 9.3.5 性能测试

| 测试项 | 预期结果 | 对应需求 |
|--------|----------|----------|
| 响应延迟 | P99 < 20s | NFR-001 |
| 错误率 | < 1% | NFR-002 |
| 并发处理 | 多用户并发正常 | NFR-003 |

#### 9.3.6 异常测试

| 测试项 | 预期结果 |
|--------|----------|
| LLM 调用失败 | 正确重试和降级 |
| 检索服务不可用 | 优雅降级 |
| 语音服务不可用 | 返回错误提示 |
| 图片服务不可用 | 返回错误提示 |
| MongoDB 连接失败 | 正确重试 |

### 9.4 参考资料

- [Agno 官方文档](https://docs.agno.com)
- [Agno GitHub](https://github.com/agno-agi/agno)
- [DeepSeek API 文档](https://platform.deepseek.com/docs)
- [Pydantic 文档](https://docs.pydantic.dev)

### 9.5 术语表

| 术语 | 说明 |
|------|------|
| Agent | 具有特定能力的 AI 代理 |
| Tool | Agent 可调用的工具函数 |
| Team | 多 Agent 协作组 |
| Workflow | 自定义流程编排 |
| session_state | Agno 中的状态传递机制 |
| response_model | Pydantic 定义的响应格式 |
| instructions | Agent 的系统指令 |
| RunResponse | Agent 运行的返回结果 |

---

## 变更记录

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|----------|
| v1.0 | 2025-12-03 | 架构组 | 初始版本 |
| v1.1 | 2025-12-03 | 架构组 | 1. 新增原系统需求分析章节 2. 补充消息状态机迁移方案 3. 精简代码示例 4. 回滚方案改用 Git 管理 |
| v1.2 | 2025-12-03 | 架构组 | **完整需求覆盖更新**：1. 需求分析从13项扩展到69项完整需求 2. 新增12个模块的需求分类 3. 新增15个Tool定义 4. 新增5个Agent定义 5. 新增3个Workflow定义 6. 测试用例扩展到完整覆盖 |
| v1.3 | 2025-12-03 | 架构组 | 简化迁移计划，移除工期估算和里程碑日期 |
| v1.4 | 2025-12-03 | 架构组 | 1. 完善 FR-009 消息打断机制的详细说明 2. 更新 Prompt 迁移策略为"保留现有模板，调用前渲染" 3. 详细设计消息打断机制的 Workflow 层和 Runner 层实现方案 |
| v1.5 | 2025-12-04 | 架构组 | **技术决策确认**：1. 新增 session_state 兼容性验证章节（含 PoC 测试用例）2. 消息打断机制确认选择方案 A（步骤间检测）3. 模型切换确认直接使用 DeepSeek 4. Prompt 迁移确认选择方案 A（保持 str.format）5. Tool 迁移策略分类（A-可直接复用/B-待讨论/C-Agno内置）6. 灰度发布确认选择方案 A（全量上线+Git回滚）|
| v1.6 | 2025-12-04 | 架构组 | **评审反馈更新**：1. PoC 测试场景扩展（新增 Workflow 嵌套修改、run_context 修改、多 Agent 状态传递测试）2. ObjectId 序列化问题分析及解决方案 3. 消息打断机制升级为方案 D（异步检测 + 提前终止，粒度 1-2 秒）4. Agent 实例化方式对比分析（选择模块级预创建 + 动态 instructions）5. PostAnalyze 执行时机分析（Runner 层控制）6. 移除 Doubao 模型相关内容（DeepSeek 已验证）7. Agno 动态 instructions 研究 8. context_prepare() 完整默认值设置 |
| v1.7 | 2025-12-04 | 架构组 | **评审决策确认**：1. 消息打断机制确认方案 D（调用前检测 + 调用中异步检测 + 调用后检测）2. Tool 迁移决策：context_retrieve 封装为 Tool，reminder_tool 统一为一个 Tool（通过 action 参数区分 CRUD）3. Prompt 迁移确认组合方式（system prompt 用动态函数，user prompt 在 Workflow 中渲染）4. 确认 DAO 层无需修改（已做兼容处理）5. 取消 FR-013 回复优化 Agent（随机触发不稳定）6. 取消每日任务模块（FR-040~044）和相册检索（FR-049）7. Agno 版本使用 agno>=2.0.0 8. 明确 PoC 测试未开始 9. 统一 Workflow 代码示例使用模块级预创建 Agent |
| v1.8 | 2025-12-04 | 架构组 | **文档清理与一致性更新**：1. 统一 Agent/Tool 列表到需求分析章节，其他位置改为引用 2. 删除重复的 Agent 列表（2.4.2 节末尾）3. 简化 5.2.4 Tool 组件列表 4. 重写 6.2.0.1 消息打断机制为 Runner 层控制 + 分段执行方案 5. 重写 6.3.5 Workflow 编排为三个独立 Workflow（PrepareWorkflow, ChatWorkflow, PostAnalyzeWorkflow）6. 删除 Workflow 中访问数据库的代码 7. 更新 6.3.1 目录结构，删除每日任务相关文件 8. 删除 Phase 2 中 DailyScriptSchema 和 MomentsSchema 9. 删除 Phase 3 中 news_search_tool 和 daily_task_tool 10. 删除 Phase 4 中每日任务 Agent 部分 11. 删除 9.3 节测试用例中每日任务相关测试 12. 移除 ObjectId PoC 测试项（已确认通过）13. 确认 PoC 测试选项 A（正式开发前完成）14. 更新 FR-065 为不迁移（依赖每日任务模块）15. 补充 2.4.2 节 Tool 列表（添加 moments_tool、album_tools）16. 更新 6.4.3 节 Tool 迁移优先级表（添加 P2 优先级 Tool）17. 区分 FR-043（每日任务图片生成，已取消）和 FR-046（独立文生图功能，保留）|
| v1.9 | 2025-12-04 | 架构组 | **Workflow 代码示例统一**：1. 明确不使用 Agno 原生 Step-based Workflow（因需要打断检测）2. 新增 6.3.5.1 Agent 模块级预创建（agents.py）3. 重写 6.3.5.2-6.3.5.4 为自定义 Workflow 类（不继承 Agno Workflow）4. 删除 6.3.5.5 重复的动态 instructions 函数代码（已在 6.3.5.1 定义）5. 简化 6.5.5 节，删除重复代码示例，改为引用 6.3.5.1 6. 修复章节编号重复问题（两个 6.3.5.4）|
| v2.0 | 2025-12-04 | 架构组 | **PoC 测试完成**：1. 执行全部 6 项 PoC 测试，均已通过 2. 更新 4.4 节测试状态为"已通过" 3. 新增 4.4.3 风险消除确认表 4. 删除冗余的测试代码示例 |

---

## 评审意见

> 请评审人员在此处填写评审意见

| 评审人 | 日期 | 意见 |
|--------|------|------|
| | | |
| | | |
| | | |
