# Text Message Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore legacy-style human-like multi-message text replies in the current single-Agent runtime without changing ClawScale protocol shape.

**Architecture:** The Interaction Agent will be prompted to return a text-only `MultiModalResponses` JSON envelope. `agent_runtime.py` will parse that envelope into ordered `VisibleMessage(message_type="text", ...)` values, run existing user-visible guardrails against the joined parsed text, and keep capability summary fallback as one message. Existing `agent_handler.py`, `output_delivery.py`, and ClawScale push dispatch will continue to handle separate output documents and delayed timestamps.

**Tech Stack:** Python 3.12, Agno runtime, Pydantic dataclasses, pytest, Mongo-backed output documents, ClawScale bridge tests with mocks.

---

## File Structure

- Modify `agent/agno_agent/runtime/agent_runtime.py`
  - Add JSON parsing helper for text-only `MultiModalResponses`.
  - Convert model output into multiple `VisibleMessage` values.
  - Run unconfirmed durable-write guardrail on parsed visible text.
- Modify `agent/agno_agent/runtime/chat_response_instructions.py`
  - Add the active text-only visible-output contract.
  - Keep retired legacy schema wording stripped.
- Modify `tests/unit/agent/test_agent_runtime_output_rules.py`
  - Add parser, fallback, capping, non-text filtering, and guardrail tests.
- Modify `tests/unit/agent/test_chat_response_instructions.py`
  - Update prompt assertions for the new active JSON contract.
- Modify `tests/unit/agent/test_agent_handler.py`
  - Add a multi-visible-message send sequencing test.
- Modify `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`
  - Add a characterization test that async push dispatch sends separate pending output docs according to timestamps.
- Modify `tests/eval/test_real_model_native_toolcalling_smoke.py`
  - Add an opt-in real-model smoke for the text-only segmentation contract.
- Add `docs/superpowers/specs/2026-05-23-text-message-segmentation-design.md`
  - Keep the design spec with the implementation branch.

Do not reintroduce `agent/agno_agent/schemas/chat_response_schema.py`. The design spec explicitly states that schema was not an active runtime contract unless the implementation chose to enable Agno `output_schema`; this plan keeps enforcement in instructions plus parser helper.

---

### Task 1: Runtime Parser And Guardrail Semantics

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `tests/unit/agent/test_agent_runtime_output_rules.py`

- [ ] **Step 1: Add failing runtime output tests**

In `tests/unit/agent/test_agent_runtime_output_rules.py`, add `import json` after the existing imports:

```python
import json
from datetime import UTC, datetime
```

Append these tests after `test_rule3_no_tool_results_uses_final_text`:

```python
def _segments_payload(*segments: object) -> str:
    return json.dumps({"MultiModalResponses": list(segments)}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_multimodal_json_becomes_ordered_visible_text_segments(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload(
            {"type": "text", "content": "先这样"},
            {"type": "text", "content": "我晚点再提醒你整理下一步"},
        ),
    )

    assert [message.message_type for message in result.visible_messages] == [
        "text",
        "text",
    ]
    assert [message.content for message in result.visible_messages] == [
        "先这样",
        "我晚点再提醒你整理下一步",
    ]
    assert result.output_disposition.status == "ok"


@pytest.mark.asyncio
async def test_malformed_multimodal_json_falls_back_to_single_text(monkeypatch):
    raw = '{"MultiModalResponses": [{"type": "text", "content": "缺了括号"}'

    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": raw}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=raw,
    )

    assert [message.content for message in result.visible_messages] == [raw]


@pytest.mark.asyncio
async def test_multimodal_parser_ignores_non_text_and_caps_at_three(monkeypatch):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        content=_segments_payload(
            {"type": "voice", "content": "不要发语音"},
            {"type": "text", "content": "一"},
            {"type": "photo", "content": "不要发图片"},
            {"type": "text", "content": "二"},
            {"type": "text", "content": "三"},
            {"type": "text", "content": "四"},
        ),
    )

    assert [message.content for message in result.visible_messages] == ["一", "二", "三"]


@pytest.mark.asyncio
async def test_segmented_reminder_promise_guardrail_uses_joined_visible_text(
    monkeypatch,
):
    result = await _run_with_fake_agent(
        messages=[{"role": "assistant", "content": ""}],
        capability_results=[],
        monkeypatch=monkeypatch,
        input_text="明天九点提醒我喝水",
        content=_segments_payload(
            {"type": "text", "content": "没问题"},
            {"type": "text", "content": "明天早上九点我会提醒你喝水"},
        ),
    )

    assert result.visible_messages == ()
    assert result.output_disposition.status == "empty"
    assert result.error_disposition is not None
    assert result.error_disposition.code == "unconfirmed_durable_write_promise"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v
```

Expected: the newly added segmentation tests fail because current `run_agent_runtime()` returns one `VisibleMessage` containing the raw JSON string and checks reminder promises against the raw JSON envelope.

- [ ] **Step 3: Add parser helpers in `agent_runtime.py`**

In `agent/agno_agent/runtime/agent_runtime.py`, add `import json` with the imports:

```python
import json
```

Add this constant after `_DEFAULT_AGENT_RUNTIME_TIMEOUT_SECONDS`:

```python
_MAX_VISIBLE_TEXT_SEGMENTS = 3
```

Add these helper functions after `_string_content()`:

```python
def _parse_visible_text_segments(final_text: str) -> tuple[str, ...]:
    text = final_text.strip()
    if not text:
        return ()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return (text,)

    if not isinstance(payload, Mapping):
        return (text,)

    responses = payload.get("MultiModalResponses")
    if not isinstance(responses, list):
        return (text,)

    segments: list[str] = []
    for item in responses:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") != "text":
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        segments.append(content)
        if len(segments) >= _MAX_VISIBLE_TEXT_SEGMENTS:
            break
    return tuple(segments)


def _visible_text_for_guardrails(segments: Sequence[str]) -> str:
    return "\n".join(segment for segment in segments if segment)
```

- [ ] **Step 4: Replace single-message conversion in `run_agent_runtime()`**

In `run_agent_runtime()`, replace the block from `final_text = ...` through the creation of `visible_messages` with this logic:

```python
        final_text = _string_content(getattr(run_output, "content", None))
        model_visible_segments = (
            _parse_visible_text_segments(final_text) if final_text else ()
        )
        guardrail_text = _visible_text_for_guardrails(model_visible_segments)
        unconfirmed_promise_error = _check_unconfirmed_durable_write_promise(
            agent_input=agent_input,
            final_text=guardrail_text,
            capability_results=capability_results,
            domain_results=domain_results,
        )

        captured_capability_results = tuple(capability_results)
        captured_domain_results = tuple(domain_results)
        durable_write_error = _check_durable_write_contract(captured_capability_results)
        runtime_contract_error = durable_write_error or unconfirmed_promise_error

        summary_text = "" if final_text else _resolve_visible_text(
            "", captured_capability_results
        )
        if runtime_contract_error is not None:
            visible_messages = ()
        elif model_visible_segments:
            visible_messages = tuple(
                VisibleMessage(message_type="text", content=segment)
                for segment in model_visible_segments
            )
        elif summary_text:
            visible_messages = (
                VisibleMessage(message_type="text", content=summary_text),
            )
        else:
            visible_messages = ()
```

Leave the later `if visible_messages and runtime_contract_error is None:` return block unchanged except for any formatter-driven line wrapping.

- [ ] **Step 5: Run runtime output tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -v
```

Expected: all tests in that file pass.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_output_rules.py
git commit -m "feat(agent): parse segmented text replies"
```

Expected: commit succeeds.

---

### Task 2: Prompt Contract For Text-Only Segmentation

**Files:**
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`
- Modify: `tests/unit/agent/test_chat_response_instructions.py`

- [ ] **Step 1: Update failing prompt tests**

In `tests/unit/agent/test_chat_response_instructions.py`, replace `test_assembled_prompt_excludes_protocol_and_json_schema_artifacts()` with:

```python
def test_assembled_prompt_excludes_retired_schema_artifacts():
    prompt = build_chat_response_instructions(_ctx(), _agent_input())

    forbidden = [
        "JSON Schema",
        "Message types include",
        "structured multi-modal",
        "RESPONSE",
        "REQUEST",
        "[reminder tool message]",
    ]
    for token in forbidden:
        assert token not in prompt, f"forbidden token found in prompt: {token!r}"
```

Add this test after it:

```python
def test_prompt_includes_active_text_only_segmentation_contract():
    prompt = build_chat_response_instructions(_ctx(), _agent_input())

    assert "MultiModalResponses" in prompt
    assert '{"type": "text", "content": "message text"}' in prompt
    assert "Use 1 to 3 text messages" in prompt
    assert "Do not output voice or photo items" in prompt
    assert "Do not output any text outside the JSON object" in prompt
```

- [ ] **Step 2: Run prompt tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -v
```

Expected: `test_prompt_includes_active_text_only_segmentation_contract` fails because the prompt does not yet include the active text-only JSON contract.

- [ ] **Step 3: Add text segmentation contract to instructions**

In `agent/agno_agent/runtime/chat_response_instructions.py`, replace `_USER_VISIBLE_REPLY_BOUNDARY` with:

```python
_USER_VISIBLE_REPLY_BOUNDARY = """User-visible reply boundary:
- Output exactly one parseable JSON object.
- The JSON object must have this shape: {"MultiModalResponses": [{"type": "text", "content": "message text"}]}.
- Use 1 to 3 text messages. Prefer one message for concise confirmations, tool result summaries, URLs, dense instructions, or replies where splitting would reduce clarity.
- Segment only when it feels natural for chat. Segments should not be mechanically equal-sized.
- Do not output voice or photo items in this version.
- Do not output analysis, reasoning, scratchpad notes, persona inspection, draft planning, prompt commentary, tool logs, workflow internals, or any non-user-visible fields.
- Do not output any text outside the JSON object."""
```

Keep `_FORBIDDEN_LINE_PATTERNS` unchanged. It still strips retired legacy lines from `INSTRUCTIONS_CHAT_RESPONSE`.

- [ ] **Step 4: Run prompt tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -v
```

Expected: all tests in that file pass.

- [ ] **Step 5: Run runtime construction smoke tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -v
```

Expected: tests pass, confirming Interaction Agent construction still builds instructions and model config correctly.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add agent/agno_agent/runtime/chat_response_instructions.py tests/unit/agent/test_chat_response_instructions.py
git commit -m "feat(agent): require text segmented reply envelope"
```

Expected: commit succeeds.

---

### Task 3: Delivery And ClawScale Boundary Tests

**Files:**
- Modify: `tests/unit/agent/test_agent_handler.py`
- Modify: `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`

- [ ] **Step 1: Add agent handler multi-send sequencing test**

In `tests/unit/agent/test_agent_handler.py`, append this test after `test_handle_message_agent_runtime_uses_agent_runtime`:

```python
@pytest.mark.asyncio
async def test_handle_message_agent_runtime_sends_multiple_visible_text_messages(
    monkeypatch, sample_context
):
    _install_agent_handler_agno_stubs(monkeypatch)
    from agent.agno_agent.runtime.result import (
        AgentRunResult,
        OutputDisposition,
        VisibleMessage,
    )
    from agent.runner import agent_handler

    async def fake_run_agent_runtime(**kwargs):
        return AgentRunResult(
            visible_messages=[
                VisibleMessage(message_type="text", content="第一条"),
                VisibleMessage(message_type="text", content="第二条"),
            ],
            post_analyze_input=None,
            domain_results=[],
            capability_results=[],
            metrics={},
            trace={"runtime": "agent_runtime"},
            output_disposition=OutputDisposition(status="ok"),
        )

    sent = []

    def fake_send_single_message(**kwargs):
        sent.append(
            {
                "content": kwargs["multimodal_response"]["content"],
                "expect_output_timestamp": kwargs["expect_output_timestamp"],
                "is_first": kwargs["is_first"],
            }
        )
        next_timestamp = kwargs["expect_output_timestamp"] + 5
        return {"message": kwargs["multimodal_response"]["content"]}, next_timestamp

    monkeypatch.setattr(agent_handler.time, "time", lambda: 1710000000)
    monkeypatch.setattr(
        agent_handler, "_run_agent_runtime_event", fake_run_agent_runtime
    )
    monkeypatch.setattr(agent_handler, "_send_single_message", fake_send_single_message)

    resp_messages, context, is_rollback, is_content_blocked = (
        await agent_handler.handle_message(
            context=sample_context,
            input_message_str="你好",
            message_source="user",
            check_new_message=False,
            worker_tag="[T]",
            current_message_ids=[],
        )
    )

    assert resp_messages == [{"message": "第一条"}, {"message": "第二条"}]
    assert sent == [
        {
            "content": "第一条",
            "expect_output_timestamp": 1710000000,
            "is_first": True,
        },
        {
            "content": "第二条",
            "expect_output_timestamp": 1710000005,
            "is_first": False,
        },
    ]
    assert context["MultiModalResponses"] == [
        {"type": "text", "content": "第一条", "metadata": {}},
        {"type": "text", "content": "第二条", "metadata": {}},
    ]
    assert is_rollback is False
    assert is_content_blocked is False
```

- [ ] **Step 2: Add ClawScale push dispatcher characterization test**

In `tests/unit/connector/clawscale_bridge/test_output_dispatcher.py`, append this test after `test_output_dispatcher_claims_pending_message_before_sending_and_posts_to_gateway`:

```python
def test_output_dispatcher_sends_staggered_push_segments_separately(monkeypatch):
    import connector.clawscale_bridge.output_dispatcher as output_dispatcher

    clock = {"now": 1710000000}
    monkeypatch.setattr(output_dispatcher.time, "time", lambda: clock["now"])

    messages = [
        _build_message_doc(
            _id="out_1",
            message="第一条",
            expect_output_timestamp=1710000000,
            metadata={
                "business_conversation_key": "bc_1",
                "delivery_mode": "push",
                "idempotency_key": "idem_1",
                "trace_id": "trace_1",
                "output_id": "out_1",
            },
        ),
        _build_message_doc(
            _id="out_2",
            message="第二条",
            expect_output_timestamp=1710000005,
            metadata={
                "business_conversation_key": "bc_1",
                "delivery_mode": "push",
                "idempotency_key": "idem_2",
                "trace_id": "trace_2",
                "output_id": "out_2",
            },
        ),
    ]

    class FakeCollection:
        def find_one_and_update(self, query, update, return_document):
            assert query["expect_output_timestamp"] == {"$lte": clock["now"]}
            for message in messages:
                if message["status"] != "pending":
                    continue
                if message["expect_output_timestamp"] > clock["now"]:
                    continue
                message["status"] = update["$set"]["status"]
                message["dispatching_timestamp"] = update["$set"][
                    "dispatching_timestamp"
                ]
                return dict(message)
            return None

    mongo = MagicMock()
    mongo.get_collection.return_value = FakeCollection()

    def fake_finalize(collection_name, query, update):
        assert collection_name == "outputmessages"
        for message in messages:
            if message["_id"] == query["_id"]:
                message["status"] = update["$set"]["status"]
                message["handled_timestamp"] = update["$set"]["handled_timestamp"]
                return 1
        return 0

    mongo.update_one.side_effect = fake_finalize
    gateway_client = MagicMock()
    gateway_client.post_output.return_value.status_code = 200

    dispatcher = output_dispatcher.ClawScaleOutputDispatcher(
        mongo=mongo,
        gateway_client=gateway_client,
    )

    assert dispatcher.dispatch_once() is True
    assert gateway_client.post_output.call_args_list[0].kwargs["output_id"] == "out_1"
    assert dispatcher.dispatch_once() is False
    assert len(gateway_client.post_output.call_args_list) == 1

    clock["now"] = 1710000005
    assert dispatcher.dispatch_once() is True
    assert gateway_client.post_output.call_args_list[1].kwargs["output_id"] == "out_2"
    assert [message["status"] for message in messages] == ["handled", "handled"]
```

- [ ] **Step 3: Run the new delivery tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_handler.py::test_handle_message_agent_runtime_sends_multiple_visible_text_messages \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py::test_output_dispatcher_sends_staggered_push_segments_separately \
  -v
```

Expected: both tests pass. If the agent handler test fails because the current code does not preserve the timestamp returned by `_send_single_message`, fix `agent/runner/agent_handler.py` so it reuses the returned `expect_output_timestamp` for the next visible message.

- [ ] **Step 4: Run broader delivery boundary tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/runner/test_agent_handler_inflight_interrupt.py \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py \
  tests/unit/agent/test_message_util_clawscale_routing.py \
  tests/unit/connector/clawscale_bridge/test_reply_waiter.py \
  -v
```

Expected: tests pass, confirming multi-text output uses existing send sequencing, async push stays separate, and sync ClawScale remains collapsed into one reply string.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add tests/unit/agent/test_agent_handler.py tests/unit/connector/clawscale_bridge/test_output_dispatcher.py
git commit -m "test(bridge): cover segmented text delivery boundaries"
```

Expected: commit succeeds.

---

### Task 4: Real-Model Smoke And Final Verification

**Files:**
- Modify: `tests/eval/test_real_model_native_toolcalling_smoke.py`
- Add: `docs/superpowers/specs/2026-05-23-text-message-segmentation-design.md`
- Add: `docs/superpowers/plans/2026-05-23-text-message-segmentation.md`

- [ ] **Step 1: Add opt-in real-model segmentation smoke**

In `tests/eval/test_real_model_native_toolcalling_smoke.py`, append this test after `test_url_context_synthesis_real_model`:

```python
@pytest.mark.asyncio
async def test_text_segmentation_contract_real_model():
    result = await run_agent_runtime(
        agent_input=_input("我今天有点累，但还是想把明天的安排简单理一下"),
        run_context=_ctx(),
    )

    assert result.output_disposition.status == "ok"
    assert 1 <= len(result.visible_messages) <= 3
    assert all(message.message_type == "text" for message in result.visible_messages)
    visible = "\n".join(message.content for message in result.visible_messages)
    assert "MultiModalResponses" not in visible
    assert '"type"' not in visible
    assert "tool_use" not in visible
```

- [ ] **Step 2: Run non-real-model unit verification**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_output_rules.py \
  tests/unit/agent/test_chat_response_instructions.py \
  tests/unit/agent/test_agent_handler.py \
  tests/unit/runner/test_agent_handler_inflight_interrupt.py \
  tests/unit/agent/test_message_util_clawscale_routing.py \
  tests/unit/connector/clawscale_bridge/test_reply_waiter.py \
  tests/unit/connector/clawscale_bridge/test_output_dispatcher.py \
  -v
```

Expected: all selected unit tests pass.

- [ ] **Step 3: Run repo-OS checks**

Run:

```bash
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected:

- `scripts/check` passes.
- `suggest-verification` includes `worker-runtime` and `repo-os-docs`.
- `review-trigger` may require human review because docs/spec files changed; record the exact output.

- [ ] **Step 4: Run real-model smoke only when credentials are available**

If staging credentials and network access are configured, run:

```bash
AGENT_RUNTIME_REAL_MODEL_SMOKE=1 .venv/bin/python -m pytest \
  tests/eval/test_real_model_native_toolcalling_smoke.py::test_text_segmentation_contract_real_model \
  -v -s
```

Expected: the test passes and visible output is text-only. If credentials are not available, do not fake this evidence; record that the real-model smoke was not run.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add \
  tests/eval/test_real_model_native_toolcalling_smoke.py \
  docs/superpowers/specs/2026-05-23-text-message-segmentation-design.md \
  docs/superpowers/plans/2026-05-23-text-message-segmentation.md
git commit -m "test(agent): add segmented text smoke coverage"
```

Expected: commit succeeds.

---

## Final Review Checklist

- [ ] Runtime parser emits 1-3 text `VisibleMessage` values from `MultiModalResponses`.
- [ ] Malformed model output falls back to one text message.
- [ ] Valid JSON with only invalid/non-text items does not emit voice/photo output.
- [ ] Unconfirmed durable-write guardrail checks joined visible segment text.
- [ ] Capability visible summaries remain one visible text message.
- [ ] Prompt asks for text-only JSON envelope and does not revive retired JSON Schema wording.
- [ ] Agent handler sends multiple visible messages in order and carries forward returned `expect_output_timestamp`.
- [ ] ClawScale sync `request_response` behavior remains collapsed to one reply string.
- [ ] ClawScale async push dispatch can deliver staggered output docs separately.
- [ ] Unit verification and repo checks are recorded.
- [ ] Real-model smoke is either run with evidence or explicitly reported as not run.
