---
kind: design
status: draft
title: Grounded recovery on turn failure — never leave the user silently waiting
created_at: 2026-06-08
updated_at: 2026-06-08
surface:
  - conversation-runtime
  - turn-runner
  - output-protocol
  - social-scheduling
related:
  - docs/issues/2026-06-07-shared-reminder-false-success.md
  - docs/issues/2026-06-07-real-user-delivery-loss-and-latency-survey.md
  - docs/issues/2026-06-06-eva-chat-rca.md
---

# Grounded Recovery On Turn Failure

## Problem

When an interactive inbound turn's agent output fails protocol validation
(`invalid_output_protocol`), the turn is marked `failed` and the user receives
**no reply at all** — only the 20s "我还在处理，稍等一下" holding message
(`coke/worker/waiting_reply.py`). The user's request is silently dropped.

### Evidence (production, gcp-coke)

User `eva` (account `94566791-4d39-4b28-9d9f-367c1ed0be2c`), 2026-06-08:

- seq 33 @ 02:58:21 "上午11点约 Oliver 健身。" (a shared booking with a friend)
- Turn `5ce4864c` (input seq 33→33) → disposition `failed` /
  `invalid_output_protocol`. Only the holding message was delivered.
- seq 34 @ 02:59:27 "晚上8点约了 Air Jelly。" started turn `6e4e6467`
  (input seq 33→34, the failed seq 33 correctly re-included in the window). It
  replied `replied` / `reply_ready` but addressed only Air Jelly and committed
  the reply, advancing `last_closed_inbound_seq` to 34 and permanently consuming
  the unanswered seq 33.
- Net for the 健身: no reminder row, no `notification_fact` (no invite to
  Oliver), no `recoverable_scheduling_intent`, no reply. Fully lost, no trace.

`invalid_output_protocol` is recurring (3× on 06-07, 1× on 06-08) and occurs
AFTER `dfd7d12d` ("normalize fenced interaction JSON output") was deployed
(worker live since 2026-06-07 15:18Z), so that fix does not cover this case.

### Three confirmed defects (cross-validated by the maintainer + 2 independent code traces)

1. **Defect A — silent fail-closed.** After one same-turn protocol retry
   (`coke/turn/runner.py:996-1008`), still-invalid output reaches
   `_record_validated_output` (`coke/turn/runner.py:1296`), calls `mark_failed`,
   and returns with no `visible_text` and no further retry (the worker's
   `SUPERVISED_TURN_FAILURE_RETRY_LIMIT` only retries `turn_task` *exceptions*,
   not normal `failed` dispositions — `coke/worker/__main__.py:273`). The
   interactive fallback hook at `coke/turn/runner.py:1010`
   (`_minimal_reminder_fire_reply`) returns `None` for non-`ReminderFireTurn`
   triggers, so interactive turns fall straight through to silence.
2. **Defect B — coalesced window drops unanswered messages.** A `failed` turn
   does NOT advance `last_closed_inbound_seq` (`service.py:301`, no
   `_save_close_state`), so the failed seq is correctly re-included in the next
   turn's window (`service.py:172`). But when that successor turn commits any
   valid reply, `commit_reply` closes the whole window through `input_to_seq`
   (`service.py:550`) with no per-message postcondition proving each message was
   addressed. The LLM answering only the latest message is therefore permanently
   consumed.
3. **Defect C (root cause) — `invalid_output_protocol` on shared bookings.**
   Shared/social bookings ("约 X 健身/吃饭") emit `invalid_output_protocol` via
   the social-scheduling contract validator (`coke/turn/output_protocol.py:130-160`
   `social_scheduling_*` retry-guidance codes; surfaced at
   `coke/llm/agno_interaction_agent.py:721-728`). `dfd7d12d` only normalized
   whole-response fenced JSON; the social-scheduling contract path and serialized
   tool-call output (`agno_interaction_agent.py:681-686`) still fail closed.

### Why fail-closed exists (must be preserved)

`8ff8de1c` ("fail closed on shared reminder false success", doc
`2026-06-07-shared-reminder-false-success.md`) intentionally fails the turn when
the agent claims a shared-reminder success that has no durable active row. This
prevents a trust-critical lie ("已建好" when nothing exists). The silent-drop is
the *side effect*: the system correctly refuses to lie, but then says nothing.
**Any fix must keep the no-false-success guarantee.**

## Goals

- The user is **never** left with only the holding message. Every interactive
  inbound turn ends with a truthful user-facing reply OR a monitored, alerted
  exception (never silent success-shaped nothing).
- Recovery copy is **grounded in real state**, never a fabricated cause and never
  a `reason_code → message` lookup table.
- On failure, when the user can help (missing/ambiguous info), the reply asks
  them to add detail / confirm, so the next turn can succeed.
- Reduce how often shared bookings fail validation at all (root cause).
- Preserve the no-false-success contract: a failed turn performs **no** durable
  state change.

## Non-Goals

- Guaranteeing semantic exactly-once "every message answered" for arbitrary
  multi-intent windows (Defect B mitigation is bounded; see Component 3).
- Changing delivery-layer behavior (ret:-2 / connector concurrency are separate
  tracked issues).
- Re-running the failing LLM to produce the apology (the recovery must not depend
  on the same model that just failed).

## Design: the legacy pattern, adapted

The pre-rebuild server (`/data/projects/coke-legacy-server`,
`agent/agno_agent/workflows/chat_workflow_streaming.py:345-479`) already solved
the never-silent problem WITHOUT a reason-code table: when the model yielded zero
parseable messages it called `_build_tool_result_fallback(session_state)`, which
reconstructs the reply from the **real tool-execution context**
(`result_summary`, `intent_fulfilled`, `action_executed`) — truthful success
text when fulfilled, and "这次没成功，你再补充一下具体时间或内容" when not. The
clean rebuild regressed this into silence. We restore the pattern using the
clean-rebuild equivalent of `tool_execution_context`: the turn's trusted domain
signals (staged commands, tool/domain outcomes, and — as the always-available
floor — the user's own input text).

Three components, implementable and shippable in order.

### Component 1 — Grounded recovery reply on turn failure (keystone)

**Seam.** Replace the interactive fall-through at `coke/turn/runner.py:1009-1012`.
Today: if the post-retry output is still invalid, `_minimal_reminder_fire_reply`
returns a templated reply only for `ReminderFireTurn`, else `None` → silent fail.
Add `_grounded_recovery_reply(request, validated, tool_events)` that returns a
valid `ValidatedOutput` (`valid=True`, `kind="reply"`,
`segments=(recovery_text,)`, `reason_code="grounded_failure_recovery"`) for
interactive inbound turns, so `_record_validated_output` takes the normal
reply-delivery branch and the user receives it.

**Grounding sources, in priority order (no reason-code→message table):**

1. **Staged command intent.** A turn stages domain commands that materialize only
   on a clean close (`service.py:344` `stage_command`). On `mark_failed` they do
   NOT materialize, so the action truthfully did not happen. If a staged command
   exists, use its captured intent (e.g. "约 olivers 11:00 健身") to say what we
   understood and that it did not complete, and ask the user to confirm/retry.
2. **Tool / domain outcome facts.** If `tool_events` / `trusted_facts` carry a
   concrete blocker that is user-actionable AND verified (e.g. an ambiguous-
   friend or missing-time outcome already surfaced by a tool), reference it to
   ask the specific clarifying question. Only use a blocker that the tool
   actually produced — never infer one from the protocol `reason_code`.
3. **Input message text floor.** Always available: the user's own message
   (`current_input_messages`). When no staged intent or verified blocker exists,
   reference what the user asked for and request a rephrase/more detail. This is
   grounded (the user's own words), never fabricated, and covers the opaque
   `serialized_tool_call_output` / unparseable-JSON cases.

**Truthfulness constraints.**

- The recovery reply MUST NOT claim any action succeeded (no false success). A
  failed turn makes no durable change; staged commands are discarded, not
  materialized.
- The recovery reply MUST NOT state a specific failure cause that was not
  actually produced by a tool/domain outcome (no fabricated "Oliver isn't your
  friend"). "I couldn't confirm this went through, could you tell me X again?" is
  honest; a specific invented reason is the inverse false-claim.
- Recovery copy is deterministic (no LLM call), composed from the grounded
  sources above plus a small number of fixed sentence frames (a frame is "我没能
  帮你完成 {intent}，{ask}" — not a reason-code lookup table).

**Never-silent guarantee.** For an interactive inbound turn, the only paths that
may end without a user reply are an intentional `no_reply` (model deliberately
stayed silent on a non-actionable message — unchanged) and a hard exception
(already routed to the worker failure path + logging). A `failed` disposition
must no longer be such a path.

### Component 2 — Reduce shared-booking validation failures (root cause)

`invalid_output_protocol` on shared bookings is the trigger that Component 1
gracefully catches; Component 2 reduces how often it fires.

**Reproduction first (gate).** Build a regression case that drives a shared
booking ("约 {friend} {time} 健身") through the interaction agent against the
real social-scheduling contract validator and reproduces an
`invalid_output_protocol` with a `social_scheduling_*` retry-guidance code. The
exact production output for eva's turn is unrecoverable (worker container was
recreated), so reproduction defines the fix.

**Likely cause and fix direction (to confirm via reproduction).** The validator
fails when the agent's claim does not match a durable social-scheduling outcome
(`output_protocol.py:120-152`). The fix is at the agent-contract layer: make the
agent's shared-booking reply contract reliably emit a claim that matches the
staged/committed outcome (or no claim when it staged a create command for close
materialization), so a legitimate booking validates instead of failing closed.
Do NOT weaken the validator to pass — that would reopen the false-success hole
(`8ff8de1c`). If reproduction shows the failure is genuine model malformation
(not a contract mismatch), Component 1 is the correct and sufficient handling and
Component 2 reduces to prompt/contract hardening only.

### Component 3 — Coalesced-window answer completeness (bounded)

With Component 1 in place, eva's actual path is largely fixed: the failed seq-33
turn now replies a grounded recovery before seq 34 arrives, so the 健身 is no
longer silently lost. Component 3 addresses the distinct residual: a *successful*
turn whose input window covers multiple distinct messages but whose reply
addresses only a subset, after which `commit_reply` closes the whole window.

**Mechanism (bounded, deterministic at the attribution level).** When a turn's
input window covers more than one inbound message, require the agent output to
carry a per-input-message acknowledgment/outcome attribution (the prompt at
`agno_interaction_agent.py:982` already instructs sequence-order answering; make
it a checked postcondition). Any input seq in the window with no corresponding
acknowledgment/outcome is NOT closed: instead it is re-enqueued as a fresh inbound
trigger (re-using the existing open-window recovery path,
`_recover_open_inbound_windows` in `coke/worker/__main__.py:146`) rather than
consumed by `_save_close_state`.

**Limits (call out for review).** This guards structural attribution ("did the
agent claim to handle message X"), not semantic truth. It is the
highest-uncertainty component; if review finds the attribution requirement
brittle, Component 3 may ship as a follow-up after Component 1+2 are confirmed to
resolve eva's case in production.

## Testing / Verification

- **Component 1 unit:** an interactive inbound turn whose agent output is invalid
  after retry produces a `kind="reply"` recovery `ValidatedOutput`, the reply is
  delivered, no durable state change occurs, and the copy contains no
  success/fabricated-cause claim. Cover all three grounding sources (staged
  intent, verified blocker, input-text floor) and the
  `serialized_tool_call_output` opaque case.
- **Component 2:** the reproduction regression goes from red
  (`invalid_output_protocol`) to green (valid booking reply with a matching
  durable outcome), and the false-success regressions from
  `2026-06-07-shared-reminder-false-success.md` stay green.
- **Component 3:** a turn over a 2-message window where the agent answers only the
  newer message re-enqueues the older seq instead of closing it; a turn that
  answers both closes normally.
- **Suite + routing:** `.venv/bin/python -m pytest tests/unit/coke -q`;
  `zsh scripts/suggest-verification --base HEAD~1`; `zsh scripts/review-trigger
  --base HEAD~1`.
- **Production confirmation (post-deploy):** re-run the eva shared-booking flow on
  the real account; confirm a grounded recovery reply is delivered (not silence)
  and no false-success row is created.

## Rollout / Risks

- Ship Component 1 first (keystone; removes the silent drop with no contract
  change). Then Component 2 (reproduce → fix). Component 3 last, possibly as a
  follow-up.
- Risk: a grounded recovery that accidentally implies success. Mitigated by the
  no-false-success constraint and tests asserting absence of success claims.
- Risk: recovery loops if Component 2 is unshipped (user retries, hits the same
  invalid output, gets another recovery). Acceptable interim — a clear "couldn't
  do it, try again" beats silence — and Component 2 closes the loop.

## Open Questions

- Component 1: when a turn staged a *valid* command but only the reply text was
  malformed, do we still discard (current proposal, strict no-false-success) or
  materialize the staged command and report real success? Default: discard
  (strict). Revisit if reproduction shows valid stages are common.
- Component 3: is the per-message attribution postcondition robust enough, or
  should it be deferred? Decide after Codex review.
