# Visible Output Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce `MultiModalResponses[*].content` as the only successful interaction-agent visible-output protocol for user turns and reminder fires.

**Architecture:** Keep the contract at the worker-runtime boundary in `agent/agno_agent/runtime/agent_runtime.py`. Replace raw-text/lenient parsing with strict envelope parsing, add one safe protocol-repair retry, and continue constructing `VisibleMessage` only from parsed envelope text. Reminder fires retry safely because they expose no tools; user turns retry only before any durable write has executed.

**Tech Stack:** Python 3, Agno `Agent`, dataclasses, pytest async tests, Coke worker-runtime trace/result contracts.

---

## File Structure

- `agent/agno_agent/runtime/agent_runtime.py` - owns strict envelope parsing, protocol-repair retry orchestration, durable-write retry safety, visible-message construction, and runtime trace/error disposition.
- `agent/agno_agent/runtime/chat_response_instructions.py` - owns prompt text that tells the interaction LLM to return only the structured envelope.
- `tests/unit/agent/test_agent_runtime_output_rules.py` - owns output-protocol regression tests for strict parsing, retries, fail-closed behavior, and guardrail interaction.
- `tests/unit/agent/test_agent_runtime_construction.py` - owns construction/input tests for `reminder.fired` and no-tool behavior.
- `tests/unit/runner/test_typed_runtime_events.py` - owns reminder event-handler behavior when typed runtime returns no visible output.
- `docs/superpowers/specs/2026-05-28-visible-output-protocol-design.md` - already patched before this plan; keep it synchronized if implementation changes the contract.

## Task 1: Strict Envelope Parser

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py`

- [ ] **Step 1: Add failing parser tests**

Append these tests near the existing multimodal output tests in `tests/unit/agent/test_agent_runtime_output_rules.py`:

```python
@pytest.mark.asyncio
async def test_raw_plain_text_triggers_output_protocol_retry(monkeypatch):
    outputs = [
        "ordinary chat",
        _segments_payload({"type": "text", "content": "repaired chat"}),
    ]
    calls = []

    class FakeAgent:
        async def arun(self, **kwargs):
            calls.append(kwargs["input"])
            return type("FakeOutput", (), {"content": outputs.pop(0), "messages": []})()

    monkeypatch.setattr(agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent())

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="hi",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )

    assert len(calls) == 2
    assert "previous response violated" in calls[1]
    assert [message.content for message in result.visible_messages] == ["repaired chat"]
    assert result.error_disposition is None


@pytest.mark.asyncio
async def test_malformed_envelope_json_is_protocol_violation_not_lenient_recovery(monkeypatch):
    raw = '{"MultiModalResponses": [{"type": "text", "content": "缺了括号"}'
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py::test_raw_plain_text_triggers_output_protocol_retry tests/unit/agent/test_agent_runtime_output_rules.py::test_malformed_envelope_json_is_protocol_violation_not_lenient_recovery -v
```

Expected: both tests fail because raw text is currently accepted and malformed envelopes are leniently recovered.

- [ ] **Step 3: Add strict parse result helpers**

In `agent/agno_agent/runtime/agent_runtime.py`, replace `_recover_lenient_envelope` usage and change parsing to return a typed parse result:

```python
@dataclass(frozen=True)
class _VisibleOutputParseResult:
    ok: bool
    segments: tuple[str, ...] = ()
    violation_reason: str | None = None


def _parse_visible_output_protocol(final_text: str) -> _VisibleOutputParseResult:
    if not final_text:
        return _VisibleOutputParseResult(False, violation_reason="empty_output")
    payload = _try_parse_envelope_json(final_text)
    if payload is None:
        return _VisibleOutputParseResult(False, violation_reason="not_parseable_json")
    if not isinstance(payload, Mapping):
        return _VisibleOutputParseResult(False, violation_reason="not_json_object")
    responses = payload.get("MultiModalResponses")
    if not isinstance(responses, Sequence) or isinstance(responses, (str, bytes, bytearray)):
        return _VisibleOutputParseResult(False, violation_reason="missing_multimodal_responses")
    segments: list[str] = []
    for item in responses:
        if not isinstance(item, Mapping) or item.get("type") != "text":
            continue
        content = _string_content(item.get("content"))
        if not content:
            continue
        for segment in _text_message_segments(content):
            segments.append(segment)
            if len(segments) >= _MAX_VISIBLE_TEXT_SEGMENTS:
                break
        if len(segments) >= _MAX_VISIBLE_TEXT_SEGMENTS:
            break
    if not segments:
        return _VisibleOutputParseResult(False, violation_reason="no_usable_text_content")
    return _VisibleOutputParseResult(True, tuple(segments))
```

Keep `_try_parse_envelope_json` fence stripping, but remove the call to `_recover_lenient_envelope`. Delete `_LENIENT_ENVELOPE_RE`, `_LENIENT_CONTENT_RE`, and `_recover_lenient_envelope`.

- [ ] **Step 4: Wire parser into runtime**

Replace the call to `_parse_visible_text_segments(final_text)` with `_parse_visible_output_protocol(final_text)` and initially set `final_text_segments = parse_result.segments if parse_result.ok else ()`. Add:

```python
def _output_protocol_violation(reason: str, *, attempted_retry: bool) -> RuntimeErrorDisposition:
    return RuntimeErrorDisposition(
        code="output_protocol_violation",
        retryable=not attempted_retry,
        metadata={"reason": reason, "attempted_retry": attempted_retry},
    )
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v
```

Expected: parser tests now pass; existing tests that expected raw text or lenient recovery may fail and must be updated in Task 2 because the contract changed.

- [ ] **Step 6: Commit Task 1**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_output_rules.py
git commit -m "feat: enforce strict visible output envelope parsing"
```

## Task 2: Protocol-Repair Retry And Durable-Write Safety

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`

- [ ] **Step 1: Add failing retry tests**

Add these tests to `tests/unit/agent/test_agent_runtime_output_rules.py`:

```python
@pytest.mark.asyncio
async def test_protocol_retry_failure_returns_no_visible_message(monkeypatch):
    calls = []

    class FakeAgent:
        async def arun(self, **kwargs):
            calls.append(kwargs["input"])
            return type("FakeOutput", (), {"content": "still raw", "messages": []})()

    monkeypatch.setattr(agent_runtime, "_create_interaction_agent", lambda **kwargs: FakeAgent())

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="hi",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )

    assert len(calls) == 2
    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"
    assert result.error_disposition.metadata["attempted_retry"] is True


@pytest.mark.asyncio
async def test_user_turn_protocol_violation_after_durable_write_does_not_retry(monkeypatch):
    write_result = DomainExecutionResult(
        domain="reminder",
        outcome="executed",
        operations=(
            DomainOperationResult(
                action="create",
                ok=True,
                effect="write",
                entity_type="reminder",
                entity_id="rem-1",
                facts={"visible_summary": "已创建提醒：喝水"},
            ),
        ),
    )
    calls = []

    class FakeAgent:
        async def arun(self, **kwargs):
            calls.append(kwargs["input"])
            return type("FakeOutput", (), {"content": "raw after write", "messages": []})()

    def fake_create(**kwargs):
        kwargs["domain_results"].append(write_result)
        return FakeAgent()

    monkeypatch.setattr(agent_runtime, "_create_interaction_agent", fake_create)

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv1",
            text="明天提醒我喝水",
            payload=UserTurnPayload(current_message_ids=["msg1"]),
            occurred_at=datetime.now(UTC),
        ),
        run_context=_ctx(),
    )

    assert len(calls) == 1
    assert result.visible_messages == ()
    assert result.error_disposition is not None
    assert result.error_disposition.code == "output_protocol_violation"
    assert result.error_disposition.metadata["durable_write_executed"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py::test_protocol_retry_failure_returns_no_visible_message tests/unit/agent/test_agent_runtime_output_rules.py::test_user_turn_protocol_violation_after_durable_write_does_not_retry -v
```

Expected: fail until retry orchestration and durable-write safety are implemented.

- [ ] **Step 3: Implement retry helpers**

Add helpers in `agent/agno_agent/runtime/agent_runtime.py` near output parsing helpers:

```python
def _protocol_repair_input(input_message: str, reason: str) -> str:
    return (
        f"{input_message}\n\n"
        "System protocol repair: the previous response violated the visible output "
        f"protocol ({reason}). Return only one JSON object with this shape: "
        '{"MultiModalResponses": [{"type": "text", "content": "message text"}]}. '
        "Do not include markdown fences or any text outside the JSON object."
    )


def _has_successful_durable_write(
    capability_results: Sequence[CapabilityResult],
    domain_results: Sequence[DomainExecutionResult],
) -> bool:
    if any(result.ok and result.durable_write for result in capability_results):
        return True
    return any(
        operation.ok and operation.effect == "write"
        for result in domain_results
        for operation in result.operations
    )
```

- [ ] **Step 4: Run one or two agent attempts**

Inside `run_agent_runtime`, replace the single `agent.arun(...)` block with an attempt helper that:

1. Creates the interaction agent.
2. Calls `agent.arun(input=input_message, session_id=run_context.conversation.id)`.
3. Extracts final text from `content` or latest assistant message.
4. Parses with `_parse_visible_output_protocol`.
5. If parse succeeds, continues with existing guardrail checks.
6. If parse fails and no durable write has run, creates a fresh interaction agent and retries once using `_protocol_repair_input(input_message, reason)`.
7. If parse fails after retry, or if a durable write already ran, returns no visible messages with `RuntimeErrorDisposition(code="output_protocol_violation")`.

Preserve the existing timeout behavior for each `agent.arun` call. Do not replay after a durable write.

- [ ] **Step 5: Update stale raw-text and lenient-recovery tests**

Update tests that currently expect raw text or malformed envelope recovery:

- `test_rule1_synthesis_with_nonempty_final_text_wins` should use `_segments_payload({"type": "text", "content": "synthesized reply"})`.
- `test_rule3_no_tool_results_uses_final_text` should use `_segments_payload({"type": "text", "content": "ordinary chat"})`.
- `test_non_envelope_invalid_json_still_falls_back_to_raw` should assert `output_protocol_violation`.
- `test_malformed_envelope_json_recovers_text_segments` and `test_malformed_multimodal_json_recovers_text_lenient` should assert `output_protocol_violation`, or be replaced by the Task 1 malformed-envelope test.
- `test_reminder_fired_input_passes_raw_input_to_model` in `tests/unit/agent/test_agent_runtime_construction.py` should return an envelope in `FakeAgent.arun`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_construction.py::test_reminder_fired_input_passes_raw_input_to_model -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_construction.py
git commit -m "feat: retry visible output protocol violations safely"
```

## Task 3: Guardrail And Reminder-Fire Integration

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py`
- Modify: `tests/unit/runner/test_typed_runtime_events.py`

- [ ] **Step 1: Add failing valid-internal-looking-content test**

Add this test to `tests/unit/agent/test_agent_runtime_output_rules.py`:

```python
@pytest.mark.asyncio
async def test_valid_envelope_content_that_looks_like_tool_markup_is_visible(monkeypatch):
    model_text = _segments_payload(
        {
            "type": "text",
            "content": '<minimax:tool_call><invoke name="noop"></invoke></minimax:tool_call>',
        }
    )

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": model_text}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=model_text,
    )

    assert [message.content for message in result.visible_messages] == [
        '<minimax:tool_call><invoke name="noop"></invoke></minimax:tool_call>'
    ]
    assert result.error_disposition is None
```

- [ ] **Step 2: Update serialized-tool-call test**

Rename `test_reminder_fire_serialized_tool_call_fails_closed` to
`test_reminder_fire_raw_serialized_tool_call_protocol_violation` and change its
expected error code from `serialized_tool_call_output` to
`output_protocol_violation`.

- [ ] **Step 3: Remove serialized-tool-call visible-content guard**

In `agent/agno_agent/runtime/agent_runtime.py`, stop calling
`_check_serialized_tool_call_output` after `VisibleMessage.content` has been
parsed from a valid envelope. Delete `_SERIALIZED_TOOL_CALL_OUTPUT_RE` and
`_check_serialized_tool_call_output` unless no other caller remains.

- [ ] **Step 4: Add typed reminder no-output assertion**

Extend `tests/unit/runner/test_typed_runtime_events.py` with:

```python
@pytest.mark.asyncio
async def test_reminder_event_handler_typed_runtime_no_output_fails_without_template():
    from agent.runner.reminder_event_handler import ReminderFireEventHandler

    async def runtime_event_handler(**_kwargs):
        return AgentRunResult(
            visible_messages=[],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="empty"),
        )

    output_writer = Mock(return_value={"_id": "out-1"})
    handler = ReminderFireEventHandler(
        conversation_dao=Mock(get_conversation_by_id=Mock(return_value={"_id": "conv-1", "talkers": [{"db_user_id": "user-1"}, {"db_user_id": "char-1"}]})),
        user_dao=Mock(get_user_by_id=Mock(side_effect=[{"_id": "user-1"}, {"_id": "char-1"}])),
        lock_manager=Mock(acquire_lock_async=AsyncMock(return_value="lock-1"), release_lock_safe_async=AsyncMock(return_value=(True, "released"))),
        context_builder=Mock(return_value={"conversation": {"_id": "conv-1"}}),
        output_writer=output_writer,
        existing_output_lookup=Mock(return_value=None),
        runtime_event_handler=runtime_event_handler,
    )

    result = await handler.handle(_event())

    assert result.ok is False
    assert result.error_code == "OutputUnavailable"
    output_writer.assert_not_called()
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/runner/test_typed_runtime_events.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/runner/test_typed_runtime_events.py
git commit -m "feat: trust valid visible envelope content"
```

## Task 4: Prompt Contract And Final Verification

**Files:**
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `docs/superpowers/specs/2026-05-28-visible-output-protocol-design.md` only if implementation forced a contract adjustment

- [ ] **Step 1: Add prompt-contract tests**

Add or extend construction tests so the built instructions include:

```python
assert "Output exactly one parseable JSON object" in instructions
assert "MultiModalResponses" in instructions
assert "Do not output any text outside the JSON object" in instructions
```

For a `reminder.fired` input, also assert:

```python
assert "system reminder delivery" in instructions
assert "do not create, update, cancel, or list reminders" in instructions
```

- [ ] **Step 2: Patch prompt text only if tests expose a missing contract**

If any assertion fails, update `_USER_VISIBLE_REPLY_BOUNDARY` or the
`ReminderFirePayload` branch in `_trusted_environment_block` in
`agent/agno_agent/runtime/chat_response_instructions.py`. Do not add examples
or special-case wording beyond the protocol and reminder-fire contract.

- [ ] **Step 3: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: worker-runtime or repo-OS suggestions. Treat `review-trigger` as a non-blocking risk report.

- [ ] **Step 4: Run worker-runtime tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/runner/test_typed_runtime_events.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Run structure check**

Run:

```bash
zsh scripts/check
```

Expected: pass. If it fails because of unrelated pre-existing state, capture the exact failure and do not mask it.

- [ ] **Step 6: Commit Task 4**

```bash
git add agent/agno_agent/runtime/chat_response_instructions.py tests/unit/agent/test_agent_runtime_construction.py docs/superpowers/specs/2026-05-28-visible-output-protocol-design.md
git commit -m "test: verify visible output prompt contract"
```

## Self-Review Notes

- Spec coverage: The tasks cover strict envelope parsing, retry once when safe, no retry after durable writes, no visible output after retry failure, no tool exposure for reminder fires, typed-runtime reminder fail-closed behavior, valid internal-looking envelope content, and prompt contract checks.
- Placeholder scan: No `TBD`, broad "handle edge cases", or unspecified test commands remain.
- Type consistency: New helpers use existing `CapabilityResult`, `DomainExecutionResult`, `RuntimeErrorDisposition`, `OutputDisposition`, and `VisibleMessage` contracts.
