# Streaming First Segment For Chat Turns Implementation Plan

> **For agentic workers:** Implement task-by-task with TDD. Steps use checkbox (`- [ ]`) syntax.

**Goal:** For pure chat turns the user must see the first complete reply segment within single-digit seconds instead of waiting for the entire ~14s Interaction Agent generation, by streaming the first safe segment as soon as it is complete.

**Architecture:** The Interaction Agent gains a streaming invoke that yields complete reply segments as they finish generating. The runner delivers the first segment early **only for full-agent chat turns that have no staged command and make no state-change claim**, then continues to full validation and close as today. This boundary makes "no fake success before materialization" automatically true, because in-scope turns never mutate state.

**Tech Stack:** Python, Agno agent streaming, pytest, `coke/turn/runner.py`, `coke/llm/agno_interaction_agent.py`, the outbound delivery port.

Source spec: `docs/superpowers/specs/2026-06-09-agent-flow-time-optimization-design.md`.

---

## Scope And Boundaries (do not violate)

- **Only stream for `full_agent` chat turns.** Concretely: stream only when the turn has NO staged command, NO domain mutation tool was/will be used, and the route is not a prepared action and not a reminder-fire/notification/social-scheduling turn. If in doubt, do NOT stream — fall back to the current deliver-at-close behavior.
- **Never stream a state-change success claim.** The in-scope boundary already guarantees this; additionally, if any streamed segment would contain a success/confirmation claim, suppress streaming for that turn.
- **Supersede stops the stream.** If a newer inbound cancels the turn (`CancelledError` / `is_newer_inbound_cancellation`), no further segments may be delivered and no segment from superseded work may be sent. Reuse the existing cancellation handling.
- **The close path is unchanged for correctness.** Streaming is an *additional early delivery* of segments that the final validated output also contains. Final validation, disposition, and the input-window close still run exactly as today. Do not let a streamed segment bypass `_validate_agent_output`.
- **No double-send.** Track which segments were already delivered by the stream so the close-time delivery does not resend them.
- Do not revive `StreamingChatWorkflow` code. Build the streaming inside the current agent/runner contract.

## File Structure

- Modify `coke/llm/agno_interaction_agent.py` — add a streaming variant (e.g. `ainvoke_streaming`) that yields complete `segment` strings as they finish, plus the final `AgentResult` at the end. Use Agno's token/stream API; incrementally assemble complete segments from the JSON `segments` array (a segment is complete when its closing quote/element boundary is parsed). If streaming under JSON mode proves unreliable, fall back to non-streaming for that call and log it — never emit a partial or malformed segment.
- Modify `coke/turn/runner.py` — in the async interactive path, when the turn is in scope for streaming, consume the streaming invoke, deliver the first complete safe segment via the outbound delivery port immediately, then finish validation/close. Add telemetry for first-segment latency.
- Add a streaming-eligibility predicate `is_streaming_eligible(trigger, semantic_decision, tool_profile) -> bool` (new pure function, e.g. in `coke/turn/routing.py` or a small `coke/turn/streaming.py`).
- Modify `coke/observability/turn_latency.py` — add `"first_segment_ms"` and `"streamed"` to `SAFE_EXTRA_FIELDS`.

## Task 1: Streaming-eligibility predicate

**Files:** Create/extend `coke/turn/streaming.py`; Test `tests/unit/coke/turn/test_streaming_eligibility.py`.

- [ ] Step 1: Write failing tests: a plain chit-chat decision (`intent_family="chit_chat"`, no staged command, render-not-required) → eligible; a reminder create decision → not eligible; a reminder-fire trigger → not eligible; a NotificationTurn/RENDER mode → not eligible; a social-scheduling intent → not eligible.
- [ ] Step 2: Run, expect failure.
- [ ] Step 3: Implement `is_streaming_eligible` returning True only for INTERACTIVE mode, route `full_agent`, intent families that are conversational (`chit_chat` and other non-mutating families), and where the tool profile contains no mutation tool the agent is expected to call. Default False.
- [ ] Step 4: Run, expect PASS.
- [ ] Step 5: Commit.

## Task 2: Streaming invoke on the agent

**Files:** Modify `coke/llm/agno_interaction_agent.py`; Test `tests/unit/coke/llm/test_agno_streaming.py`.

- [ ] Step 1: Write a failing test using a fake/stubbed Agno model stream that yields tokens forming `{"type":"reply","segments":["Hello there.","How can I help?"]}`. Assert `ainvoke_streaming(request)` yields `"Hello there."` before `"How can I help?"`, and finally returns an `AgentResult` whose `output` equals the full parsed reply and whose `tool_events` are present.
- [ ] Step 2: Run, expect failure.
- [ ] Step 3: Implement `ainvoke_streaming`: drive the model in streaming mode, incrementally parse the `segments` array, `yield` each segment string the moment it is complete, and return the final `AgentResult` identical to what `ainvoke` would produce. If the model/stream API cannot deliver complete segments safely, fall back internally to `ainvoke` and yield nothing before returning the final result.
- [ ] Step 4: Run, expect PASS. Also run existing `agno_interaction_agent` tests; expect no regression.
- [ ] Step 5: Commit.

## Task 3: Early-delivery wiring in the runner

**Files:** Modify `coke/turn/runner.py`, `coke/observability/turn_latency.py`; Test `tests/unit/coke/turn/test_runner_streaming.py`.

- [ ] Step 1: Add `"first_segment_ms"` and `"streamed"` to `SAFE_EXTRA_FIELDS`.
- [ ] Step 2: Write a failing async runner test: an eligible chat turn delivers the first segment via the outbound delivery port BEFORE the turn completes, the final close still records the full validated reply, and the already-streamed segment is not delivered twice. Assert telemetry includes `streamed=True` and a `first_segment_ms` value.
- [ ] Step 3: In the async interactive path, when `is_streaming_eligible(...)`, replace the `agent.primary` block with a streaming consumption: as the first complete segment arrives, call the outbound delivery port to send it and record `first_segment_ms`; collect remaining segments; after the stream returns the final `AgentResult`, run the SAME `_validate_agent_output` and close logic as today, but skip re-delivering already-streamed segments. Keep the non-eligible path byte-for-byte as today.
- [ ] Step 4: Run the new test and the full `tests/unit/coke` suite; expect PASS.
- [ ] Step 5: Commit.

## Task 4: Supersede / cancellation safety

**Files:** Test `tests/unit/coke/turn/test_runner_streaming.py` (extend).

- [ ] Step 1: Write a test: when a newer inbound cancels mid-stream, no further segments are delivered and the turn records as superseded/interrupted (reuse existing cancellation test patterns). Also test: if the final validated output differs from a streamed segment (e.g. validation forces a correction), the close path must not contradict an already-sent segment — in that case streaming must have been suppressed; assert suppression for any turn whose validation can rewrite first-answer content.
- [ ] Step 2: Run; fix wiring so streamed delivery happens inside the same cancellation scope and only after the first segment passes the first-answer validation that the close path would apply.
- [ ] Step 3: Run the suite; expect PASS.
- [ ] Step 4: Commit.

## Verification (run before handoff)

- [ ] `.venv/bin/python -m pytest tests/unit/coke -q` — all pass.
- [ ] `zsh scripts/suggest-verification --base origin/main` then run the suggested surface command.
- [ ] `black . && isort .`; confirm no stray formatting churn.
- [ ] Record a before/after note: for an eligible chat turn, first-segment delivery time vs total turn time (unit-level timing is enough at this stage).

## Self-Review Checklist (do before declaring done)

- Non-eligible turns are unchanged (no streaming for reminder/create/fire/notification/social/prepared turns).
- No streamed segment can contain an unmaterialized success claim (guaranteed by the no-mutation scope).
- No double-delivery of streamed segments at close.
- Cancellation stops the stream; superseded work delivers nothing.
- Final validation and disposition are unchanged.
