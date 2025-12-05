# Implementation Plan

## Proactive Message Feature

- [x] 1. Schema 定义和验证
  - [x] 1.1 完善 FutureMessageResponse Schema
    - 确保 FutureMessageResponse 包含所有必需字段
    - 添加字段验证和默认值
    - _Requirements: 1.1, 1.2_
  - [x] 1.2 编写 Schema 属性测试
    - **Property 1: Schema 结构完整性**
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 2. Agent 实现
  - [x] 2.1 完善 FutureMessageQueryRewriteAgent
    - 实现动态 instructions 函数
    - 配置 output_schema 为 QueryRewriteResponse
    - _Requirements: 2.1, 2.4_
  - [x] 2.2 完善 FutureMessageContextRetrieveAgent
    - 配置 context_retrieve_tool
    - 实现检索消息构建逻辑
    - _Requirements: 2.2_
  - [x] 2.3 完善 FutureMessageChatAgent
    - 实现动态 instructions 函数
    - 配置 output_schema 为 FutureMessageResponse
    - _Requirements: 2.3, 2.4_
  - [x] 2.4 编写 Agent 单元测试
    - 测试 Agent 输出格式
    - 测试动态 instructions 渲染
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Workflow 实现
  - [x] 3.1 完善 FutureMessageWorkflow.run() 方法
    - 实现 QueryRewrite → ContextRetrieve → ChatResponse 流程
    - 确保 session_state 正确传递
    - _Requirements: 3.1, 3.3_
  - [x] 3.2 实现 _build_retrieve_message() 方法
    - 构建上下文检索的消息
    - 包含规划行动和查询词
    - _Requirements: 3.1_
  - [x] 3.3 实现 _handle_relation_change() 方法
    - 解析 RelationChange
    - 更新 closeness 和 trustness
    - 确保值在 0-100 范围内
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 3.4 编写关系变化属性测试
    - **Property 4: 关系值边界约束**
    - **Validates: Requirements 4.1, 4.2, 4.3**
  - [x] 3.5 实现 _handle_future_response() 方法
    - 增加 proactive_times 计数
    - 实现概率衰减机制 (0.15^(n+1))
    - 设置或清除 future.timestamp 和 future.action
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 3.6 编写概率控制属性测试
    - **Property 5: 主动消息计数递增**
    - **Property 6: 概率命中时的状态设置**
    - **Property 7: 概率未命中时的状态清除**
    - **Validates: Requirements 5.1, 5.3, 5.4, 5.5**
  - [x] 3.7 编写 Workflow 属性测试
    - **Property 2: Workflow 执行顺序**
    - **Property 3: Workflow 返回结构**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 4. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Prompt 模板集成
  - [x] 5.1 配置问题重写 Prompt 模板
    - 使用 TASKPROMPT_未来_语义理解
    - 包含 CONTEXTPROMPT_规划行动
    - _Requirements: 7.1, 7.3_
  - [x] 5.2 配置消息生成 Prompt 模板
    - 使用 TASKPROMPT_未来_微信对话
    - 包含完整上下文 Prompt
    - _Requirements: 7.2, 7.3_
  - [x] 5.3 实现 Prompt 渲染错误处理
    - 捕获 KeyError 异常
    - 记录警告日志
    - 使用默认值降级
    - _Requirements: 7.4_
  - [x] 5.4 编写 Prompt 渲染属性测试
    - **Property 8: Prompt 模板渲染**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [x] 6. 触发服务实现
  - [x] 6.1 实现 ProactiveMessageTriggerService 类
    - 实现 check_and_trigger() 方法
    - 实现 _get_due_conversations() 方法
    - 实现 _trigger_proactive_message() 方法
    - _Requirements: 6.1, 6.2_
  - [x] 6.2 实现消息写入逻辑
    - 将 MultiModalResponses 写入 outputmessages 队列
    - 更新会话的 future 状态
    - _Requirements: 6.3, 6.4_
  - [x] 6.3 编写触发服务单元测试
    - Mock DAO 层测试查询逻辑
    - Mock Workflow 测试触发逻辑
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 7. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 集成测试
  - [ ] 8.1 编写 Workflow 端到端测试
    - 构造完整 session_state
    - 执行 FutureMessageWorkflow
    - 验证返回结构和状态更新
    - _Requirements: 8.1_
  - [ ] 8.2 编写输出有效性属性测试
    - **Property 9: 主动消息输出有效性**
    - **Validates: Requirements 8.2**
  - [ ] 8.3 编写频率控制集成测试
    - 测试连续主动消息的概率衰减
    - _Requirements: 8.3_
  - [ ] 8.4 编写触发服务集成测试
    - 测试完整的触发流程
    - _Requirements: 8.4_

- [ ] 9. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

