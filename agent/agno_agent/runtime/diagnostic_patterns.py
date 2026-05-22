from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent.agno_agent.runtime.domain_results import (
    DomainExecutionResult,
    ReplyContract,
    resolve_required_fact,
)

QUESTION_PATTERNS: dict[str, Sequence[str]] = {
    "end_time": (
        "截止时间",
        "什么时候结束",
        "持续到什么时候",
        "结束时间",
        "until when",
        "when should it end",
        "when should it stop",
    ),
    "target_reminder": (
        "哪条提醒",
        "提醒名称",
        "which reminder",
        "what reminder",
    ),
    "trigger_at": (
        "几点",
        "什么时候提醒",
        "提醒时间",
        "what time",
        "when should I remind",
    ),
    "title": (
        "提醒你做什么",
        "提醒内容",
        "what should I remind",
    ),
    "advance_offset": (
        "提前多久",
        "how far in advance",
    ),
}

CLAIM_PATTERNS: dict[str, Sequence[str]] = {
    "reminder_created": (
        "已创建提醒",
        "已设好提醒",
        "设置好了提醒",
        "提醒已创建",
        "created a reminder",
        "reminder is set",
        "set the reminder",
        "I will remind you",
        "I'll remind you",
    ),
    "not_created": (
        "没有创建提醒",
        "还没创建提醒",
        "未创建提醒",
        "reminder was not created",
        "did not create a reminder",
    ),
    "needs_more_info": (
        "还需要更多信息",
        "需要补充信息",
        "need more information",
        "need more info",
    ),
    "appointment_confirmed": (
        "已确认预约",
        "预约已确认",
        "confirmed the appointment",
        "appointment is confirmed",
    ),
}


def check_required_facts(result: DomainExecutionResult, text: str) -> list[str]:
    violations: list[str] = []
    normalized_text = _normalize(text)
    for requirement in result.reply_contract.required_facts:
        try:
            value = resolve_required_fact(result, requirement.path)
        except (IndexError, KeyError, ValueError):
            violations.append(f"missing required fact {requirement.path}")
            continue
        if value is None:
            violations.append(f"missing required fact {requirement.path}")
            continue
        if not any(
            _normalize(candidate) in normalized_text
            for candidate in _fact_variants(value)
        ):
            violations.append(f"missing required fact {requirement.path}")
    return violations


def check_required_questions(contract: ReplyContract, text: str) -> list[str]:
    normalized_text = _normalize(text)
    violations: list[str] = []
    for label in contract.required_questions:
        patterns = QUESTION_PATTERNS.get(label, ())
        if not patterns or not any(
            _normalize(pattern) in normalized_text for pattern in patterns
        ):
            violations.append(f"missing required question {label}")
    return violations


def check_prohibited_claims(contract: ReplyContract, text: str) -> list[str]:
    normalized_text = _normalize(text)
    violations: list[str] = []
    for label in contract.prohibited_claims:
        patterns = CLAIM_PATTERNS.get(label, ())
        if patterns and any(
            _normalize(pattern) in normalized_text for pattern in patterns
        ):
            violations.append(f"prohibited claim {label}")
    return violations


def _fact_variants(value: Any) -> Sequence[str]:
    text = str(value)
    variants = {text}
    if text.endswith(":00") and text.count(":") == 2:
        variants.add(text[:-3])
    if "T" in text:
        variants.add(text.replace("T", " "))
    return tuple(item for item in variants if item)


def _normalize(text: str) -> str:
    return "".join(str(text or "").casefold().split())
