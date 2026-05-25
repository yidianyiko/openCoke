---
status: draft
created_at: 2026-05-26
owner: bug-x-fix
kind: prompt-design
---

# Bug X prompt debooking design

## Problem

The coach-booking hunt shows that Coke over-refuses friend-to-friend lesson
coordination when the user says things like `约教练 Alex 明天 10:00 上一节课`.
The intended product mapping is not an external booking API call. It is a
`create_shared_reminder` request between two Coke friends, later accepted or
rejected by the other side.

Coke still must not claim it called an external coach-booking app or confirmed
an offline class through a third party. Direction: less prompt, not more; remove
broad "coach/class booking is forbidden" wording, and do not add a new case
table of booking phrases.

## Current state

`agent/prompt/onboarding_prompt.py:32` currently says:

```text
只介绍当前真实能做的事；绝不承诺已经设置提醒、已经预约课程或约见教练，除非当前系统上下文有成功工具结果。课程预约、约见教练目前不在你的能力范围里——用户问到时直接说不能帮约，请他自己去 App 或线下处理。
```

The second sentence is the over-refusal trigger because it does not distinguish
external booking from an in-product shared reminder with an active friend.

`agent/prompt/character/coke_prompt.py:22` currently says:

```text
你**没有**直接代用户预约线下教练课程或第三方课程的能力。如果用户提到要约线下教练或第三方课程，请直接说明你只能帮设置提醒，真正预约需要用户自己去 App 或线下处理；绝不能说你已经约好或已经跟教练确认。
```

`agent/prompt/character/coke_prompt.py:48` currently says:

```text
4. 如果用户提到线下课程预约或约教练，明确告诉他你不能直接帮约——只能帮他设个到点提醒，预约本身要他自己去 App 或线下处理。不要追问"要不要帮你跟教练确认"这种你做不了的事。
```

`agent/prompt/character/coke_prompt.py:49` currently says:

```text
5. 只有当提醒工具确认成功后，才能说“我到时候提醒你”或类似话；在此之前只能询问或提出建议。绝不说"已经帮你约好课"、"已经跟教练确认"这类你无能力交付的话。
```

`agent/prompt/character/coke_prompt.py:108` currently says:

```text
**绝不承诺线下课程预约或代约教练已完成**——这不在你的能力范围内。
```

`agent/prompt/character/coke_prompt.py:124` currently says:

```text
未来提醒、课程预约和监督承诺必须基于已确认的系统状态。
```

Lines 22 and 48 are the direct refusal rules. Lines 49, 108, and 124 should be
generalized to tool-confirmed writes.

`agent/agno_agent/runtime/chat_response_instructions.py:39` currently says:

```text
- Requests to book, reserve, or schedule a coach, class, lesson, or session are unsupported. Do not call reminder_domain or scheduling_domain for the booking itself. Reply directly with a clear refusal, say Coke can help with reminders, friend coordination, or shared reminders, and only create a reminder after the user asks for a reminder with enough details or confirms one.
```

This prompt-level refusal can still make C1/C5/C6/C8/C9/C12 refuse instead of
calling `scheduling_domain`.

The same file already has the positive shared-reminder rule at
`chat_response_instructions.py:40`, and supporting constraints at lines 43-44:

```text
- When the user explicitly directs a scheduling action with a clear target ... create / accept / reject / cancel a shared reminder ... you MUST call scheduling_domain with the matching intent in this same turn.
- A shared reminder requires one active friend. If the named person is not an active friend, explain that the user must add them as a friend first.
- For create_shared_reminder, derive the title from the concrete shared item the user is asking to schedule in the current turn.
```

`agent/agno_agent/capabilities/scheduling.py` exposes shared-reminder create /
accept / reject / cancel tools. Successful `create_shared_reminder` writes get
the visible summary `已提交共享提醒请求。`.

`agent/agno_agent/capabilities/reminder_intent.py` has
`_is_unsupported_booking_request`. It blocks hidden one-person reminder writes
for unsupported booking wording unless the user explicitly says `提醒我`; it
does not block `scheduling_domain`.

`agent/agno_agent/runtime/agent_runtime.py` has
`_check_unconfirmed_durable_write_promise`, which blocks reminder /
shared-reminder / friend-request write claims without a successful write. The
helper `_is_reminder_capability_offer_not_write_claim` lets safe reminder
offers through when they do not claim completion.

## Proposed change

Replace the current line 32 sentence with:

```text
只介绍当前真实能做的事；绝不承诺已经设置提醒，除非当前系统上下文有成功工具结果。
```

Delete the second sentence entirely:

```text
课程预约、约见教练目前不在你的能力范围里——用户问到时直接说不能帮约，请他自己去 App 或线下处理。
```

No replacement is needed. The onboarding capability list already mentions
friends and shared reminders.

Delete line 22 entirely:

```text
你**没有**直接代用户预约线下教练课程或第三方课程的能力。如果用户提到要约线下教练或第三方课程，请直接说明你只能帮设置提醒，真正预约需要用户自己去 App 或线下处理；绝不能说你已经约好或已经跟教练确认。
```

Delete line 48 entirely and renumber the following item:

```text
4. 如果用户提到线下课程预约或约教练，明确告诉他你不能直接帮约——只能帮他设个到点提醒，预约本身要他自己去 App 或线下处理。不要追问"要不要帮你跟教练确认"这种你做不了的事。
```

Replace the current line 49 with a general tool-result rule:

```text
4. 只有当 reminder_domain 或 scheduling_domain 返回 ok=True 且 effect=write 的成功结果后，才能承诺未来提醒、共享提醒请求/接受/取消或监督跟进。在此之前只能询问、建议或根据工具失败结果说明未完成。
```

Replace the current line 108 with:

```text
绝不把没有成功工具结果的未来提醒、共享提醒、好友请求或外部预约说成已经完成。
```

Replace the current line 124 with:

```text
未来提醒、共享提醒、好友协作和监督承诺必须基于已确认的系统状态。
```

These replacements preserve the no-unconfirmed-write contract without saying
"always refuse coach/class/course booking".

Delete line 39 entirely:

```text
- Requests to book, reserve, or schedule a coach, class, lesson, or session are unsupported. Do not call reminder_domain or scheduling_domain for the booking itself. Reply directly with a clear refusal, say Coke can help with reminders, friend coordination, or shared reminders, and only create a reminder after the user asks for a reminder with enough details or confirms one.
```

No replacement. The next lines already say explicit shared-reminder actions
must call `scheduling_domain`, that shared reminders require an active friend,
and that titles must come from the current shared item.

- `tests/unit/agent/test_chat_response_instructions.py`: stop asserting the
  removed broad-refusal phrases; add negative assertions for them; keep positive
  assertions for shared-reminder capability and tool-result grounding.
- `tests/unit/agent/test_default_character_bootstrap.py`: stop requiring the
  `没有` + `预约` disclaimer; require generalized successful-tool-result wording.
- Keep output-rule coverage for reminder offers vs completed claims, and keep
  reminder-intent coverage that unsupported direct booking text does not create
  a personal reminder.

## Risk analysis

Commit `8d811077` fixed a real failure: the old prompt advertised "帮你约课"
and "约彭教练" despite no external booking backend. It was preventing:

1. Claims that Coke can book a class with 彭教练.
2. Claims like "已经帮你约好课" or "已经跟教练确认" without any system write.
3. Hidden personal reminders from unsupported direct booking text.
4. Safe refusal-plus-reminder-offer text being dropped as an unconfirmed write.

The current explicit refusal solved those failures too broadly. It now blocks
valid shared-reminder scheduling with an active friend named Coach Alex.

- `_check_unconfirmed_durable_write_promise` blocks reminder/shared-reminder
  creation claims when no successful write result exists.
- `_is_reminder_capability_offer_not_write_claim` prevents safe reminder
  offers from being converted into empty fallback, so the prior false positive
  from `d415235e` stays fixed.
- `_is_unsupported_booking_request` keeps the personal reminder detector from
  writing a hidden `约彭教练` reminder for unsupported direct booking phrasing.
- `scheduling_domain` and the gateway own shared-reminder writes;
  `create_shared_reminder` requires one active friend and fails closed.
- The domain execution result contract says the final reply must not claim a
  write unless an operation reports `ok=True` and `effect=write`.

- The unconfirmed-write guardrail does not fully cover a pure external booking
  hallucination such as "已帮你约好彭教练" if the text does not look like a
  reminder/shared-reminder/friend-request claim.
- The existing `_runner_phase_class_booking_refusal.py` smoke is therefore
  required after the fix. If it fails with a hallucinated external booking
  confirmation, the right follow-up is a narrow runtime/output-claim guardrail
  for unsupported external appointment confirmations, not restoring broad
  prompt-level refusal.
- If it fails because the model maps a no-friend external request into shared
  reminder, surface the gateway/name-resolution failure clearly. Do not restore
  a prompt rule that all coach/class/lesson wording must be refused.

## Verification plan

Do not rerun hunts in this design codex. The fix codex should run these after
editing.

- Prompt text no longer contains the removed broad-refusal strings:
  `课程预约、约见教练目前不在你的能力范围里`,
  `如果用户提到线下课程预约或约教练，明确告诉他你不能直接帮约`,
  `Requests to book, reserve, or schedule... are unsupported`, or
  `Do not call reminder_domain or scheduling_domain for the booking itself`.
- Prompt text still contains shared-reminder capability, successful-tool-result
  grounding, and the domain result contract for executed write facts.
- Existing unit tests still prove direct reminder promises and completed
  shared-reminder claims fail closed without a write; safe reminder offers pass;
  unsupported direct booking text does not write personal reminders; explicit
  reminder-about-booking text can create a personal reminder; and
  `create_shared_reminder` still writes a `shared_reminder_request`.

Suggested focused unit command:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_chat_response_instructions.py \
  tests/unit/agent/test_default_character_bootstrap.py \
  tests/unit/agent/test_agent_runtime_output_rules.py \
  tests/unit/agent/test_reminder_intent_capability.py \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_execution_agents.py \
  -q
```

Smoke re-runs required for the fix:

```bash
.venv/bin/python tools/agent_smoke/_runner_phase_coach_booking_hunt.py
```

Expected change: C1 must pass. C5, C6, C7, C8, C9, and C12 should be unblocked
from the over-refusal pattern and either pass or expose narrower non-prompt
bugs. C10 invented availability and C13 Bug B empty fallback are out of scope.

```bash
.venv/bin/python tools/agent_smoke/_runner_phase_class_booking_refusal.py
```

This must still pass unchanged. The agent must not regress to replies like
`好嘞，已帮你约了彭教练`, must not emit empty fallback, and must not create
hidden personal reminders for unsupported direct booking prompts.

Also run diff-aware routing after the fix:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Do not change the LLM model. It remains GLM-5.1 thinking-off. Do not
reintroduce `blockAccount`.

## Out of scope

- C10 invented availability. That needs its own design.
- C13 Bug B empty fallback. That needs its own design.
- Any new coach-booking product contract, availability window, conflict
  detection, or external booking integration.
- Any prompt enumeration of every possible `约课` wording.

## Reviewable summary

- Delete the broad coach/class/course refusal wording from onboarding, Coke
  character prompt, and the chat-response delegation boundary.
- Keep only generalized "do not claim a write without successful tool result"
  wording.
- Let valid active-friend lesson requests route to `create_shared_reminder`
  instead of forcing refusal.
- Keep the personal reminder booking guardrail so unsupported booking text does
  not create hidden one-person reminders.
- Rely on runtime write-claim guardrails for reminder/shared-reminder claims,
  and treat pure external booking confirmation as residual smoke-covered risk.
- Verify with focused prompt/runtime unit tests, then rerun both the coach
  booking hunt and the class-booking refusal smoke.
- C10 invented availability and C13 empty fallback are explicitly separate
  fixes.
