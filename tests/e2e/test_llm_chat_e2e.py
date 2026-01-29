# -*- coding: utf-8 -*-
"""
真实 LLM 聊天 E2E 测试

测试完整的消息处理链路，包括真实 LLM 调用。
测试用例从 llm_chat_cases.json 读取。

前置条件：
- agent_start.sh 已在后台运行
- MongoDB 可用
- LLM API 可用

运行方式：
    pytest tests/e2e/test_llm_chat_e2e.py -v -m llm

运行特定分类：
    pytest tests/e2e/test_llm_chat_e2e.py -v -k "basic"
    pytest tests/e2e/test_llm_chat_e2e.py -v -k "multi_turn"
"""
import json
import time
from pathlib import Path

import pytest

# 加载测试用例
CASES_FILE = Path(__file__).parent / "llm_chat_cases.json"
with open(CASES_FILE, "r", encoding="utf-8") as f:
    CASES_DATA = json.load(f)

TEST_CASES = CASES_DATA["test_cases"]
CONFIG = CASES_DATA["config"]


def get_cases_by_category(category: str) -> list:
    """按分类获取测试用例"""
    return [c for c in TEST_CASES if c.get("category") == category]


def get_cases_by_tag(tag: str) -> list:
    """按标签获取测试用例"""
    return [c for c in TEST_CASES if tag in c.get("tags", [])]


def verify_response(responses: list, expect: dict) -> tuple[bool, str]:
    """
    验证响应是否符合预期

    Args:
        responses: 响应消息列表
        expect: 预期配置

    Returns:
        (是否通过, 错误信息)
    """
    if not responses:
        return False, "未收到响应"

    total_content = "".join(r.get("message", "") for r in responses)

    # 检查非空
    if expect.get("not_empty") and not total_content.strip():
        return False, "响应内容为空"

    # 检查包含任一关键词
    if "contains_any" in expect:
        keywords = expect["contains_any"]
        if not any(kw in total_content for kw in keywords):
            return False, f"响应未包含任一关键词: {keywords}"

    # 检查包含所有关键词
    if "contains_all" in expect:
        keywords = expect["contains_all"]
        missing = [kw for kw in keywords if kw not in total_content]
        if missing:
            return False, f"响应缺少关键词: {missing}"

    # 检查不包含
    if "not_contains" in expect:
        keywords = expect["not_contains"]
        found = [kw for kw in keywords if kw in total_content]
        if found:
            return False, f"响应不应包含: {found}"

    return True, ""


def run_conversation(
    client, conversation: list, timeout: int
) -> tuple[bool, str, list]:
    """
    执行对话流程

    Args:
        client: TerminalTestClient
        conversation: 对话列表
        timeout: 超时时间

    Returns:
        (是否通过, 错误信息, 所有响应)
    """
    all_responses = []

    for i, turn in enumerate(conversation):
        role = turn["role"]

        if role == "user":
            content = turn["content"]
            client.send(content)

            # 如果下一轮是 assistant，等待响应
            if i + 1 < len(conversation) and conversation[i + 1]["role"] == "assistant":
                responses = client.wait_response(timeout=timeout)
                all_responses.extend(responses)

                # 验证响应
                expect = conversation[i + 1].get("expect", {})
                passed, error = verify_response(responses, expect)
                if not passed:
                    return False, f"第 {i+1} 轮验证失败: {error}", all_responses

                # 多轮对话间隔
                time.sleep(2)

    return True, "", all_responses


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.slow
class TestLLMChatFromJSON:
    """从 JSON 加载的 LLM 聊天测试"""

    @pytest.mark.parametrize(
        "case", get_cases_by_category("basic_chat"), ids=lambda c: c["id"]
    )
    def test_basic_chat(self, clean_terminal_client, case):
        """基本聊天测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"

    @pytest.mark.parametrize(
        "case", get_cases_by_category("question"), ids=lambda c: c["id"]
    )
    def test_question(self, clean_terminal_client, case):
        """问题回答测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"

    @pytest.mark.parametrize(
        "case", get_cases_by_category("multi_turn"), ids=lambda c: c["id"]
    )
    def test_multi_turn(self, clean_terminal_client, case):
        """多轮对话测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"

    @pytest.mark.parametrize(
        "case", get_cases_by_category("edge_case"), ids=lambda c: c["id"]
    )
    def test_edge_case(self, clean_terminal_client, case):
        """边缘情况测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"

    @pytest.mark.parametrize(
        "case", get_cases_by_category("emotion"), ids=lambda c: c["id"]
    )
    def test_emotion(self, clean_terminal_client, case):
        """情感表达测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"

    @pytest.mark.parametrize(
        "case", get_cases_by_category("daily"), ids=lambda c: c["id"]
    )
    def test_daily(self, clean_terminal_client, case):
        """日常对话测试"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.slow
class TestLLMChatAll:
    """运行所有聊天测试用例"""

    @pytest.mark.parametrize("case", TEST_CASES, ids=lambda c: c["id"])
    def test_all_cases(self, clean_terminal_client, case):
        """运行所有测试用例"""
        timeout = CONFIG["response_timeout_seconds"]
        passed, error, responses = run_conversation(
            clean_terminal_client, case["conversation"], timeout
        )
        assert passed, f"[{case['name']}] {error}"
