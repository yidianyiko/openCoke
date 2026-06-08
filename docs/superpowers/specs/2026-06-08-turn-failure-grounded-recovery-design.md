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

- Guaranteeing semantic "every message answered" for arbitrary multi-intent
  windows (general Defect B; deferred — see Component 3). Eva's specific
  failed-then-coalesced path IS fixed by Component 1's window-closing recovery.
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

Two shippable components in order (Component 1 keystone, then Component 2 root
cause); Component 3 is deferred (see below).

### Component 1 — Grounded recovery reply on turn failure (keystone)

**Seam.** Replace the interactive fall-through at `coke/turn/runner.py:1009-1012`.
Today: if the post-retry output is still invalid, `_minimal_reminder_fire_reply`
returns a templated reply only for `ReminderFireTurn`, else `None` → silent fail.

**Do NOT reuse the normal `kind="reply"` branch.** Both code reviews flagged that
that branch (`coke/turn/runner.py:1333`) calls `commit_reply`, which
**materializes staged commands** before closing (`service.py:223`,
`_save_close_state` `service.py:550`). Routing recovery through it would perform
the user's action from a failed turn — re-opening exactly the false-success /
trust hole `8ff8de1c` closed, and breaking the existing regression that asserts a
failed turn leaves the staged command `status=="staged"` and creates no row
(`tests/unit/coke/turn/test_turn_runner.py:1207`).

**Add a dedicated recovery close+deliver path.** When post-retry output is still
invalid for an interactive inbound turn, build a grounded `recovery_text` and
record it through a NEW conversation-runtime method
`commit_recovery_reply(turn_id, segments=(recovery_text,),
reason_code="grounded_failure_recovery")` that:

- records a distinct `recovered` disposition (failure stays observable in
  metrics — it is not a normal `replied`),
- does **NOT** materialize staged commands — leaves them inert and marks them
  superseded (never `_materialize_staged_command`),
- advances `last_closed_inbound_seq` to the turn's `input_to_seq` via
  `_save_close_state`, so the message is handled-by-recovery and not reprocessed.

The runner then runs the existing reply delivery loop (`runner.py:1347-1368`) on
`recovery_text` so the user receives it. This is the only change to delivery.

Closing the window here also resolves eva's coalescing path directly: seq 33 is
closed by its own recovery reply, so it is never re-included in seq 34's turn (see
Component 3).

**Grounding sources, in priority order (no reason-code→message table):**

1. **Staged command intent.** A turn stages domain commands that materialize only
   on a clean close (`service.py:344` `stage_command`). Read them at the seam via
   `repository.staged_commands_for_turn(turn_id)` (reachable through
   `request.freshness_guard.conversation_runtime.repository`; they are NOT on
   `AgentRequest`). If a staged command exists, use its captured intent (e.g.
   "约 olivers 11:00 健身") to say what we understood and that it did not complete,
   and ask the user to confirm/retry.
2. **Structured tool/domain outcome facts.** If `tool_events` (passed into the
   seam already as the `tool_events` arg) carry a concrete user-actionable blocker
   the tool actually produced (ambiguous-friend, missing-time), reference it to
   ask the specific clarifying question. Use ONLY structured tool-event facts —
   never scrape `serialized_tool_call_output` markup as intent, and never infer a
   blocker from the protocol `reason_code`. Note: the `social_scheduling_*`
   validation reason codes are NOT preserved at the runner seam today
   (`output_protocol.py:51` only forwards serialized-tool-call and
   state-change-without-tool reasons), so this source must not depend on them.
3. **Input message text floor.** Always available: the user's own message
   (`current_input_messages` on `AgentRequest`). When no staged intent or
   structured blocker exists, reference what the user asked for and request a
   rephrase/more detail. Grounded in the user's own words, never fabricated;
   covers the opaque `serialized_tool_call_output` / unparseable-JSON cases.

**Truthfulness constraints.**

- The recovery reply MUST NOT claim any action succeeded (no false success). The
  recovery close performs no durable change: staged commands are left inert and
  marked superseded, never materialized (today `mark_failed` already leaves them
  `status=="staged"`; the recovery path must preserve that no-materialization
  invariant).
- The recovery reply MUST NOT state a specific failure cause that was not
  actually produced by a tool/domain outcome (no fabricated "Oliver isn't your
  friend"). "I couldn't confirm this went through, could you tell me X again?" is
  honest; a specific invented reason is the inverse false-claim.
- Recovery copy is deterministic (no LLM call), composed from the grounded
  sources above plus a small number of fixed sentence frames (a frame is "我没能
  帮你完成 {intent}，{ask}" — not a reason-code lookup table).

**Never-silent guarantee.** For an interactive inbound turn, the only paths that
may end without a user reply are an intentional `no_reply` on a NON-state-changing
turn and a hard exception (already routed to the worker failure path + logging). A
`failed` disposition must no longer be such a path.

**`no_reply`-with-staged guard.** Both reviews noted `commit_no_reply`
(`runner.py:1313`, `service.py:258`) also materializes staged commands. An
intentional `no_reply` after the turn staged a state-changing command would
silently perform an action with no user-facing confirmation — a different silent
trust gap. Add an invariant: `no_reply` is rejected (routed to the recovery path)
when the turn has staged commands or state-changing tool events. (Lower priority
than the core recovery path; may ship as a follow-up, but specify and test it.)

**Architecture exception.** The runtime contract says the Interaction Agent is the
only normal user-prose producer, with waiting text as the sole typed runtime
exception (`docs/ARCHITECTURE.md:52`). This recovery reply is runtime-owned prose,
so it is a SECOND typed exception. The implementation change MUST document it in
`docs/ARCHITECTURE.md` in the same commit.

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
(`output_protocol.py:100-156`). The fix is at the agent-contract layer: make the
agent's shared-booking reply contract reliably emit a claim that matches the
staged/committed outcome (or no claim when it staged a create command for close
materialization), so a legitimate booking validates instead of failing closed.
Do NOT weaken the validator to pass — that would reopen the false-success hole
(`8ff8de1c`). If reproduction shows the failure is genuine model malformation
(not a contract mismatch), Component 1 is the correct and sufficient handling and
Component 2 reduces to prompt/contract hardening only.

### Component 3 — Coalesced-window answer completeness (DEFERRED)

**Component 1 resolves eva's actual path**: the failed seq-33 turn now sends a
grounded recovery AND closes its own window, so seq 33 is never re-included in
seq 34's turn and cannot be silently dropped by coalescing. This is the concrete
bug the operator reported.

The *general* residual — a **successful** turn whose window covers multiple
distinct messages but whose reply addresses only a subset — is **deferred**, not
designed here. Both code reviews proved the originally-proposed mechanism is
infeasible under the current data model: the runtime has a single monotonic
high-water mark `conversation.last_closed_inbound_seq` (`service.py:172`,
`_save_close_state` `service.py:550`). It cannot represent "seq 34 closed, seq 33
still open." `_recover_open_inbound_windows` (`__main__.py:146`) only requeues the
full open suffix where `latest > last_closed`, and `recover:{conversation}:{seq}`
trigger reuse collides with `start_turn`'s trigger_id idempotency
(`service.py:160`). A real fix needs a NEW per-message ack/close data model (sparse
close state), which is out of scope for this spec and tracked as a follow-up.

## Testing / Verification

- **Component 1 unit:** an interactive inbound turn whose agent output is invalid
  after retry takes the recovery path: a `recovery_text` is delivered, the
  disposition is `recovered` (not `replied`), `last_closed_inbound_seq` advances,
  staged commands stay unmaterialized (assert `status` not committed / no durable
  row, mirroring `test_turn_runner.py:1207`), and the copy contains no
  success/fabricated-cause claim. Assert **positive** non-completion wording
  ("couldn't / 没能 ... retry"), not merely the absence of banned success phrases.
  Cover all three grounding sources (staged intent, structured blocker,
  input-text floor) and the `serialized_tool_call_output` opaque case.
- **`no_reply`-with-staged guard unit:** a turn that returns `no_reply` after
  staging a state-changing command is routed to recovery (not silently
  materialized).
- **Eva-path regression:** a failed seq-33 turn closes its own window so a
  following seq-34 turn covers only seq 34 (seq 33 not coalesced/dropped).
- **Component 2:** the reproduction regression goes from red
  (`invalid_output_protocol`) to green (valid booking reply with a matching
  durable outcome), and the false-success regressions from
  `2026-06-07-shared-reminder-false-success.md` stay green.
- **Suite + routing:** `.venv/bin/python -m pytest tests/unit/coke -q`;
  `zsh scripts/suggest-verification --base HEAD~1`; `zsh scripts/review-trigger
  --base HEAD~1`.
- **Production confirmation (post-deploy):** re-run the eva shared-booking flow on
  the real account; confirm a grounded recovery reply is delivered (not silence)
  and no false-success row is created.

## Rollout / Risks

- Ship Component 1 first (keystone; removes the silent drop and fixes eva's
  coalescing path). Then Component 2 (reproduce → fix). Component 3 is deferred —
  it needs a new sparse per-message close model and is tracked as a follow-up.
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
- Component 3: resolved by both reviews — deferred; needs a new sparse
  per-message close data model (the single `last_closed_inbound_seq` high-water
  mark cannot express it). Tracked as a follow-up, not in this spec's scope.
