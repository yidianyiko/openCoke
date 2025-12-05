# Requirements Document

## Introduction

本需求文档描述主动消息功能（Proactive Message）的实现需求。主动消息是指角色在用户没有主动发起对话的情况下，根据之前的对话规划，主动向用户发送消息的功能。

该功能是 Agno 框架迁移的一部分，涉及以下核心组件：
- **FutureMessagePlanAgent**: 在对话结束时规划未来主动消息的时间和内容
- **ProactiveMessageAgent**: 在触发时间到达时生成主动消息内容
- **ProactiveMessageWorkflow**: 编排主动消息生成的完整流程

详细设计参见：[迁移计划文档](../../../doc/agno-demo/agno-migration-plan.md)

## Glossary

- **主动消息（Proactive Message）**: 角色在用户没有回复的情况下，主动发起的消息
- **未来消息规划（Future Message Plan）**: 在对话结束时规划下一次主动消息的时间和行动
- **FutureMessagePlanAgent**: 负责规划未来主动消息的 Agent
- **ProactiveMessageAgent**: 负责生成主动消息内容的 Agent
- **ProactiveMessageWorkflow**: 编排主动消息生成流程的 Workflow
- **规划行动（Future Action）**: 规划的主动消息触发时角色应执行的行动描述
- **触发时间（Trigger Time）**: 主动消息应该发送的时间点
- **主动消息次数（Proactive Times）**: 连续主动消息的计数，用于频率控制
- **频率控制**: 通过概率衰减机制防止过度骚扰用户

## Requirements

### Requirement 1: 未来消息规划 Schema 定义

**User Story:** As a 开发者, I want to 定义未来消息规划的 Schema, so that Agent 输出格式规范且可验证。

#### Acceptance Criteria

1. WHEN FutureMessagePlanAgent 执行完成 THEN the System SHALL 返回符合 FutureMessageResponse Schema 的结构化数据，包含 InnerMonologue、MultiModalResponses、RelationChange、FutureResponse 字段
2. WHEN FutureResponse 字段被解析 THEN the System SHALL 包含 FutureResponseTime（触发时间）和 FutureResponseAction（规划行动）两个子字段
3. WHEN MultiModalResponse 被解析 THEN the System SHALL 支持 text、voice、photo 三种消息类型

### Requirement 2: 主动消息 Agent 实现

**User Story:** As a 开发者, I want to 实现主动消息相关的 Agent, so that 系统可以规划和生成主动消息。

#### Acceptance Criteria

1. WHEN 对话结束时需要规划未来消息 THEN the FutureMessageQueryRewriteAgent SHALL 基于规划行动进行问题重写，生成检索查询词
2. WHEN 问题重写完成后 THEN the FutureMessageContextRetrieveAgent SHALL 调用 context_retrieve_tool 检索与规划行动相关的上下文
3. WHEN 上下文检索完成后 THEN the FutureMessageChatAgent SHALL 基于角色人设和规划行动生成主动消息内容
4. WHEN Agent 使用动态 instructions THEN the System SHALL 通过函数方式渲染 Prompt 模板，注入 session_state 中的动态数据

### Requirement 3: 主动消息 Workflow 编排

**User Story:** As a 开发者, I want to 使用 Workflow 编排主动消息生成流程, so that 主动消息处理流程清晰可控。

#### Acceptance Criteria

1. WHEN Runner 层调用 FutureMessageWorkflow THEN the System SHALL 顺序执行 QueryRewrite、ContextRetrieve、ChatResponse 三个步骤
2. WHEN FutureMessageWorkflow 执行完成 THEN the System SHALL 返回包含 content 和 session_state 的结果字典
3. WHEN Workflow 执行过程中修改 session_state THEN the System SHALL 正确传递修改后的状态到后续步骤
4. WHEN ChatResponse 生成回复后 THEN the System SHALL 将 MultiModalResponses 保存到 session_state 供后续使用

### Requirement 4: 关系变化处理

**User Story:** As a 系统, I want to 在主动消息生成后更新用户关系, so that 关系数据保持准确。

#### Acceptance Criteria

1. WHEN 主动消息生成包含 RelationChange THEN the System SHALL 更新 session_state 中的 closeness（亲密度）值
2. WHEN 主动消息生成包含 RelationChange THEN the System SHALL 更新 session_state 中的 trustness（信任度）值
3. WHEN 更新 closeness 或 trustness THEN the System SHALL 确保值在 0-100 范围内

### Requirement 5: 未来消息规划处理

**User Story:** As a 系统, I want to 在主动消息发送后规划下一次主动消息, so that 角色可以持续主动互动。

#### Acceptance Criteria

1. WHEN 主动消息发送成功 THEN the System SHALL 增加 proactive_times 计数
2. WHEN 决定是否设置下一次主动消息 THEN the System SHALL 使用概率衰减机制（0.15^(n+1)）控制频率
3. WHEN 概率命中时 THEN the System SHALL 解析 FutureResponseTime 并设置 future.timestamp
4. WHEN 概率命中时 THEN the System SHALL 设置 future.action 为 FutureResponseAction 的值
5. WHEN 概率未命中时 THEN the System SHALL 清除 future.timestamp 和 future.action

### Requirement 6: 主动消息触发服务

**User Story:** As a 系统, I want to 定时检查并触发主动消息, so that 主动消息在规划时间发送。

#### Acceptance Criteria

1. WHEN 定时服务检查主动消息 THEN the System SHALL 查询所有 future.timestamp 已到达的会话
2. WHEN 触发时间到达 THEN the System SHALL 调用 FutureMessageWorkflow 生成主动消息
3. WHEN 主动消息生成成功 THEN the System SHALL 将消息写入 outputmessages 队列
4. WHEN 主动消息发送后 THEN the System SHALL 更新会话的 future 状态

### Requirement 7: Prompt 模板支持

**User Story:** As a 开发者, I want to 复用现有 Prompt 模板, so that 主动消息生成质量与普通对话一致。

#### Acceptance Criteria

1. WHEN 渲染问题重写 Prompt THEN the System SHALL 使用 TASKPROMPT_未来_语义理解 模板
2. WHEN 渲染消息生成 Prompt THEN the System SHALL 使用 TASKPROMPT_未来_微信对话 模板
3. WHEN 渲染 Prompt 模板 THEN the System SHALL 包含 CONTEXTPROMPT_规划行动 上下文
4. WHEN Prompt 模板渲染缺少字段 THEN the System SHALL 记录警告日志并使用默认值

### Requirement 8: 集成测试验证

**User Story:** As a 开发者, I want to 验证主动消息功能正确, so that 确保功能质量。

#### Acceptance Criteria

1. WHEN 执行主动消息生成流程 THEN the System SHALL 正确完成 QueryRewrite→ContextRetrieve→ChatResponse 全流程
2. WHEN 主动消息生成成功 THEN the System SHALL 返回有效的 MultiModalResponses 列表
3. WHEN 频率控制生效 THEN the System SHALL 在连续主动消息后降低下一次主动消息的概率
4. WHEN 主动消息触发服务运行 THEN the System SHALL 正确识别并处理到期的主动消息

