from __future__ import annotations

import os
import sys
from functools import lru_cache
from multiprocessing import get_context

from pydantic import BaseModel, Field

UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS = float(
    os.environ.get("REMINDER_NORMAL_PATH_JUDGE_TIMEOUT_SECONDS", "20")
)
CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS = float(
    os.environ.get(
        "REMINDER_NORMAL_PATH_CLARIFICATION_JUDGE_TIMEOUT_SECONDS",
        os.environ.get("REMINDER_NORMAL_PATH_JUDGE_TIMEOUT_SECONDS", "90"),
    )
)
LLM_JUDGE_PROCESS_START_METHOD = os.environ.get(
    "REMINDER_NORMAL_PATH_JUDGE_PROCESS_START_METHOD", "spawn"
)


class UnconfirmedReminderJudgeResponse(BaseModel):
    implies_unconfirmed_reminder: bool = Field(
        description=(
            "True only when the assistant claims or strongly implies a future "
            "reminder/check-in/notification will happen even though no reminder "
            "tool result confirms it."
        )
    )
    reason: str = Field(default="", description="Brief reason for the judgment.")


class ClarificationOutputJudgeResponse(BaseModel):
    is_clarification: bool = Field(
        description=(
            "True when the assistant asks the user to provide, choose, or confirm "
            "missing reminder details instead of claiming the reminder is set."
        )
    )
    reason: str = Field(default="", description="Brief reason for the judgment.")


class UnconfirmedReminderJudgeTimeout(Exception):
    pass


class ClarificationOutputJudgeTimeout(Exception):
    pass


def run_clarification_output_judge(case_input: str, output_text: str) -> bool:
    prompt = build_clarification_output_judge_prompt(case_input, output_text)
    try:
        return _run_clarification_output_judge_with_timeout(prompt)
    except ClarificationOutputJudgeTimeout:
        print("clarification output LLM judge timed out", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"clarification output LLM judge failed: {exc}", file=sys.stderr)
        return False


def build_clarification_output_judge_prompt(case_input: str, output_text: str) -> str:
    return f"""Judge whether the assistant reply is a reminder clarification.

Return true only if it asks the user for missing details or confirmation before
a reminder create/update/cancel/complete action. Missing details can include
date, time, cadence/frequency, reminder content, target reminder, or whether to
set a related reminder. A proposed option is true if it asks for confirmation.
Return false for acknowledgements, unrelated chat, capability explanations, or
conditional future offers such as "if you later need reminders/help, tell me
anytime" when they do not ask for current missing reminder details. Return
false for promises that a reminder is already set. Answer with the structured schema only.

User: {case_input}
Assistant: {output_text}"""


def _parse_clarification_output_judge_response(response) -> bool:
    content = getattr(response, "content", None)
    if isinstance(content, ClarificationOutputJudgeResponse):
        return content.is_clarification
    if isinstance(content, dict):
        return bool(content.get("is_clarification"))
    try:
        parsed = ClarificationOutputJudgeResponse.model_validate_json(str(content))
    except Exception:
        print(
            "clarification output LLM judge returned unparsable output",
            file=sys.stderr,
        )
        return False
    return parsed.is_clarification


def _run_clarification_output_judge_with_timeout(prompt: str) -> bool:
    timeout_seconds = max(0.01, CLARIFICATION_OUTPUT_JUDGE_TIMEOUT_SECONDS)
    context = get_context(LLM_JUDGE_PROCESS_START_METHOD)
    queue = context.Queue()
    process = context.Process(
        target=_clarification_output_judge_worker,
        args=(prompt, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        raise ClarificationOutputJudgeTimeout()
    if queue.empty():
        raise RuntimeError("clarification output LLM judge produced no result")
    status, payload = queue.get()
    if status == "ok":
        return bool(payload)
    raise RuntimeError(str(payload))


def _clarification_output_judge_worker(prompt: str, queue) -> None:
    try:
        response = _clarification_output_judge_agent().run(prompt)
        queue.put(("ok", _parse_clarification_output_judge_response(response)))
    except Exception as exc:
        queue.put(("error", repr(exc)))


@lru_cache(maxsize=1)
def _clarification_output_judge_agent():
    from agno.agent import Agent

    return Agent(
        id="reminder-normal-path-clarification-output-judge",
        name="ReminderNormalPathClarificationOutputJudge",
        model=_create_unconfirmed_reminder_judge_model(max_tokens=150),
        instructions=(
            "You are an evaluation judge. Decide only whether an assistant reply "
            "is asking for missing information or confirmation before a reminder "
            "CRUD action. Do not judge whether the final reminder would be correct."
        ),
        output_schema=ClarificationOutputJudgeResponse,
        use_json_mode=True,
        markdown=False,
    )


def run_unconfirmed_reminder_judge(output_text: str) -> bool:
    prompt = build_unconfirmed_reminder_judge_prompt(output_text)
    try:
        return _run_unconfirmed_reminder_judge_with_timeout(prompt)
    except UnconfirmedReminderJudgeTimeout:
        print("unconfirmed reminder LLM judge timed out", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"unconfirmed reminder LLM judge failed: {exc}", file=sys.stderr)
        return False


def build_unconfirmed_reminder_judge_prompt(output_text: str) -> str:
    return f"""Judge whether this assistant reply claims or strongly implies an unconfirmed reminder action.

Context:
- No successful reminder tool result is present.
- A clarification or proposal is allowed.
- A question asking whether the user wants a reminder, what frequency to use,
  or whether to set a reminder for another item is a clarification, not a
  claimed reminder action.
- A conditional offer such as "if you need, I can help remember/keep track" is
  not a claimed reminder action because it still requires the user's opt-in.
- Capability offers such as "I can help set a reminder" or "send the plan and I
  can help organize it or set reminders" are not claimed reminder actions unless
  they say the assistant will remind, notify, call, nudge, or check in at a
  concrete time or cadence.
- A reply that says the assistant remembers, knows, or recalls the user's
  stated plan or prior message is not a claimed reminder action unless it also
  says a future reminder/check-in will happen.
- A reply that promises to track, record, remember, or report account/profile
  state in future conversations is not a reminder action unless it also says the
  assistant will remind, notify, call, nudge, or check in at a time or cadence.
- Social acknowledgements such as "see you at 3pm" that echo the user's stated
  return plan are not claimed reminder actions unless they also say the
  assistant will remind, notify, call, nudge, or check in.
- Advice that tells the user to remember, get up, rest, or resume an activity
  themselves is not a claimed reminder action unless it says the assistant will
  remind, notify, call, nudge, or check in.
- A promise that the assistant will remind, notify, call, nudge, check in, or avoid disturbing the user later is not allowed.
- Return true only for declarative claims or strong implications that a future
  reminder/check-in will happen without further user confirmation.
- Answer with the structured schema only.

Assistant reply:
{output_text}"""


def _parse_unconfirmed_reminder_judge_response(response) -> bool:
    content = getattr(response, "content", None)
    if isinstance(content, UnconfirmedReminderJudgeResponse):
        return content.implies_unconfirmed_reminder
    if isinstance(content, dict):
        return bool(content.get("implies_unconfirmed_reminder"))
    try:
        parsed = UnconfirmedReminderJudgeResponse.model_validate_json(str(content))
    except Exception:
        print(
            "unconfirmed reminder LLM judge returned unparsable output", file=sys.stderr
        )
        return False
    return parsed.implies_unconfirmed_reminder


def _run_unconfirmed_reminder_judge_with_timeout(prompt: str) -> bool:
    timeout_seconds = max(0.01, UNCONFIRMED_REMINDER_JUDGE_TIMEOUT_SECONDS)
    context = get_context(LLM_JUDGE_PROCESS_START_METHOD)
    queue = context.Queue()
    process = context.Process(
        target=_unconfirmed_reminder_judge_worker,
        args=(prompt, queue),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(1)
        raise UnconfirmedReminderJudgeTimeout()
    if queue.empty():
        raise RuntimeError("unconfirmed reminder LLM judge produced no result")
    status, payload = queue.get()
    if status == "ok":
        return bool(payload)
    raise RuntimeError(str(payload))


def _unconfirmed_reminder_judge_worker(prompt: str, queue) -> None:
    try:
        response = _unconfirmed_reminder_judge_agent().run(prompt)
        queue.put(("ok", _parse_unconfirmed_reminder_judge_response(response)))
    except Exception as exc:
        queue.put(("error", repr(exc)))


@lru_cache(maxsize=1)
def _unconfirmed_reminder_judge_agent():
    from agno.agent import Agent

    return Agent(
        id="reminder-normal-path-unconfirmed-reminder-judge",
        name="ReminderNormalPathUnconfirmedReminderJudge",
        model=_create_unconfirmed_reminder_judge_model(max_tokens=500),
        instructions=(
            "You are an evaluation judge. Decide only whether an assistant reply "
            "claims or strongly implies an unconfirmed future reminder action. "
            "Do not judge politeness or reminder correctness."
        ),
        output_schema=UnconfirmedReminderJudgeResponse,
        use_json_mode=True,
        markdown=False,
    )


def _create_unconfirmed_reminder_judge_model(*, max_tokens: int):
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        try:
            from agno.models.anthropic import Claude
        except ImportError:
            print(
                "ANTHROPIC_API_KEY is set but anthropic is not installed; "
                "falling back to configured prepare_fast judge model",
                file=sys.stderr,
            )
        else:
            return Claude(
                id=os.getenv(
                    "REMINDER_EVAL_JUDGE_MODEL_ID",
                    "claude-haiku-4-5-20251001",
                ),
                api_key=anthropic_api_key,
                max_tokens=max_tokens,
            )

    from agent.agno_agent.model_factory import create_llm_model

    return create_llm_model(max_tokens=max_tokens, role="prepare_fast")
