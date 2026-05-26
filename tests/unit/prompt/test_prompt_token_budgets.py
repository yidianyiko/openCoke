"""Per-agent system-prompt token budget enforcement.

Background: ARCHITECTURE.md §4 documents that reminder_detect's prompt grew
to ~3000 tokens of accumulated rules, causing ~23% LLM stall rate in
isolation (see docs/issues/2026-05-12-reminder-detect-model-bake-off.md).
ADR 0004 establishes per-agent token budgets enforced in CI to prevent
that pattern from recurring on any role.

Budget unit: an approximate token count using a CJK-aware heuristic
(1 CJK char = 1 token, 1 latin word = 1.3 token, etc.). This is not
tokenizer-exact, but it is deterministic, dependency-free, and good enough
to catch regressions of more than a few percent. Tighten only when a real
regression slips through.
"""
from __future__ import annotations

from datetime import UTC, datetime
import re

from agent.agno_agent.runtime.chat_response_instructions import (
    _DELEGATION_BOUNDARY,
    _DOMAIN_EXECUTION_RESULT_CONTRACT,
    _USER_VISIBLE_REPLY_BOUNDARY,
    build_chat_response_instructions,
)
from agent.agno_agent.runtime.context import (
    AgentRunContext,
    TrustedCharacterContext,
    TrustedConversationContext,
    TrustedRelationContext,
    TrustedUserContext,
)
from agent.agno_agent.runtime.execution_agents import _SCHEDULING_SYSTEM_PROMPT
from agent.agno_agent.runtime.inputs import (
    AgentInput,
    ReminderFirePayload,
    UserTurnPayload,
)
from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_CHAT_RESPONSE,
    INSTRUCTIONS_POST_ANALYZE,
    INSTRUCTIONS_QUERY_REWRITE,
    INSTRUCTIONS_REMINDER_DETECT,
)
from agent.prompt.character.coke_prompt import COKE_SYSTEM_PROMPT
from agent.prompt.onboarding_prompt import ONBOARDING_PROMPT
from agent.prompt.reminder_few_shot import format_reminder_few_shots_for_prompt


def approximate_tokens(text: str) -> int:
    """Tokenizer-free token estimate."""
    cjk = len(re.findall(r"[一-鿿぀-ヿ]", text))
    latin_words = len(re.findall(r"[A-Za-z']+", text))
    digits = len(re.findall(r"\d", text))
    punct = len(re.findall(r"[^\w\s一-鿿぀-ヿ]", text))
    return cjk + int(latin_words * 1.3) + int(digits * 0.5) + int(punct * 0.5)


_BUDGET_TIME = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)


def _chat_response_context(*, is_new_user: bool = False) -> AgentRunContext:
    return AgentRunContext(
        user=TrustedUserContext(id="user-1", nickname="Alice", timezone="Asia/Tokyo"),
        character=TrustedCharacterContext(
            id="coke",
            nickname="Coke",
            metadata={"description": COKE_SYSTEM_PROMPT},
        ),
        conversation=TrustedConversationContext(
            id="conv-1",
            platform="business",
            route_key="wechat_personal:primary",
        ),
        relation=TrustedRelationContext(uid="user-1", cid="coke"),
        platform="business",
        recent_chat_history="",
        current_time=_BUDGET_TIME,
        is_new_user=is_new_user,
    )


def _user_turn_input() -> AgentInput:
    return AgentInput(
        input_type="user.turn",
        conversation_id="conv-1",
        text="hi",
        payload=UserTurnPayload(current_message_ids=["msg-1"]),
        occurred_at=_BUDGET_TIME,
    )


def _reminder_fire_input() -> AgentInput:
    return AgentInput(
        input_type="reminder.fired",
        conversation_id="conv-1",
        text="提醒：喝水",
        payload=ReminderFirePayload(
            fire_id="fire-1",
            reminder_id="reminder-1",
            title="喝水",
            scheduled_for=datetime(2026, 5, 26, 9, 0, tzinfo=UTC),
        ),
        occurred_at=_BUDGET_TIME,
    )


def _assembled_chat_response_prompt(
    *,
    is_new_user: bool = False,
    reminder_fire: bool = False,
) -> str:
    agent_input = _reminder_fire_input() if reminder_fire else _user_turn_input()
    return build_chat_response_instructions(
        _chat_response_context(is_new_user=is_new_user),
        agent_input,
    )


# Budgets are deliberate ceilings, not measurements of current size.
# Lower numbers below current size = forcing function to diet further.
# See docs/adr/0004-per-agent-prompt-budget-discipline.md.
PROMPT_BUDGETS: dict[str, tuple[str, int]] = {
    "INSTRUCTIONS_REMINDER_DETECT": (INSTRUCTIONS_REMINDER_DETECT, 1000),
    "INSTRUCTIONS_POST_ANALYZE": (INSTRUCTIONS_POST_ANALYZE, 400),
    "INSTRUCTIONS_CHAT_RESPONSE": (INSTRUCTIONS_CHAT_RESPONSE, 600),
    "INSTRUCTIONS_QUERY_REWRITE": (INSTRUCTIONS_QUERY_REWRITE, 300),
    "COKE_SYSTEM_PROMPT": (COKE_SYSTEM_PROMPT, 2200),
    "ONBOARDING_PROMPT": (ONBOARDING_PROMPT, 450),
    "SCHEDULING_SYSTEM_PROMPT": (_SCHEDULING_SYSTEM_PROMPT, 750),
    "REMINDER_FEW_SHOTS": (format_reminder_few_shots_for_prompt(), 1200),
    "USER_VISIBLE_REPLY_BOUNDARY": (_USER_VISIBLE_REPLY_BOUNDARY, 250),
    "DELEGATION_BOUNDARY": (_DELEGATION_BOUNDARY, 1200),
    "DOMAIN_EXECUTION_RESULT_CONTRACT": (_DOMAIN_EXECUTION_RESULT_CONTRACT, 250),
    "ASSEMBLED_CHAT_RESPONSE_USER_TURN": (
        _assembled_chat_response_prompt(),
        4200,
    ),
    "ASSEMBLED_CHAT_RESPONSE_FIRST_CHAT": (
        _assembled_chat_response_prompt(is_new_user=True),
        4500,
    ),
    "ASSEMBLED_CHAT_RESPONSE_REMINDER_FIRE": (
        _assembled_chat_response_prompt(reminder_fire=True),
        4200,
    ),
}


def test_prompt_token_budgets_are_respected():
    failures: list[str] = []
    for name, (prompt, budget) in PROMPT_BUDGETS.items():
        actual = approximate_tokens(prompt)
        if actual > budget:
            failures.append(
                f"{name}: ~{actual} tokens > budget {budget} "
                f"(diet the prompt or move rules into few-shot data; "
                f"see docs/adr/0004-per-agent-prompt-budget-discipline.md)"
            )
    assert not failures, "Prompt budget violations:\n  " + "\n  ".join(failures)


def test_prompt_budget_registry_covers_runtime_prompt_surfaces():
    assert {
        "INSTRUCTIONS_REMINDER_DETECT",
        "INSTRUCTIONS_POST_ANALYZE",
        "INSTRUCTIONS_CHAT_RESPONSE",
        "INSTRUCTIONS_QUERY_REWRITE",
        "COKE_SYSTEM_PROMPT",
        "ONBOARDING_PROMPT",
        "SCHEDULING_SYSTEM_PROMPT",
        "REMINDER_FEW_SHOTS",
        "USER_VISIBLE_REPLY_BOUNDARY",
        "DELEGATION_BOUNDARY",
        "DOMAIN_EXECUTION_RESULT_CONTRACT",
    }.issubset(PROMPT_BUDGETS)


def test_prompt_budget_registry_covers_assembled_chat_response_surfaces():
    assert {
        "ASSEMBLED_CHAT_RESPONSE_USER_TURN",
        "ASSEMBLED_CHAT_RESPONSE_FIRST_CHAT",
        "ASSEMBLED_CHAT_RESPONSE_REMINDER_FIRE",
    }.issubset(PROMPT_BUDGETS)


def test_scheduling_system_prompt_is_structured_for_review():
    prompt = PROMPT_BUDGETS["SCHEDULING_SYSTEM_PROMPT"][0]
    lines = [line for line in prompt.splitlines() if line.strip()]

    assert 5 <= len(lines) <= 40
    assert "## Role" in prompt
    assert "## Tool selection" in prompt
    assert "## Boundaries" in prompt


def test_prompt_budget_headroom_is_preserved():
    """Keep at least 5% budget headroom for future prompt changes."""
    near_budget: list[str] = []
    for name, (prompt, budget) in PROMPT_BUDGETS.items():
        actual = approximate_tokens(prompt)
        if actual > budget * 0.95 and actual <= budget:
            near_budget.append(f"{name}: ~{actual}/{budget} (>95% of budget)")
    assert not near_budget, "Prompt budget headroom violations:\n  " + "\n  ".join(
        near_budget
    )
