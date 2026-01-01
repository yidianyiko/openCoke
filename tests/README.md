# 测试文档

## 测试结构

```
tests/
├── fixtures/           # 测试数据和 Mock
│   ├── mock_responses.py
│   ├── sample_messages.py
│   └── sample_contexts.py
├── unit/              # 单元测试
│   ├── test_util_*.py
│   ├── test_dao_*.py
│   ├── test_entity_*.py
│   └── test_connector_*.py
├── integration/       # 集成测试
│   ├── test_mongodb_full.py
│   └── test_workflow_integration.py
├── pbt/              # 属性测试
│   ├── test_time_parsing_pbt.py
│   ├── test_vector_pbt.py
│   └── test_str_util_pbt.py
└── e2e/              # 端到端测试
    ├── conftest.py           # E2E fixtures (terminal_client)
    ├── test_chat_flow_e2e.py
    ├── test_reminder_flow_e2e.py
    ├── test_llm_chat_e2e.py      # 真实 LLM 聊天测试
    └── test_llm_reminder_e2e.py  # 真实 LLM 提醒测试
```

## 运行测试

### 运行所有测试
```bash
pytest
```

### 只运行单元测试
```bash
pytest -m unit
```

### 运行除集成测试外的所有测试
```bash
pytest -m "not integration"
```

### 运行覆盖率报告
```bash
pytest --cov --cov-report=html
```

### 并行运行测试
```bash
pytest -n auto
```

### 运行特定测试文件
```bash
pytest tests/unit/test_util_str.py
```

### 运行特定测试类
```bash
pytest tests/unit/test_util_str.py::TestRemoveChinese
```

### 运行特定测试方法
```bash
pytest tests/unit/test_util_str.py::TestRemoveChinese::test_pure_chinese
```

## 测试标记

- `@pytest.mark.unit` - 纯单元测试，无外部依赖
- `@pytest.mark.integration` - 需要外部服务（MongoDB等）
- `@pytest.mark.slow` - 耗时较长的测试
- `@pytest.mark.pbt` - 属性测试（Property-Based Testing）
- `@pytest.mark.e2e` - 端到端测试
- `@pytest.mark.llm` - 需要真实 LLM 调用的测试（需要 agent_start.sh 运行中）

## 测试覆盖率目标

- 整体覆盖率：70%+
- util 模块：80%+
- dao 模块：70%+
- entity 模块：80%+

## 编写测试指南

### 单元测试
- 使用 Mock 隔离外部依赖
- 测试边界情况和异常处理
- 保持测试独立性

### 集成测试
- 使用 `@pytest.mark.integration` 标记
- 在 `conftest.py` 中检查外部服务可用性
- 测试后清理数据

### 属性测试
- 使用 Hypothesis 库
- 测试函数的不变量和属性
- 使用 `@pytest.mark.pbt` 标记

### E2E 测试
- 使用 `@pytest.mark.e2e` 和 `@pytest.mark.slow` 标记
- 测试完整的用户流程
- 可能需要配置 API keys

## Fixtures

### MongoDB Fixtures
- `mongodb_available` - 检查 MongoDB 是否可用
- `mongo_client` - MongoDB 客户端
- `test_collection` - 临时测试集合

### Context Fixtures
- `sample_context` - 标准测试 context
- `sample_full_context` - 完整测试 context
- `sample_minimal_context` - 最小化测试 context

### Message Fixtures
- `sample_text_message` - 文本消息
- `sample_voice_message` - 语音消息

### Mock Fixtures
- `mock_mongodb` - Mock MongoDB 客户端
- `mock_llm_client` - Mock LLM API 客户端
- `mock_embedding_client` - Mock Embedding API 客户端

## CI/CD 集成

测试可以集成到 CI/CD 流程中：

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest -m "not integration" --cov --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```
