# Web Search Tool (博查 Search API) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add web search capability to the agent system using Bocha Search API, allowing the agent to search real-time information from the internet.

**Architecture:** Create a new `web_search_tool.py` that wraps Bocha Search API, then integrate it into the existing three-phase workflow by extending OrchestratorAgent's decision logic and adding a search step in PrepareWorkflow.

**Tech Stack:** Python 3.12+, httpx (async HTTP client), Bocha Search API, Agno framework

---

## Task 1: Add Bocha API Configuration

**Files:**
- Modify: `conf/config.json`
- Modify: `.env` (add API key)

**Step 1: Add bocha config section to config.json**

```json
{
    "bocha": {
        "base_url": "https://api.bochaai.com/v1/web-search",
        "default_count": 5,
        "timeout": 10
    }
}
```

Add this after the `aliyun_asr` section in `conf/config.json`.

**Step 2: Add API key to .env**

```bash
echo "BOCHA_API_KEY=your_api_key_here" >> .env
```

**Step 3: Commit**

```bash
git add conf/config.json
git commit -m "feat(config): add bocha search API configuration"
```

---

## Task 2: Create Web Search Tool - Test First

**Files:**
- Create: `tests/unit/test_web_search_tool.py`

**Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""
Web Search Tool Unit Tests
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestWebSearchTool:
    """web_search_tool 单元测试"""

    def test_import_web_search_tool(self):
        """测试工具可以正确导入"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool
        assert web_search_tool is not None

    def test_web_search_tool_has_tool_decorator(self):
        """测试工具有 @tool 装饰器"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool
        # Agno tool decorator adds __tool__ attribute
        assert hasattr(web_search_tool, '__wrapped__') or callable(web_search_tool)

    def test_web_search_tool_returns_dict(self):
        """测试工具返回字典格式"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "Test Result",
                            "url": "https://example.com",
                            "snippet": "Test snippet"
                        }
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = web_search_tool(query="测试搜索")

            assert isinstance(result, dict)
            assert "ok" in result

    def test_web_search_tool_empty_query_returns_error(self):
        """测试空查询返回错误"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        result = web_search_tool(query="")

        assert result["ok"] is False
        assert "error" in result

    def test_web_search_tool_api_error_handling(self):
        """测试 API 错误处理"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = Exception("API Error")

            result = web_search_tool(query="测试搜索")

            assert result["ok"] is False
            assert "error" in result

    def test_web_search_tool_formats_results(self):
        """测试搜索结果格式化"""
        from agent.agno_agent.tools.web_search_tool import web_search_tool

        with patch('agent.agno_agent.tools.web_search_tool.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "webPages": {
                    "value": [
                        {
                            "name": "标题1",
                            "url": "https://example1.com",
                            "snippet": "摘要1",
                            "siteName": "网站1"
                        },
                        {
                            "name": "标题2",
                            "url": "https://example2.com",
                            "snippet": "摘要2",
                            "siteName": "网站2"
                        }
                    ]
                }
            }
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = web_search_tool(query="测试", count=2)

            assert result["ok"] is True
            assert "results" in result
            assert len(result["results"]) == 2
            assert result["results"][0]["title"] == "标题1"
            assert result["results"][0]["url"] == "https://example1.com"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agent.agno_agent.tools.web_search_tool'"

**Step 3: Commit failing test**

```bash
git add tests/unit/test_web_search_tool.py
git commit -m "test(web-search): add failing tests for web_search_tool"
```

---

## Task 3: Implement Web Search Tool

**Files:**
- Create: `agent/agno_agent/tools/web_search_tool.py`

**Step 1: Create the implementation**

```python
# -*- coding: utf-8 -*-
"""
Web Search Tool - 博查搜索工具

使用博查 Search API 实现联网搜索功能，让 Agent 能够获取实时互联网信息。

API 文档: https://open.bochaai.com/
"""

import os
from typing import Optional

import httpx
from agno.tools import tool

from util.log_util import get_logger

logger = get_logger(__name__)

# 配置
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
BOCHA_BASE_URL = "https://api.bochaai.com/v1/web-search"
DEFAULT_TIMEOUT = 10
DEFAULT_COUNT = 5


@tool(
    description="联网搜索工具，用于搜索互联网上的实时信息。适用于查询新闻、天气、事件、人物等需要最新数据的场景。",
)
def web_search_tool(
    query: str,
    count: int = DEFAULT_COUNT,
    freshness: str = "noLimit",
    session_state: Optional[dict] = None,
) -> dict:
    """
    使用博查 Search API 搜索互联网信息

    Args:
        query: 搜索关键词，支持自然语言
        count: 返回结果数量，1-10，默认5
        freshness: 时间范围过滤
            - "noLimit": 不限时间（默认）
            - "oneDay": 最近一天
            - "oneWeek": 最近一周
            - "oneMonth": 最近一个月
            - "oneYear": 最近一年
        session_state: Agno 框架自动注入的会话状态

    Returns:
        dict: 搜索结果
            - ok: bool, 是否成功
            - results: list, 搜索结果列表（成功时）
                - title: 标题
                - url: 链接
                - snippet: 摘要
                - site_name: 来源网站
            - formatted: str, 格式化的搜索结果文本（成功时）
            - error: str, 错误信息（失败时）
    """
    # 参数校验
    if not query or not query.strip():
        return {"ok": False, "error": "搜索关键词不能为空"}

    if not BOCHA_API_KEY:
        logger.error("BOCHA_API_KEY 未配置")
        return {"ok": False, "error": "搜索服务未配置"}

    # 限制 count 范围
    count = max(1, min(10, count))

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.post(
                BOCHA_BASE_URL,
                headers={
                    "Authorization": f"Bearer {BOCHA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": query.strip(),
                    "count": count,
                    "freshness": freshness,
                    "summary": True,
                },
            )

            if response.status_code != 200:
                logger.error(f"博查 API 返回错误: {response.status_code} - {response.text}")
                return {"ok": False, "error": f"搜索服务返回错误: {response.status_code}"}

            data = response.json()

            # 解析搜索结果
            web_pages = data.get("webPages", {}).get("value", [])
            if not web_pages:
                return {
                    "ok": True,
                    "results": [],
                    "formatted": "未找到相关搜索结果。",
                }

            # 格式化结果
            results = []
            formatted_lines = ["【联网搜索结果】"]

            for i, page in enumerate(web_pages, 1):
                result = {
                    "title": page.get("name", ""),
                    "url": page.get("url", ""),
                    "snippet": page.get("snippet", "") or page.get("summary", ""),
                    "site_name": page.get("siteName", ""),
                }
                results.append(result)

                # 格式化为可读文本
                formatted_lines.append(
                    f"{i}. [{result['title']}] - {result['site_name'] or '未知来源'}"
                )
                if result["snippet"]:
                    formatted_lines.append(f"   {result['snippet'][:200]}")
                formatted_lines.append(f"   链接: {result['url']}")
                formatted_lines.append("")

            logger.info(f"博查搜索完成: query='{query}', 结果数={len(results)}")

            return {
                "ok": True,
                "results": results,
                "formatted": "\n".join(formatted_lines),
            }

    except httpx.TimeoutException:
        logger.error(f"博查 API 超时: query='{query}'")
        return {"ok": False, "error": "搜索服务超时，请稍后重试"}
    except Exception as e:
        logger.error(f"博查搜索失败: {e}")
        return {"ok": False, "error": f"搜索失败: {str(e)}"}
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add agent/agno_agent/tools/web_search_tool.py
git commit -m "feat(web-search): implement web_search_tool with Bocha API"
```

---

## Task 4: Export Web Search Tool

**Files:**
- Modify: `agent/agno_agent/tools/__init__.py`

**Step 1: Write failing test for export**

Add to `tests/unit/test_web_search_tool.py`:

```python
def test_web_search_tool_exported_from_tools_module(self):
    """测试工具从 tools 模块正确导出"""
    from agent.agno_agent.tools import web_search_tool
    assert web_search_tool is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_web_search_tool.py::TestWebSearchTool::test_web_search_tool_exported_from_tools_module -v`
Expected: FAIL with "ImportError: cannot import name 'web_search_tool'"

**Step 3: Update __init__.py**

In `agent/agno_agent/tools/__init__.py`, add import and export:

```python
# 在文件开头的 imports 部分添加
from agent.agno_agent.tools.web_search_tool import web_search_tool

# 在 __all__ 列表中添加
__all__ = [
    # 核心 Tool
    "context_retrieve_tool",
    "reminder_tool",
    "web_search_tool",  # 新增
    # 语音 Tool
    "voice2text_tool",
    "text2voice_tool",
    # 图片 Tool
    "image2text_tool",
    "image_send_tool",
    "image_generate_tool",
    # 相册 Tool
    "moments_tool",
    "photo_delete_tool",
]
```

Also update the docstring to include web_search_tool.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/tools/__init__.py
git commit -m "feat(web-search): export web_search_tool from tools module"
```

---

## Task 5: Extend OrchestratorSchema for Web Search

**Files:**
- Modify: `agent/agno_agent/schemas/orchestrator_schema.py`
- Create: `tests/unit/test_orchestrator_schema_web_search.py`

**Step 1: Write failing test**

```python
# -*- coding: utf-8 -*-
"""
OrchestratorSchema Web Search Extension Tests
"""

import pytest


class TestOrchestratorSchemaWebSearch:
    """OrchestratorSchema 联网搜索扩展测试"""

    def test_orchestrator_response_has_web_search_fields(self):
        """测试 OrchestratorResponse 包含联网搜索字段"""
        from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse

        # 创建实例测试默认值
        response = OrchestratorResponse()

        assert hasattr(response, "need_web_search")
        assert hasattr(response, "web_search_query")
        assert response.need_web_search is False
        assert response.web_search_query == ""

    def test_orchestrator_response_web_search_serialization(self):
        """测试联网搜索字段序列化"""
        from agent.agno_agent.schemas.orchestrator_schema import OrchestratorResponse

        response = OrchestratorResponse(
            need_web_search=True,
            web_search_query="杭州今天天气"
        )

        data = response.model_dump()

        assert data["need_web_search"] is True
        assert data["web_search_query"] == "杭州今天天气"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_orchestrator_schema_web_search.py -v`
Expected: FAIL with "AttributeError: 'OrchestratorResponse' object has no attribute 'need_web_search'"

**Step 3: Add web search fields to OrchestratorResponse**

In `agent/agno_agent/schemas/orchestrator_schema.py`, add after `need_reminder_detect` field:

```python
    need_web_search: bool = Field(
        default=False,
        description=(
            "是否需要联网搜索。"
            "默认：false。"
            "何时设为 true：用户询问实时信息（天气、新闻、股价）或外部世界的事实"
        ),
    )

    web_search_query: str = Field(
        default="",
        description=(
            "联网搜索的关键词。"
            "格式：简洁的搜索词，中英文皆可。"
            "示例：'杭州今天天气'、'特斯拉最新股价'、'2024世界杯'"
        ),
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_orchestrator_schema_web_search.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add agent/agno_agent/schemas/orchestrator_schema.py tests/unit/test_orchestrator_schema_web_search.py
git commit -m "feat(schema): add web search fields to OrchestratorResponse"
```

---

## Task 6: Update OrchestratorAgent Instructions

**Files:**
- Modify: `agent/prompt/agent_instructions_prompt.py`

**Step 1: Update INSTRUCTIONS_ORCHESTRATOR**

Replace the existing `INSTRUCTIONS_ORCHESTRATOR` with:

```python
INSTRUCTIONS_ORCHESTRATOR = """理解用户消息意图，做出调度决策。

## 决策规则

### need_context_retrieve
- 默认 true
- 设为 false：纯提醒操作（取消/查看/删除提醒）

### need_reminder_detect
设为 true（满足任一）：
1. 包含任何相关关键词：提醒、任务、待办、计划、日程、闹钟、定时、倒计时、番茄钟、打卡、督促、催、别忘了、通知、叫、喊等。
2. 消息中出现时间信息
3. 上下文延续：正在补充提醒相关信息
4. 用户质疑/询问某"提醒"状态
5. 不确定时，倾向于设为 true

设为 false：
1. 明确的纯闲聊，完全不涉及时间或事项管理
2. 叙述过去的事实（不是请求）

### need_web_search（联网搜索）
设为 true（满足任一）：
1. 用户询问实时信息：天气、新闻、股价、汇率、赛事比分等
2. 用户询问外部世界的具体事实：某人、某事件、某地点、某产品等
3. 用户明确要求搜索：「搜一下」「查一下」+ 外部信息
4. 用户问题涉及知识库可能没有的最新信息

设为 false：
1. 涉及「我的」「我设的」「待办」「提醒」「闹钟」等用户个人数据 → 这是提醒操作，不是搜索
2. 纯闲聊、情感交流、角色扮演
3. 用户询问角色本身的设定或能力
4. 历史对话相关的问题

**区分关键**：判断意图主体是「用户个人数据」还是「外部世界信息」
- 「查一下我的提醒」→ 提醒操作（need_reminder_detect=true）
- 「查一下杭州天气」→ 联网搜索（need_web_search=true）

### web_search_query
当 need_web_search=true 时填写，生成简洁有效的搜索词：
- 提取核心关键词，去除口语化表达
- 「帮我搜一下杭州明天会不会下雨」→「杭州明天天气」
- 「马斯克最近在干什么」→「马斯克 最新动态」

### context_retrieve_params
根据用户消息内容生成检索参数，参考 Schema 中的格式说明。

### inner_monologue
推测用户意图，简述调度决策理由。"""
```

**Step 2: Verify syntax**

Run: `python -c "from agent.prompt.agent_instructions_prompt import INSTRUCTIONS_ORCHESTRATOR; print('OK')"`
Expected: Output "OK"

**Step 3: Commit**

```bash
git add agent/prompt/agent_instructions_prompt.py
git commit -m "feat(prompt): update OrchestratorAgent instructions for web search"
```

---

## Task 7: Add Web Search Context Prompt

**Files:**
- Modify: `agent/prompt/chat_contextprompt.py`

**Step 1: Add web search context template**

Add at the end of `chat_contextprompt.py`:

```python
# ========== 联网搜索相关 ==========

CONTEXTPROMPT_联网搜索结果 = """### 联网搜索结果
{web_search_result}

【说明】以上是联网搜索获取的实时信息。请根据搜索结果回答用户问题：
- 引用信息时可以提及来源
- 如果搜索结果不足以回答问题，可以如实告知
- 结合角色人设自然地表达"""


def get_web_search_context(session_state: dict) -> str:
    """
    获取联网搜索结果上下文

    Args:
        session_state: 会话状态字典

    Returns:
        格式化的搜索结果上下文，如果没有结果则返回空字符串
    """
    web_search_result = session_state.get("web_search_result", {})

    if not web_search_result:
        return ""

    # 检查是否成功
    if not web_search_result.get("ok", False):
        error = web_search_result.get("error", "搜索失败")
        return f"""### 联网搜索提示
搜索未能成功：{error}
请根据已有知识回答用户问题，或告知用户搜索暂时不可用。"""

    # 获取格式化结果
    formatted = web_search_result.get("formatted", "")
    if not formatted:
        return ""

    return f"""### 联网搜索结果
{formatted}

【说明】以上是联网搜索获取的实时信息。请根据搜索结果回答用户问题：
- 引用信息时可以提及来源
- 如果搜索结果不足以回答问题，可以如实告知
- 结合角色人设自然地表达"""
```

**Step 2: Verify syntax**

Run: `python -c "from agent.prompt.chat_contextprompt import get_web_search_context; print('OK')"`
Expected: Output "OK"

**Step 3: Commit**

```bash
git add agent/prompt/chat_contextprompt.py
git commit -m "feat(prompt): add web search context template"
```

---

## Task 8: Integrate Web Search into PrepareWorkflow - Test First

**Files:**
- Create: `tests/unit/test_prepare_workflow_web_search.py`

**Step 1: Write failing test**

```python
# -*- coding: utf-8 -*-
"""
PrepareWorkflow Web Search Integration Tests
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestPrepareWorkflowWebSearch:
    """PrepareWorkflow 联网搜索集成测试"""

    @pytest.mark.asyncio
    async def test_web_search_executed_when_needed(self):
        """测试当 need_web_search=True 时执行搜索"""
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()

        # Mock orchestrator_agent 返回 need_web_search=True
        mock_orchestrator_response = MagicMock()
        mock_orchestrator_response.content = MagicMock()
        mock_orchestrator_response.content.model_dump.return_value = {
            "inner_monologue": "用户询问天气",
            "need_context_retrieve": True,
            "context_retrieve_params": {},
            "need_reminder_detect": False,
            "need_web_search": True,
            "web_search_query": "杭州今天天气",
        }

        with patch('agent.agno_agent.workflows.prepare_workflow.orchestrator_agent') as mock_orch, \
             patch('agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool') as mock_ctx, \
             patch('agent.agno_agent.workflows.prepare_workflow.web_search_tool') as mock_search:

            mock_orch.arun = AsyncMock(return_value=mock_orchestrator_response)
            mock_ctx.return_value = {"character_global": "", "user": ""}
            mock_search.return_value = {
                "ok": True,
                "results": [{"title": "天气", "snippet": "晴天"}],
                "formatted": "【联网搜索结果】\n1. 天气 - 晴天"
            }

            session_state = {
                "conversation": {"conversation_info": {"time_str": "2026年01月28日", "chat_history": []}},
                "character": {"_id": "char1"},
                "user": {"_id": "user1"},
            }

            result = await workflow.run("杭州今天天气怎么样", session_state)

            # 验证搜索被调用
            mock_search.assert_called_once_with(query="杭州今天天气")

            # 验证结果存入 session_state
            assert "web_search_result" in result["session_state"]
            assert result["session_state"]["web_search_result"]["ok"] is True

    @pytest.mark.asyncio
    async def test_web_search_skipped_when_not_needed(self):
        """测试当 need_web_search=False 时跳过搜索"""
        from agent.agno_agent.workflows.prepare_workflow import PrepareWorkflow

        workflow = PrepareWorkflow()

        mock_orchestrator_response = MagicMock()
        mock_orchestrator_response.content = MagicMock()
        mock_orchestrator_response.content.model_dump.return_value = {
            "inner_monologue": "普通闲聊",
            "need_context_retrieve": True,
            "context_retrieve_params": {},
            "need_reminder_detect": False,
            "need_web_search": False,
            "web_search_query": "",
        }

        with patch('agent.agno_agent.workflows.prepare_workflow.orchestrator_agent') as mock_orch, \
             patch('agent.agno_agent.workflows.prepare_workflow.context_retrieve_tool') as mock_ctx, \
             patch('agent.agno_agent.workflows.prepare_workflow.web_search_tool') as mock_search:

            mock_orch.arun = AsyncMock(return_value=mock_orchestrator_response)
            mock_ctx.return_value = {"character_global": "", "user": ""}

            session_state = {
                "conversation": {"conversation_info": {"time_str": "2026年01月28日", "chat_history": []}},
                "character": {"_id": "char1"},
                "user": {"_id": "user1"},
            }

            result = await workflow.run("你好呀", session_state)

            # 验证搜索未被调用
            mock_search.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_prepare_workflow_web_search.py -v`
Expected: FAIL (web_search_tool not imported or called in workflow)

**Step 3: Commit failing test**

```bash
git add tests/unit/test_prepare_workflow_web_search.py
git commit -m "test(workflow): add failing tests for web search integration"
```

---

## Task 9: Implement Web Search in PrepareWorkflow

**Files:**
- Modify: `agent/agno_agent/workflows/prepare_workflow.py`

**Step 1: Add import**

At the top of the file, add:

```python
from agent.agno_agent.tools.web_search_tool import web_search_tool
```

**Step 2: Add web search step in run() method**

In the `run()` method, after Step 2 (context retrieve) and before Step 3 (reminder detect), add:

```python
        # Step 2.5: 联网搜索 (按需调用，0次 LLM)
        need_web_search = orchestrator.get("need_web_search", False)
        if need_web_search:
            self._run_web_search(session_state, orchestrator)
        else:
            logger.info("跳过联网搜索 (need_web_search=False)")
```

**Step 3: Add _run_web_search method**

Add this method to the PrepareWorkflow class:

```python
    def _run_web_search(
        self, session_state: dict, orchestrator: dict
    ) -> None:
        """执行联网搜索"""
        try:
            query = orchestrator.get("web_search_query", "")
            if not query:
                logger.warning("联网搜索被请求但未提供搜索词")
                return

            logger.info(f"执行联网搜索: query='{query}'")

            search_result = web_search_tool(query=query)
            session_state["web_search_result"] = search_result

            if search_result.get("ok"):
                result_count = len(search_result.get("results", []))
                logger.info(f"联网搜索完成: 获取 {result_count} 条结果")
            else:
                logger.warning(f"联网搜索失败: {search_result.get('error', 'unknown')}")

        except Exception as e:
            logger.error(f"联网搜索执行异常: {e}")
            session_state["web_search_result"] = {"ok": False, "error": str(e)}
```

**Step 4: Update docstring**

Update the class docstring to mention web search:

```python
    """
    准备阶段 Workflow (V2 架构)

    注意：这是自定义 Workflow 类，不继承 Agno Workflow，
    因为需要 Runner 层控制分段执行和打断检测.

    执行流程：
    1. OrchestratorAgent-语义理解 + 调度决策 (1次 LLM)
    2. context_retrieve_tool-直接函数调用 (0次 LLM)
    2.5. web_search_tool-联网搜索 (0次 LLM, 按需)
    3. ReminderDetectAgent-按需调用 (0-1次 LLM)

    输出：
   -session_state["orchestrator"]-OrchestratorAgent 的输出
   -session_state["context_retrieve"]-context_retrieve_tool 的输出
   -session_state["web_search_result"]-联网搜索结果 (按需)

    兼容性：
   -session_state["query_rewrite"]-保留旧字段，从 orchestrator 映射
    """
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_prepare_workflow_web_search.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add agent/agno_agent/workflows/prepare_workflow.py
git commit -m "feat(workflow): integrate web search into PrepareWorkflow"
```

---

## Task 10: Update ChatWorkflow to Include Search Results

**Files:**
- Modify: `agent/agno_agent/workflows/chat_workflow_streaming.py`

**Step 1: Read current implementation**

First, examine the current chat workflow to understand how context is assembled.

**Step 2: Add web search context**

In the context assembly section (where other contexts like reminder results are added), add:

```python
# 联网搜索结果上下文
from agent.prompt.chat_contextprompt import get_web_search_context

web_search_context = get_web_search_context(session_state)
if web_search_context:
    # 添加到 context 列表或模板中
    contexts.append(web_search_context)
```

The exact implementation depends on how the current workflow assembles context. Follow the existing pattern for `get_reminder_result_context`.

**Step 3: Verify manually**

Run a quick test to ensure the workflow doesn't crash:

```bash
python -c "from agent.agno_agent.workflows.chat_workflow_streaming import *; print('OK')"
```

**Step 4: Commit**

```bash
git add agent/agno_agent/workflows/chat_workflow_streaming.py
git commit -m "feat(workflow): pass web search results to ChatResponseAgent"
```

---

## Task 11: Run Full Test Suite

**Step 1: Run all unit tests**

Run: `pytest -m "not integration" -v`
Expected: All tests PASS

**Step 2: Run linting**

Run: `black . && isort .`
Fix any formatting issues.

**Step 3: Final commit**

```bash
git add -A
git commit -m "style: format code with black and isort"
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `doc/architecture/detailed_architecture_analysis.md` (if exists)
- Modify: `CLAUDE.md`

**Step 1: Update CLAUDE.md**

Add to the Tools section:

```markdown
- `web_search_tool`: 联网搜索（博查 Search API）
```

Add to the Three-Phase Workflow Design section:

```markdown
Phase 1: PrepareWorkflow (2-6s)
  ├─ OrchestratorAgent: semantic understanding + scheduling decisions
  ├─ context_retrieve_tool: direct function call for context retrieval
  ├─ web_search_tool: optional, when need_web_search=true  ← NEW
  └─ ReminderDetectAgent: optional, only when reminder intent detected
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with web search tool"
```

---

## Summary

This plan implements web search capability through:

1. **Tool Layer**: `web_search_tool.py` wrapping Bocha Search API
2. **Schema Layer**: Extended `OrchestratorResponse` with `need_web_search` and `web_search_query`
3. **Prompt Layer**: Updated OrchestratorAgent instructions and added web search context template
4. **Workflow Layer**: Integrated search step into PrepareWorkflow and passed results to ChatWorkflow

**Key Design Decisions:**
- Search is triggered by OrchestratorAgent, not a separate Agent (simpler, fewer LLM calls)
- Direct tool call (0 LLM), not agent-based (search query already generated by Orchestrator)
- Clear distinction between "personal data" (reminders) and "external info" (web search)
