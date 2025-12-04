# Implementation Plan

- [ ] 1. 基础设施准备
  - [ ] 1.1 更新 requirements.txt 添加 agno 和 pydantic 依赖
    - 添加 agno>=2.0.0 和 pydantic>=2.0.0
    - _Requirements: 1.1_
  - [ ] 1.2 创建目录结构
    - 创建 qiaoyun/agno_agent/agents/、tools/、schemas/、workflows/ 目录
    - 创建各目录的 __init__.py 文件
    - _Requirements: 1.3_

- [ ] 2. Pydantic Schema 定义
  - [ ] 2.1 实现 QueryRewriteResponse Schema
    - 创建 qiaoyun/agno_agent/schemas/query_rewrite_schema.py
    - 定义 InnerMonologue、CharacterSettingQueryQuestion 等字段
    - _Requirements: 2.1_
  - [ ]* 2.2 编写 QueryRewriteResponse Schema 属性测试
    - **Property 1: Agent 输出格式一致性**
    - **Validates: Requirements 2.1**
  - [ ] 2.3 实现 ChatResponse Schema
    - 创建 qiaoyun/agno_agent/schemas/chat_response_schema.py
    - 定义 MultiModalResponse、RelationChangeModel、FutureResponseModel 子模型
    - 定义 ChatResponse 主模型
    - _Requirements: 2.2_
  - [ ]* 2.4 编写 ChatResponse Schema 属性测试
    - **Property 1: Agent 输出格式一致性**
    - **Validates: Requirements 2.2**
  - [ ] 2.5 实现 PostAnalyzeResponse Schema
    - 创建 qiaoyun/agno_agent/schemas/post_analyze_schema.py
    - 定义 CharacterPublicSettings、UserSettings 等字段
    - _Requirements: 2.3_
  - [ ]* 2.6 编写 PostAnalyzeResponse Schema 属性测试
    - **Property 1: Agent 输出格式一致性**
    - **Validates: Requirements 2.3**

- [ ] 3. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 核心 Tool 开发
  - [ ] 4.1 实现 context_retrieve_tool
    - 创建 qiaoyun/agno_agent/tools/context_retrieve_tool.py
    - 复用现有 QiaoyunContextRetrieveAgent 的核心逻辑
    - 使用 @tool 装饰器封装
    - _Requirements: 3.1_
  - [ ]* 4.2 编写 context_retrieve_tool 属性测试
    - **Property 2: context_retrieve_tool 返回结构完整性**
    - **Validates: Requirements 3.1**
  - [ ] 4.3 实现 reminder_tool
    - 创建 qiaoyun/agno_agent/tools/reminder_tools.py
    - 实现 create/update/delete/list 四种操作
    - 复用 ReminderDAO 和时间解析工具
    - _Requirements: 3.2, 3.3, 3.4_
  - [ ]* 4.4 编写 reminder_tool CRUD 属性测试
    - **Property 3: reminder_tool CRUD 一致性**
    - **Validates: Requirements 3.2**
  - [ ]* 4.5 编写时间解析属性测试
    - **Property 4: 时间解析正确性**
    - **Validates: Requirements 3.3**

- [ ] 5. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Agent 迁移
  - [ ] 6.1 实现动态 instructions 函数
    - 创建 qiaoyun/agno_agent/agents.py
    - 实现 get_query_rewrite_instructions、get_chat_response_instructions、get_post_analyze_instructions
    - _Requirements: 4.5_
  - [ ]* 6.2 编写动态 instructions 属性测试
    - **Property 5: 动态 instructions 渲染完整性**
    - **Validates: Requirements 4.5**
  - [ ] 6.3 实现模块级预创建 Agent
    - 在 agents.py 中预创建 query_rewrite_agent、reminder_detect_agent、context_retrieve_agent、chat_response_agent、post_analyze_agent
    - 配置 model、instructions、response_model、tools
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 7. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Workflow 编排
  - [ ] 8.1 实现 PrepareWorkflow
    - 创建 qiaoyun/agno_agent/workflows/prepare_workflow.py
    - 顺序执行 QueryRewrite、ReminderDetect、ContextRetrieve
    - 更新 session_state 中的 query_rewrite 和 context_retrieve 字段
    - _Requirements: 5.1_
  - [ ]* 8.2 编写 PrepareWorkflow 属性测试
    - **Property 6: PrepareWorkflow 状态累积**
    - **Validates: Requirements 5.1**
  - [ ] 8.3 实现 ChatWorkflow
    - 创建 qiaoyun/agno_agent/workflows/chat_workflow.py
    - 渲染 user prompt 并调用 chat_response_agent
    - _Requirements: 5.2_
  - [ ] 8.4 实现 PostAnalyzeWorkflow
    - 创建 qiaoyun/agno_agent/workflows/post_analyze_workflow.py
    - 渲染 user prompt 并调用 post_analyze_agent
    - _Requirements: 5.3_
  - [ ]* 8.5 编写 Workflow 状态传递属性测试
    - **Property 7: Workflow 状态传递**
    - **Validates: Requirements 5.4**

- [ ] 9. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Runner 层适配
  - [ ] 10.1 实现 ObjectId 序列化函数
    - 在 qiaoyun/runner/context.py 中添加 _convert_objectid_to_str 函数
    - 递归转换 dict 中的 ObjectId 为字符串
    - _Requirements: 6.1_
  - [ ]* 10.2 编写 ObjectId 序列化属性测试
    - **Property 8: ObjectId 序列化**
    - **Validates: Requirements 6.1**
  - [ ] 10.3 更新 context_prepare 函数
    - 调用 _convert_objectid_to_str 进行 ObjectId 转换
    - 设置所有 Prompt 模板所需字段的默认值
    - _Requirements: 6.2_
  - [ ]* 10.4 编写默认值完整性属性测试
    - **Property 9: 默认值完整性**
    - **Validates: Requirements 6.2**
  - [ ] 10.5 更新 main_handler 函数
    - 导入并实例化三个 Workflow
    - 实现 Phase 1 → 检测 → Phase 2 → 发送 → Phase 3 的执行流程
    - 在 Phase 1 后和每条消息发送后检测新消息
    - 实现异常捕获和错误日志记录
    - _Requirements: 6.3, 6.4, 6.5_

- [ ] 11. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. 消息打断机制
  - [ ] 12.1 实现消息合并逻辑
    - 在 rollback 时将所有待处理消息合并为一个上下文
    - _Requirements: 7.2_
  - [ ]* 12.2 编写消息合并属性测试
    - **Property 10: 消息合并正确性**
    - **Validates: Requirements 7.2**
  - [ ] 12.3 实现已发送消息记录逻辑
    - 在 rollback 发生时保留已发送的消息到对话历史
    - _Requirements: 7.4_
  - [ ]* 12.4 编写已发送消息记录属性测试
    - **Property 11: 已发送消息记录**
    - **Validates: Requirements 7.4**

- [ ] 13. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. 集成测试
  - [ ]* 14.1 编写文本消息处理流程集成测试
    - 验证 输入→处理→输出 全流程
    - _Requirements: 8.1_
  - [ ]* 14.2 编写提醒创建流程集成测试
    - 验证提醒意图识别和创建
    - _Requirements: 8.2_
  - [ ]* 14.3 编写消息打断流程集成测试
    - 模拟新消息到达，验证 rollback 行为
    - _Requirements: 7.1, 7.3_

- [ ] 15. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.
