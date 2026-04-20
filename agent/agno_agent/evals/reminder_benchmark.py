from __future__ import annotations

import asyncio
import importlib
import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bson import ObjectId

from conf.config import CONF

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CASES_PATH = PROJECT_ROOT / "tests" / "evals" / "reminder_toolcall_benchmark_cases.json"
BASE_TIMESTAMP = 1762819200


def load_cases() -> dict[str, Any]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _quiet_noisy_loggers() -> None:
    for logger_name in (
        "hpack",
        "httpx",
        "httpcore",
        "openai",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def make_sample_context(message: str) -> dict[str, Any]:
    conversation_info = {
        "chat_history": [],
        "input_messages": [{"message": message, "input_timestamp": BASE_TIMESTAMP}],
        "input_messages_str": message,
        "chat_history_str": "",
        "time_str": "2026年04月21日 09时00分",
        "photo_history": [],
        "future": {"timestamp": None, "action": None},
        "turn_sent_contents": [],
    }
    return {
        "user": {
            "id": "benchmark_user_id",
            "_id": ObjectId(),
            "display_name": "Benchmark User",
            "nickname": "Benchmark User",
            "platforms": {"wechat": {"id": "wxid_benchmark_user", "nickname": "Benchmark User"}},
        },
        "character": {
            "_id": ObjectId(),
            "name": "测试角色",
            "nickname": "测试角色",
            "platforms": {"wechat": {"id": "wxid_test_char", "nickname": "测试角色"}},
            "user_info": {
                "description": "测试角色描述",
                "status": {"place": "家里", "action": "休息"},
            },
        },
        "conversation": {
            "_id": ObjectId(),
            "platform": "business",
            "conversation_info": conversation_info,
        },
        "relation": {
            "_id": ObjectId(),
            "uid": "benchmark_uid",
            "cid": "benchmark_cid",
            "relationship": {
                "description": "在聊天里认识的朋友",
                "closeness": 50,
                "trustness": 50,
                "dislike": 0,
                "status": "空闲",
            },
            "user_info": {"realname": "", "hobbyname": "", "description": ""},
            "character_info": {
                "status": "空闲",
                "longterm_purpose": "",
                "shortterm_purpose": "",
                "attitude": "",
            },
        },
        "platform": "business",
        "conversation_id": "benchmark_conversation_id",
        "news_str": "",
        "repeated_input_notice": "",
        "recent_chat_history": "（无历史消息）",
        "proactive_forbidden_messages": "",
        "proactive_times": 0,
        "system_message_metadata": {},
        "MultiModalResponses": [],
        "context_retrieve": {
            "character_global": "",
            "character_private": "",
            "user": "",
            "character_knowledge": "",
            "confirmed_reminders": "",
            "relevant_history": "",
        },
        "query_rewrite": {
            "InnerMonologue": "",
            "CharacterSettingQueryQuestion": "",
            "CharacterSettingQueryKeywords": "",
            "UserProfileQueryQuestion": "",
            "UserProfileQueryKeywords": "",
            "CharacterKnowledgeQueryQuestion": "",
            "CharacterKnowledgeQueryKeywords": "",
        },
        "message_source": "user",
        "input_timestamp": BASE_TIMESTAMP,
        "tool_results": [],
    }


class Recorder:
    def __init__(self) -> None:
        self.created_docs: list[dict[str, Any]] = []
        self.deleted_keywords: list[str] = []
        self.updated_payloads: list[dict[str, Any]] = []
        self.completed_keywords: list[str] = []
        self.filtered_queries: list[dict[str, Any]] = []


class FakeReminderDAO:
    recorder: Recorder | None = None

    def __init__(self, *args, **kwargs):
        self._recorder = self.__class__.recorder

    def create_reminder(self, reminder_data):
        assert self._recorder is not None
        self._recorder.created_docs.append(reminder_data)
        return f"fake_{len(self._recorder.created_docs)}"

    def find_similar_reminder(self, *args, **kwargs):
        return None

    def update_reminders_by_keyword(self, user_id, keyword, update_data):
        assert self._recorder is not None
        self._recorder.updated_payloads.append({"keyword": keyword, "update_data": update_data})
        return 1, []

    def delete_reminders_by_keyword(self, user_id, keyword):
        assert self._recorder is not None
        self._recorder.deleted_keywords.append(keyword)
        return 1

    def complete_reminders_by_keyword(self, user_id, keyword):
        assert self._recorder is not None
        self._recorder.completed_keywords.append(keyword)
        return 1

    def filter_reminders(self, user_id, status_list=None, **kwargs):
        assert self._recorder is not None
        self._recorder.filtered_queries.append({"status_list": status_list, **kwargs})
        return []

    def close(self):
        return None


@contextmanager
def patched_reminder_dao(recorder: Recorder):
    FakeReminderDAO.recorder = recorder
    with patch("dao.reminder_dao.ReminderDAO", FakeReminderDAO):
        yield


def _configure_model(model_id: str) -> None:
    _quiet_noisy_loggers()
    CONF.setdefault("llm", {})
    CONF["llm"].update(
        {
            "provider": "siliconflow",
            "model_id": model_id,
            "api_key": CONF["llm"].get("api_key"),
            "base_url": "https://api.siliconflow.cn/v1",
            "max_retries": 2,
            "roles": {
                "prepare": {
                    "provider": "siliconflow",
                    "model_id": model_id,
                    "api_key": CONF["llm"].get("api_key"),
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
                "post_analyze": {
                    "provider": "siliconflow",
                    "model_id": model_id,
                    "api_key": CONF["llm"].get("api_key"),
                    "base_url": "https://api.siliconflow.cn/v1",
                    "max_retries": 2,
                },
            },
        }
    )


def _reload_runtime():
    model_factory = importlib.import_module("agent.agno_agent.model_factory")
    agents = importlib.import_module("agent.agno_agent.agents")
    prepare_workflow = importlib.import_module("agent.agno_agent.workflows.prepare_workflow")
    reminder_tools = importlib.import_module("agent.agno_agent.tools.reminder_tools")

    model_factory = importlib.reload(model_factory)
    agents = importlib.reload(agents)
    prepare_workflow = importlib.reload(prepare_workflow)
    reminder_tools = importlib.reload(reminder_tools)
    return agents, prepare_workflow, reminder_tools


def _parse_orchestrator_content(content: Any) -> dict[str, Any]:
    if hasattr(content, "model_dump"):
        return content.model_dump()
    if isinstance(content, dict):
        return content
    return {}


async def _run_case(model_id: str, case: dict[str, Any]) -> dict[str, Any]:
    _configure_model(model_id)
    agents, prepare_module, reminder_tools = _reload_runtime()
    workflow = prepare_module.PrepareWorkflow()
    session_state = make_sample_context(case["message"])

    orchestrator_prompt = workflow._render_template(workflow.orchestrator_template, session_state)
    gate_started = time.perf_counter()
    orchestrator_response = await agents.orchestrator_agent.arun(
        input=orchestrator_prompt, session_state=session_state
    )
    gate_latency = time.perf_counter() - gate_started
    orchestrator_result = _parse_orchestrator_content(getattr(orchestrator_response, "content", None))
    actual_gate = bool(orchestrator_result.get("need_reminder_detect", False))

    recorder = Recorder()
    reminder_input = workflow._build_reminder_input(case["message"], session_state)
    reminder_tools.set_reminder_session_state(session_state)

    with patched_reminder_dao(recorder):
        tool_started = time.perf_counter()
        reminder_response = await agents.reminder_detect_agent.arun(
            input=reminder_input, session_state=session_state
        )
        tool_latency = time.perf_counter() - tool_started

    actual_tool_call = bool(getattr(reminder_response, "tools", None))
    actual_create = len(recorder.created_docs) > 0
    actual_has_time = recorder.created_docs[0].get("next_trigger_time") is not None if actual_create else None

    return {
        "case_id": case["id"],
        "message": case["message"],
        "category": case["category"],
        "model_id": model_id,
        "expect_gate": case["expect_gate"],
        "expect_tool_call": case["expect_tool_call"],
        "expect_create": case["expect_create"],
        "expect_has_time": case["expect_has_time"],
        "actual_gate": actual_gate,
        "actual_tool_call": actual_tool_call,
        "actual_create": actual_create,
        "actual_has_time": actual_has_time,
        "gate_latency_seconds": round(gate_latency, 3),
        "tool_latency_seconds": round(tool_latency, 3),
        "orchestrator_result": orchestrator_result,
        "tool_result_summaries": list(session_state.get("tool_results", [])),
        "created_docs": recorder.created_docs,
        "response_tools": getattr(reminder_response, "tools", None),
    }


async def benchmark_models(model_ids: list[str]) -> dict[str, Any]:
    data = load_cases()
    cases = data["cases"]
    results: list[dict[str, Any]] = []

    for model_id in model_ids:
        for case in cases:
            results.append(await _run_case(model_id, case))

    return {"results": results, "summary": summarize_results(results)}


def _safe_div(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def summarize_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    by_model = {}
    for item in results:
        by_model.setdefault(item["model_id"], []).append(item)

    for model_id, rows in by_model.items():
        gate_correct = sum(1 for row in rows if row["actual_gate"] == row["expect_gate"])
        tp_tool = sum(1 for row in rows if row["actual_tool_call"] and row["expect_tool_call"])
        fp_tool = sum(1 for row in rows if row["actual_tool_call"] and not row["expect_tool_call"])
        fn_tool = sum(1 for row in rows if (not row["actual_tool_call"]) and row["expect_tool_call"])
        create_correct = sum(1 for row in rows if row["actual_create"] == row["expect_create"])
        timed_rows = [row for row in rows if row["expect_create"]]
        timed_correct = sum(
            1
            for row in timed_rows
            if row["actual_has_time"] == row["expect_has_time"]
        )
        negative_rows = [row for row in rows if row["category"] == "negative"]
        false_positive_creates = sum(1 for row in negative_rows if row["actual_create"])

        summaries.append(
            {
                "model_id": model_id,
                "case_count": len(rows),
                "gate_accuracy": _safe_div(gate_correct, len(rows)),
                "tool_precision": _safe_div(tp_tool, tp_tool + fp_tool),
                "tool_recall": _safe_div(tp_tool, tp_tool + fn_tool),
                "tool_f1": _safe_div(2 * tp_tool, 2 * tp_tool + fp_tool + fn_tool),
                "create_accuracy": _safe_div(create_correct, len(rows)),
                "timed_create_accuracy": _safe_div(timed_correct, len(timed_rows)),
                "negative_false_create_rate": _safe_div(false_positive_creates, len(negative_rows)),
                "avg_gate_latency_seconds": round(sum(r["gate_latency_seconds"] for r in rows) / len(rows), 3),
                "avg_tool_latency_seconds": round(sum(r["tool_latency_seconds"] for r in rows) / len(rows), 3),
            }
        )

    return sorted(summaries, key=lambda row: row["tool_f1"], reverse=True)


def format_markdown_summary(summary: list[dict[str, Any]]) -> str:
    header = (
        "| Model | Gate Acc | Tool P | Tool R | Tool F1 | Create Acc | Timed Create Acc | Neg False Create | Gate Lat(s) | Tool Lat(s) |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    lines = [header]
    for row in summary:
        lines.append(
            "| {model_id} | {gate_accuracy:.2%} | {tool_precision:.2%} | {tool_recall:.2%} | "
            "{tool_f1:.2%} | {create_accuracy:.2%} | {timed_create_accuracy:.2%} | "
            "{negative_false_create_rate:.2%} | {avg_gate_latency_seconds:.3f} | {avg_tool_latency_seconds:.3f} |".format(
                **row
            )
        )
    return "\n".join(lines)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def run_cli(model_ids: list[str], output_path: Path | None = None) -> dict[str, Any]:
    benchmark = asyncio.run(benchmark_models(model_ids))
    if output_path is not None:
        output_path.write_text(
            json.dumps(_json_safe(benchmark), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return benchmark
