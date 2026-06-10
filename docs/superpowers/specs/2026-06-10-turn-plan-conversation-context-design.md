# Turn Plan Conversation Context — Design

Status: design-ready (2026-06-10). Scope: v2 interactive turn path
(`COKE_TURN_PIPELINE=v2`). Owner-decided sequencing: Pass 1 here; Pass 2
(structured resumable pending action) deferred behind a follow-up eval.

## Problem

The v2 planner (`SiliconFlowPlanner`) is context-blind. The runner builds the
planner's `conversation_history` from `_v2_conversation_history(start.input_messages)`
— i.e. ONLY the current turn's inbound messages. It never sees prior turns.

Observed production failure (olivers, 2026-06-10): "和eva约一个明天晚上八点的晚饭"
→ assistant "约不了，她那边有日程冲突了，要不换个时间？" → user "晚上七点半" →
assistant "晚上七点半，有什么安排吗?" (the follow-up was treated as a contextless
fragment; the eva-dinner reschedule intent was lost). The user had to fully restate.

Legacy (v1) avoided this with TWO mechanisms: (a) Agno `add_history_to_context=True`
injects the conversation's prior turns (keyed by `session_id=conversation_id`);
(b) `RecoverableSchedulingIntent` persists a blocked scheduling request's full
proposed action so a follow-up deterministically resumes it. v2 dropped both;
`PendingClarification` only covers ambiguous-candidate disambiguation.

## Evidence guiding the design

Feeding conversation history to the planner makes it ACT on the follow-up, but
GLM-5.1 (thinking-off) reconstruction is NON-DETERMINISTIC: across runs the same
"晚上七点半" + 2-message history yields `[]`, a generic `reminder.create`, or the
correct `social_scheduling.create_shared_reminder(participant=eva,…)`. So history
is necessary but not sufficient for blocked/partial-resume reliability. Hence the
two-pass plan.

## Pass 1 (this design): conversation history window into Plan

Give the planner (and, for free, Express) a bounded window of recent conversation
turns, and instruct it to resolve follow-ups against that window.

### Components

1. Runner builds a real window.
   - New `CokeTurnRunner._v2_conversation_window(conversation_id, current_turn_id,
     limit=8)`:
     - `self.conversation_runtime.recent_turns_with_messages(conversation_id, limit)`
       returns newest-first `(Turn, input_messages, outbound_messages)` tuples.
     - Reverse to chronological. SKIP the tuple whose `turn.id == current_turn_id`
       (the current message is already carried in `payload`).
     - For each remaining turn, in order: emit each input message as
       `{"role":"user","content":text,"seq":seq}` (skip blank text), then each
       outbound message as `{"role":"assistant","content":text}` (skip blank).
     - Cap to the most recent 20 messages.
     - On `ConversationRuntimeError`, fall back to
       `_v2_conversation_history(start.input_messages)`.
   - `_v2_pipeline_request` uses the window builder instead of
     `_v2_conversation_history(start.input_messages)`.

2. Planner prompt (`TURN_PLANNER_SYSTEM_PROMPT`) gains a follow-up rule:
   conversation_history is the prior turns of THIS conversation; the latest message
   may continue/answer/correct the most recent still-open request (a bare time, a
   friend name answering "who?", "改成X"/"换成Y", a new time after the assistant
   asked to reschedule). When so, RECONSTRUCT the prior request's full action (same
   domain+operation, carry forward ALL params: participant/friend, content/title…)
   and merge the new detail; never downgrade a shared/social request to a personal
   reminder, never treat a follow-up as converse.

3. Express needs no change — it already receives `conversation_history` from the
   request and now gets the window, improving contextual converse.

### Bounds / non-goals

- Window is bounded (≤8 turns, ≤20 messages) to avoid the context explosion the
  bounded-Express split was created to prevent.
- Pass 1 does NOT add deterministic resume; blocked/partial-resume reliability is
  measured by a follow-up eval and, if still flaky, addressed in Pass 2.

## Design review (2026-06-10): two-consultant synthesis + a key correction

Two independent Codex design passes (reliability lens + minimalism lens) plus code
inspection converged and corrected the original framing:

- **Unanimous:** history source = our own bounded window from the message store
  (`recent_turns_with_messages`), NOT Agno session history. Agno is the wrong
  boundary for a raw-JSON planner and its storage is noisy (prompts, tool events,
  raw `{"type":"reply",...}` segments).
- **Critical correction:** the planner currently receives NO conversation history at
  all. `_plan_request()` builds `PlanRequest` without `conversation_history`, and
  `SiliconFlowPlanner.plan()` omits it from the `complete_json` user payload — only
  Express gets it. The first true fix is wiring the window THROUGH to the planner
  payload (PlanRequest field + pipeline `_plan_request` + plan.py user dict).
- **Evidence caveat:** the earlier "reconstruction is non-deterministic" finding was
  CONFOUNDED — the planner never had the history; the apparent "eva reconstruction"
  was the model parroting an eva example baked into the test prompt. So whether
  window+prompt alone suffices is UNPROVEN and must be measured AFTER the wire is in.
- **Both consultants expect** a typed continuation hint (structured carry-forward of
  the immediately-prior request + the assistant's obligation, with a runtime merge
  that rejects domain/operation drift) may be needed for reliability. Reliability lens
  (A) persists it at close (`close.py`/`commit_reply`/message payload); minimalism
  lens (B) derives it non-persistently at request build. This hint is "Pass 2-lite".

**Decision (sequenced, evidence-gated):** First land the FOUNDATION — wire the bounded
window into the planner + the follow-up prompt rule (neutral, no leaking examples) —
then EMPIRICALLY re-test the eva reschedule (and simpler follow-ups) with the history
actually reaching the planner. If reconstruction is reliable, that is the complete
Pass 1. If it still flaps, add the typed continuation hint (preferring A's
persisted-at-close form) and note it crosses into the deferred structured-resume work.

## Pass 2 (deferred): structured resumable pending action

Generalize `PendingClarification` to persist the full proposed action (domain,
operation, resolved-so-far params) when a turn settles in needs_input(missing
param) / needs_confirmation / blocked(reschedule). The next turn detects a
follow-up and resumes deterministically, bypassing fuzzy reconstruction. Gated on
Pass 1's eval showing residual unreliability.

## Verification

- Unit: `_v2_conversation_window` builds chronological user/assistant history,
  excludes the current turn, caps length, falls back on error.
- Real-model in-container: reproduce the eva reschedule end-to-end (olivers) and a
  simpler follow-up ("提醒我跑步" then "明天早上七点") several times; confirm the
  follow-up is understood. Non-determinism here is the Pass-2 trigger signal.
