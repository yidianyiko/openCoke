# Requirements Document

## Introduction

本需求文档描述将现有自研 Agent 框架迁移至 Agno 框架的功能需求。迁移范围包括 Framework 层替换、Agent 层重构、Runner 层适配，同时保留 Connector 层和 DAO 层不变。

迁移目标：
- 减少自研代码维护成本
- 提升系统稳定性
- 获得更灵活的模型切换能力
- 为未来扩展 Memory、Knowledge 等能力奠定基础

详细设计参见：[迁移计划文档](../../../doc/agno-demo/agno-migration-plan.md)

## Glossary

- **Agno**: 生产级 Agent 框架，提供 Agent、Team、Workflow、Tools 等能力
- **Agent**: 具有特定能力的 AI 代理，使用 LLM 执行任务
- **Tool**: Agent 可调用的工具函数，封装外部能力
- **Workflow**: 自定义流程编排，控制多个 Agent 的执行顺序
- **session_state**: Agno 中的状态传递机制，用于跨 Agent 传递数据
- **Runner 层**: 消息处理主循环，负责调度 Agent 和处理响应
- **context_prepare**: 构建 Agent 执行所需上下文的函数
- **消息打断**: 检测到新消息时中断当前处理，避免对话上下文割裂

## Requirements

### Requirement 1: 基础设施准备

**User Story:** As a 开发者, I want to 配置 Agno 框架依赖和环境, so that 后续开发工作可以顺利进行。

#### Acceptance Criteria

1. WHEN 开发者安装项目依赖 THEN the System SHALL 成功安装 agno>=2.0.0 和 pydantic>=2.0.0
2. WHEN 开发者配置环境变量 THEN the System SHALL 支持通过 DEEPSEEK_API_KEY 环境变量配置 DeepSeek API 密钥
3. WHEN 开发者创建目录结构 THEN the System SHALL 在 qiaoyun/agno_agent/ 下创建 agents/、tools/、schemas/、workflows/ 子目录

### Requirement 2: Pydantic Schema 定义

**User Story:** As a 开发者, I want to 定义 Agent 响应的 Pydantic Schema, so that Agent 输出格式规范且可验证。

#### Acceptance Criteria

1. WHEN QueryRewriteAgent 执行完成 THEN the System SHALL 返回符合 QueryRewriteResponse Schema 的结构化数据，包含 InnerMonologue、CharacterSettingQueryQuestion、UserProfileQueryQuestion、CharacterKnowledgeQueryQuestion 字段
2. WHEN ChatResponseAgent 执行完成 THEN the System SHALL 返回符合 ChatResponse Schema 的结构化数据，包含 InnerMonologue、MultiModalResponses、RelationChange、FutureResponse 字段
3. WHEN PostAnalyzeAgent 执行完成 THEN the System SHALL 返回符合 PostAnalyzeResponse Schema 的结构化数据，包含 CharacterPublicSettings、CharacterPrivateSettings、UserSettings、RelationDescription 字段

### Requirement 3: 核心 Tool 开发

**User Story:** As a 开发者, I want to 将现有功能封装为 Agno Tool, so that Agent 可以调用这些能力。

#### Acceptance Criteria

1. WHEN Agent 需要检索上下文 THEN the System SHALL 提供 context_retrieve_tool，支持检索角色全局设定、角色私有设定、用户资料、角色知识
2. WHEN Agent 需要管理提醒 THEN the System SHALL 提供 reminder_tool，通过 action 参数支持 create/update/delete/list 四种操作
3. WHEN reminder_tool 创建提醒 THEN the System SHALL 支持解析相对时间（如"30分钟后"、"明天"）和绝对时间
4. WHEN reminder_tool 创建周期提醒 THEN the System SHALL 支持 daily/weekly/monthly/yearly 周期类型

### Requirement 4: Agent 迁移

**User Story:** As a 开发者, I want to 将现有 Agent 迁移到 Agno 框架, so that 对话处理流程使用新框架执行。

#### Acceptance Criteria

1. WHEN 用户发送消息 THEN the QueryRewriteAgent SHALL 对用户输入进行语义理解并生成检索查询词
2. WHEN QueryRewriteAgent 执行完成 THEN the ChatResponseAgent SHALL 基于检索结果和角色人设生成多模态回复
3. WHEN ChatResponseAgent 生成回复后 THEN the PostAnalyzeAgent SHALL 总结对话并更新用户/角色记忆
4. WHEN 用户消息包含提醒意图 THEN the ReminderDetectAgent SHALL 识别提醒意图并调用 reminder_tool 创建提醒
5. WHEN Agent 使用动态 instructions THEN the System SHALL 通过函数方式渲染 Prompt 模板，注入 session_state 中的动态数据

### Requirement 5: Workflow 编排

**User Story:** As a 开发者, I want to 使用 Workflow 编排多个 Agent 的执行顺序, so that 对话处理流程清晰可控。

#### Acceptance Criteria

1. WHEN Runner 层调用 PrepareWorkflow THEN the System SHALL 顺序执行 QueryRewrite、ReminderDetect、ContextRetrieve 三个步骤
2. WHEN Runner 层调用 ChatWorkflow THEN the System SHALL 基于 PrepareWorkflow 的结果生成回复
3. WHEN Runner 层调用 PostAnalyzeWorkflow THEN the System SHALL 基于对话结果进行后处理分析
4. WHEN Workflow 执行过程中修改 session_state THEN the System SHALL 正确传递修改后的状态到后续步骤

### Requirement 6: Runner 层适配

**User Story:** As a 开发者, I want to 修改 Runner 层以调用 Agno Workflow, so that 消息处理流程使用新框架。

#### Acceptance Criteria

1. WHEN context_prepare 函数执行 THEN the System SHALL 将 MongoDB ObjectId 转换为字符串，确保 session_state 可 JSON 序列化
2. WHEN context_prepare 函数执行 THEN the System SHALL 为所有 Prompt 模板所需字段设置默认值
3. WHEN Runner 层执行 Phase 1 后 THEN the System SHALL 检测是否有新消息到达，如有则触发 rollback
4. WHEN Runner 层发送每条消息后 THEN the System SHALL 检测是否有新消息到达，如有则停止发送并跳过 PostAnalyze
5. WHEN Workflow 执行失败 THEN the System SHALL 捕获异常并记录错误日志

### Requirement 7: 消息打断机制

**User Story:** As a 用户, I want to 在发送多条消息时获得连贯的回复, so that 对话体验流畅自然。

#### Acceptance Criteria

1. WHEN 用户在系统处理消息期间发送新消息 THEN the System SHALL 在 Phase 1 完成后检测到新消息并放弃当前回复生成
2. WHEN 系统检测到新消息触发 rollback THEN the System SHALL 将所有待处理消息合并为一个上下文一起处理
3. WHEN 系统在发送消息过程中检测到新消息 THEN the System SHALL 停止发送剩余消息并跳过 PostAnalyze 步骤
4. WHEN rollback 发生 THEN the System SHALL 保留已发送的消息记录到对话历史

### Requirement 8: 集成测试验证

**User Story:** As a 开发者, I want to 验证迁移后的系统功能正确, so that 确保迁移质量。

#### Acceptance Criteria

1. WHEN 执行文本消息处理流程 THEN the System SHALL 正确完成 输入→处理→输出 全流程
2. WHEN 执行提醒创建流程 THEN the System SHALL 正确识别提醒意图并创建提醒记录
3. WHEN 系统响应用户消息 THEN the System SHALL 在 P99 延迟 20 秒内完成响应
4. WHEN 系统处理消息 THEN the System SHALL 保持错误率低于 1%
