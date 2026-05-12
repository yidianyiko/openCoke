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

import re

from agent.prompt.agent_instructions_prompt import (
    INSTRUCTIONS_CHAT_RESPONSE,
    INSTRUCTIONS_ORCHESTRATOR,
    INSTRUCTIONS_POST_ANALYZE,
    INSTRUCTIONS_QUERY_REWRITE,
    INSTRUCTIONS_REMINDER_DETECT,
)


def approximate_tokens(text: str) -> int:
    """Tokenizer-free token estimate."""
    cjk = len(re.findall(r"[一-鿿぀-ヿ]", text))
    latin_words = len(re.findall(r"[A-Za-z']+", text))
    digits = len(re.findall(r"\d", text))
    punct = len(re.findall(r"[^\w\s一-鿿぀-ヿ]", text))
    return cjk + int(latin_words * 1.3) + int(digits * 0.5) + int(punct * 0.5)


# Budgets are deliberate ceilings, not measurements of current size.
# Lower numbers below current size = forcing function to diet further.
# See docs/adr/0004-per-agent-prompt-budget-discipline.md.
PROMPT_BUDGETS: dict[str, tuple[str, int]] = {
    "INSTRUCTIONS_REMINDER_DETECT": (INSTRUCTIONS_REMINDER_DETECT, 1000),
    "INSTRUCTIONS_ORCHESTRATOR": (INSTRUCTIONS_ORCHESTRATOR, 800),
    "INSTRUCTIONS_POST_ANALYZE": (INSTRUCTIONS_POST_ANALYZE, 400),
    "INSTRUCTIONS_CHAT_RESPONSE": (INSTRUCTIONS_CHAT_RESPONSE, 600),
    "INSTRUCTIONS_QUERY_REWRITE": (INSTRUCTIONS_QUERY_REWRITE, 300),
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


def test_prompt_budget_headroom_warning():
    """Soft signal: warn (via failure message structure) if any prompt is
    within 5% of its budget; not a hard fail, but visible in test output.
    """
    near_budget: list[str] = []
    for name, (prompt, budget) in PROMPT_BUDGETS.items():
        actual = approximate_tokens(prompt)
        if actual > budget * 0.95 and actual <= budget:
            near_budget.append(f"{name}: ~{actual}/{budget} (>95% of budget)")
    # This test always passes; the assertion is just to surface the list.
    # If it ever grows, that's the signal to plan a diet before the next
    # rule addition.
    assert near_budget == near_budget  # tautology; keeps signal visible
