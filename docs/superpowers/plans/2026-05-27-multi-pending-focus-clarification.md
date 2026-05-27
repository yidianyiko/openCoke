# Multi-Pending Focus Clarification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an invitee has two or more pending product-action invites and replies with a generic accept/reject utterance, the agent runtime must enumerate the candidates by their delivery times and ask the user to pick one, instead of returning the existing generic "我没法可靠判断你要同意还是拒绝" reply.

**Architecture:**

- Carry `delivered_at` into the agent runtime focus model so that two pending invites with byte-identical `summary_for_llm` are still distinguishable to the user.
- Split the existing focused-semantic fail-closed result into two branches: single-candidate (unchanged wording, `safety_boundary="semantic_focus_ambiguous"`) and multi-candidate (`safety_boundary="semantic_focus_multi_pending"`, visible summary enumerates each candidate by delivery time and summary, `required_questions` asks which invite the user means).
- No keyword / regex routing is added. The semantic interpreter prompt and the gateway shared-reminder service are not changed in this plan.

**Tech Stack:**

- Python 3.12, pydantic v2 for `FocusChannel` / `PendingAction`
- Existing agent runtime (`agent/agno_agent/runtime/agent_runtime.py`, `focus.py`, `domain_results.py`)
- pytest for unit tests
- Project workflow: `zsh scripts/suggest-verification` + `zsh scripts/review-trigger` + production smoke per `docs/issues/2026-05-27-real-user-happy-path-matrix.md`

## File Structure

- Modify: `agent/agno_agent/runtime/focus.py` — add `delivered_at` field to `PendingAction`, populate it from `product_notification` candidate entries.
- Modify: `agent/agno_agent/runtime/agent_runtime.py` — split `_focused_semantic_failure_result` into single-candidate and multi-candidate branches; introduce `_multi_pending_clarification_result` helper that lists each candidate.
- Modify: `tests/unit/agent/test_agent_runtime_construction.py` — keep the single-candidate ambiguous test as-is; add a multi-candidate ambiguous test that asserts the new `semantic_focus_multi_pending` contract.
- Modify: `docs/issues/2026-05-27-shared-reminder-multi-pending-accept-fail-closed.md` — flip `status: open` → `status: resolved` after production verification, append the verification result.
- Modify: `docs/issues/2026-05-27-real-user-happy-path-matrix.md` — add a new row for multi-pending accept clarification once production smoke passes.

---

## Task 1: Carry delivered_at into the focus PendingAction

**Files:**
- Modify: `agent/agno_agent/runtime/focus.py:12-23` (`PendingAction` model)
- Modify: `agent/agno_agent/runtime/focus.py:81-122` (`_action_input_from_product_notification`, `_pending_action_from_mapping`)
- Test: `tests/unit/agent/test_agent_runtime_construction.py` (new test alongside existing focus tests)

- [ ] **Step 1: Write failing test for delivered_at carried into PendingAction**

Add this test to `tests/unit/agent/test_agent_runtime_construction.py`, right before the existing
`test_run_agent_runtime_fails_closed_when_focused_semantic_intent_is_ambiguous`:

```python
def test_focus_from_multi_pending_notification_carries_delivered_at():
    from agent.agno_agent.runtime.focus import focus_from_product_notification

    product_notification = {
        "ambiguity": "multi_pending",
        "candidates": [
            {
                "request_id": "rid_1",
                "request_type": "shared_reminder_request",
                "delivered_at": "2026-05-27T14:07:38.968Z",
                "allowed_actions": ["accept", "reject"],
                "summary_for_llm": "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00。",
            },
            {
                "request_id": "rid_2",
                "request_type": "shared_reminder_request",
                "delivered_at": "2026-05-27T13:40:37.376Z",
                "allowed_actions": ["accept", "reject"],
                "summary_for_llm": "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00。",
            },
        ],
    }
    focus = focus_from_product_notification(
        product_notification,
        current_time=datetime(2026, 5, 27, 14, 8, tzinfo=UTC),
    )
    assert focus.ambiguity == "multi_pending"
    assert focus.current is None
    assert [c.action_id for c in focus.candidates] == ["rid_1", "rid_2"]
    assert [c.delivered_at for c in focus.candidates] == [
        datetime(2026, 5, 27, 14, 7, 38, 968000, tzinfo=UTC),
        datetime(2026, 5, 27, 13, 40, 37, 376000, tzinfo=UTC),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_focus_from_multi_pending_notification_carries_delivered_at -v`
Expected: FAIL with `AttributeError: 'PendingAction' object has no attribute 'delivered_at'` or similar.

- [ ] **Step 3: Add delivered_at to PendingAction and populate it from product_notification**

In `agent/agno_agent/runtime/focus.py`, change the `PendingAction` model and the two factory helpers:

```python
class PendingAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_id: str
    kind: str
    allowed_actions: tuple[str, ...]
    status: str
    expires_at: datetime | None = None
    delivered_at: datetime | None = None
    summary_for_llm: str
```

In `_action_input_from_product_notification`, add `"delivered_at": product_notification.get("delivered_at")` to the returned dict, immediately after `"expires_at"`.

In `_pending_action_from_mapping`, read `delivered_at = _parse_datetime(value.get("delivered_at"))` after the existing `expires_at` line and pass it into the returned `PendingAction(..., delivered_at=delivered_at, ...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_focus_from_multi_pending_notification_carries_delivered_at -v`
Expected: PASS.

- [ ] **Step 5: Run the wider focus and agent-runtime test files to confirm no regression**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py -q`
Expected: PASS (existing tests untouched).

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/focus.py tests/unit/agent/test_agent_runtime_construction.py
git commit -m "$(cat <<'EOF'
feat(focus): carry delivered_at on PendingAction

Multi-pending focus candidates share an identical summary_for_llm when the
gateway bundles duplicate shared-reminder invites. Carry the per-candidate
delivered_at into PendingAction so the agent runtime can later show a
distinguishable list to the user.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Split focused-semantic failure into single vs multi-candidate branches

**Files:**
- Modify: `agent/agno_agent/runtime/agent_runtime.py:615-658` (`_focused_semantic_failure_result`)
- Modify: `agent/agno_agent/runtime/agent_runtime.py:661-669` (`_should_fail_closed_focused_semantic`, no logic change but reused)
- Test: `tests/unit/agent/test_agent_runtime_construction.py` (new test; existing single-candidate test stays)

- [ ] **Step 1: Write failing test for multi_pending fail-closed contract**

Add this test to `tests/unit/agent/test_agent_runtime_construction.py`, immediately after
`test_run_agent_runtime_fails_closed_when_focused_semantic_intent_is_ambiguous`:

```python
@pytest.mark.asyncio
async def test_run_agent_runtime_fails_closed_with_enumeration_for_multi_pending_focus(
    monkeypatch,
):
    async def fake_interpret_semantic_intent(**_kwargs):
        return agent_runtime.SemanticIntentResult(
            intent="ambiguous",
            confidence="low",
            clarification_reason="multi candidate focus",
        )

    class UnexpectedAgent:
        async def arun(self, **_kwargs):
            raise AssertionError(
                "interaction agent should not handle multi_pending focus"
            )

    monkeypatch.setattr(
        agent_runtime, "interpret_semantic_intent", fake_interpret_semantic_intent
    )
    monkeypatch.setattr(
        agent_runtime,
        "_create_interaction_agent",
        lambda **kwargs: UnexpectedAgent(),
    )

    result = await agent_runtime.run_agent_runtime(
        agent_input=AgentInput(
            input_type="user.turn",
            conversation_id="conv-1",
            text="我同意",
            payload=UserTurnPayload(
                current_message_ids=["msg-1"],
                metadata={
                    "product_notification": {
                        "ambiguity": "multi_pending",
                        "candidates": [
                            {
                                "request_id": "rid_1",
                                "request_type": "shared_reminder_request",
                                "delivered_at": "2026-05-27T14:07:38.968Z",
                                "allowed_actions": ["accept", "reject"],
                                "summary_for_llm": (
                                    "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00。"
                                ),
                            },
                            {
                                "request_id": "rid_2",
                                "request_type": "shared_reminder_request",
                                "delivered_at": "2026-05-27T13:40:37.376Z",
                                "allowed_actions": ["accept", "reject"],
                                "summary_for_llm": (
                                    "李梓豪邀请你参加「数学课」，时间2026-05-28 20:00。"
                                ),
                            },
                        ],
                    }
                },
            ),
            occurred_at=datetime(2026, 5, 27, 14, 8, tzinfo=UTC),
        ),
        run_context=_run_context(),
    )

    domain_result = result.domain_results[0]
    assert domain_result.safety_boundary == "semantic_focus_multi_pending"
    assert domain_result.reply_contract.intent == "ask_clarification"
    assert domain_result.reply_contract.required_questions == (
        "你要对哪一条邀请操作？",
    )
    fact_paths = [
        requirement.path for requirement in domain_result.reply_contract.required_facts
    ]
    assert "candidates[0].delivered_at" in fact_paths
    assert "candidates[0].summary_for_llm" in fact_paths
    assert "candidates[1].delivered_at" in fact_paths
    assert "candidates[1].summary_for_llm" in fact_paths

    visible = result.visible_messages[0].content
    assert "rid_1" not in visible  # request_id is not user-facing
    assert "14:07" in visible
    assert "13:40" in visible
    assert "数学课" in visible
    assert "同意还是拒绝" not in visible  # not the single-candidate wording
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_fails_closed_with_enumeration_for_multi_pending_focus -v`
Expected: FAIL because `safety_boundary` is currently `semantic_focus_ambiguous` and `visible_messages[0].content` is the existing generic line.

- [ ] **Step 3: Implement the multi-candidate branch in agent_runtime**

Replace the existing `_focused_semantic_failure_result` body in `agent/agno_agent/runtime/agent_runtime.py:615-658` with a dispatch that picks a branch based on `getattr(focus, "ambiguity", None)`. Single-candidate branch keeps the existing summary and contract; multi-candidate branch produces the enumerated reply.

```python
def _focused_semantic_failure_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
) -> DomainExecutionResult:
    if getattr(focus, "ambiguity", None) == "multi_pending":
        return _multi_pending_clarification_result(focus, semantic_result)
    return _single_candidate_focus_failure_result(focus, semantic_result)


def _single_candidate_focus_failure_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
) -> DomainExecutionResult:
    action = _focus_current_action(focus)
    action_id = str(_focus_action_value(action, "action_id") or "")
    kind = str(_focus_action_value(action, "kind") or "product_action")
    summary = "我没法可靠判断你要同意还是拒绝这条请求，请再明确回复同意或拒绝。"
    error = DomainError(
        code="semantic_focus_ambiguous",
        message=semantic_result.clarification_reason or summary,
        retryable=True,
        detail={
            "semantic_intent": semantic_result.intent,
            "semantic_confidence": semantic_result.confidence,
            "action_id": action_id,
            "kind": kind,
        },
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="classify_product_action_reply",
                ok=False,
                effect="none",
                entity_type=kind,
                entity_id=action_id or None,
                facts={"visible_summary": summary},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary="semantic_focus_ambiguous",
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=(),
            required_questions=("同意还是拒绝这条请求？",),
            prohibited_claims=("friend_request_accepted", "shared_reminder_accepted"),
            allow_rephrase=True,
        ),
        error=error,
    )


def _multi_pending_clarification_result(
    focus: Any,
    semantic_result: SemanticIntentResult,
) -> DomainExecutionResult:
    candidates = tuple(getattr(focus, "candidates", ()) or ())
    lines = ["你有多条等你确认的邀请，请选一条："]
    facts: list[ReplyFactRequirement] = []
    for index, candidate in enumerate(candidates):
        delivered_at = getattr(candidate, "delivered_at", None)
        summary = getattr(candidate, "summary_for_llm", "") or ""
        delivered_label = _format_delivered_at_for_user(delivered_at)
        lines.append(f"{index + 1}. {delivered_label} {summary}".rstrip())
        facts.append(
            ReplyFactRequirement(path=f"candidates[{index}].delivered_at")
        )
        facts.append(
            ReplyFactRequirement(path=f"candidates[{index}].summary_for_llm")
        )
    summary_text = "\n".join(lines)
    error = DomainError(
        code="semantic_focus_multi_pending",
        message=semantic_result.clarification_reason or summary_text,
        retryable=True,
        detail={
            "semantic_intent": semantic_result.intent,
            "semantic_confidence": semantic_result.confidence,
            "candidate_count": len(candidates),
        },
    )
    return DomainExecutionResult(
        domain="scheduling",
        outcome="failed",
        operations=(
            DomainOperationResult(
                action="classify_product_action_reply",
                ok=False,
                effect="none",
                entity_type="product_action",
                entity_id=None,
                facts={"visible_summary": summary_text},
                error=error,
            ),
        ),
        missing_fields=(),
        safety_boundary="semantic_focus_multi_pending",
        reply_contract=ReplyContract(
            intent="ask_clarification",
            required_facts=tuple(facts),
            required_questions=("你要对哪一条邀请操作？",),
            prohibited_claims=(
                "friend_request_accepted",
                "shared_reminder_accepted",
            ),
            allow_rephrase=True,
        ),
        error=error,
    )


def _format_delivered_at_for_user(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    local = value.astimezone() if value.tzinfo else value
    return local.strftime("%H:%M")
```

Also add `ReplyFactRequirement` and `datetime` to the existing imports at the top of `agent_runtime.py` if they are not already imported.

- [ ] **Step 4: Run the new test plus the existing single-candidate ambiguous test**

Run:
```
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_fails_closed_with_enumeration_for_multi_pending_focus \
  tests/unit/agent/test_agent_runtime_construction.py::test_run_agent_runtime_fails_closed_when_focused_semantic_intent_is_ambiguous \
  -v
```
Expected: both PASS. The single-candidate test still sees `safety_boundary == "semantic_focus_ambiguous"` and the original summary text.

- [ ] **Step 5: Run the full agent unit suites that touch this path**

Run:
```
.venv/bin/python -m pytest \
  tests/unit/agent/test_agent_runtime_construction.py \
  tests/unit/agent/test_agent_runtime_output_rules.py \
  tests/unit/agent/test_agent_runtime_scheduling_tools.py \
  tests/unit/agent/test_execution_agents.py \
  -q
```
Expected: PASS. If any unrelated test starts failing, stop and re-read the diff before continuing.

- [ ] **Step 6: Commit**

```bash
git add agent/agno_agent/runtime/agent_runtime.py tests/unit/agent/test_agent_runtime_construction.py
git commit -m "$(cat <<'EOF'
feat(runtime): enumerate candidates on multi_pending focus

When focus.ambiguity is multi_pending the existing fail-closed reply asks the
user to repeat accept/reject, which is the wrong clarification: the missing
signal is which of the bundled invites is meant. Split the focused-semantic
failure path so multi_pending enumerates each candidate by delivery time and
summary and asks the user to pick one, while the single-candidate ambiguous
case keeps its original wording and safety boundary.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Local diff-aware verification

**Files:** none. Pure verification, output captured under `artifacts/evidence/`.

- [ ] **Step 1: Run the diff-aware verification suggestion**

Run: `zsh scripts/suggest-verification --base HEAD~2`
Expected: a printed `zsh scripts/verify-surface ...` command. Save the printed command into `artifacts/evidence/2026-05-27-multi-pending-focus-clarification/suggest-verification.txt`.

- [ ] **Step 2: Run the suggested surface verification**

Run the exact command from Step 1. Tee its output into `artifacts/evidence/2026-05-27-multi-pending-focus-clarification/verify-surface.txt`. Expected: PASS.

- [ ] **Step 3: Run the review-trigger risk report (non-blocking)**

Run: `zsh scripts/review-trigger --base HEAD~2` and tee into
`artifacts/evidence/2026-05-27-multi-pending-focus-clarification/review-trigger.txt`. This must not block; it is informational only.

- [ ] **Step 4: Commit the evidence**

```bash
git add artifacts/evidence/2026-05-27-multi-pending-focus-clarification
git commit -m "chore: add evidence for multi-pending focus clarification"
```

---

## Task 4: Production deploy and real-user smoke

**Files:**
- Modify: `docs/issues/2026-05-27-shared-reminder-multi-pending-accept-fail-closed.md` — append `## Verification Result` and flip `status: open` → `status: resolved`.
- Modify: `docs/issues/2026-05-27-real-user-happy-path-matrix.md` — add a `Shared reminder multi-pending clarification` row.

- [ ] **Step 1: Deploy**

Run: `./scripts/deploy-compose-to-gcp.sh --restart`
Expected: deploy script reports gateway-submodule match, runs compose up, and all `--restart` post-checks pass.

- [ ] **Step 2: Confirm both existing pending invites are still in place**

Run:
```
ssh gcp-coke 'docker compose -f /home/whoami/coke/docker-compose.prod.yml exec -T postgres psql -U clawscale -d clawscale -c "select id, requester_account_id, invitee_account_id, title, fire_at, status from shared_reminder_requests where invitee_account_id = '"'"'ck_SXk_J0U0V5JKcK09QHEuo'"'"' and status = '"'"'pending_invitee_confirmation'"'"' order by created_at desc;"'
```
Expected: both `cmpo527yn…` and `cmpo43gom…` still `pending_invitee_confirmation`. If they were cleaned up, instruct 李梓豪 to recreate two near-duplicate invites via the production bridge before continuing.

- [ ] **Step 3: Drive a real user-path "我同意" through the bridge**

Have `olivers` reply with "我同意" (or any generic accept) via the live channel that triggers `/bridge/inbound`. Capture the inbound id and the visible outbound from `db.outputmessages`.

Run:
```
ssh gcp-coke 'docker compose -f /home/whoami/coke/docker-compose.prod.yml exec -T mongo mongosh --quiet mymongo --eval "print(JSON.stringify(db.outputmessages.find({to_user:\"ck_SXk_J0U0V5JKcK09QHEuo\"}).sort({input_timestamp:-1}).limit(1).toArray(), null, 2))"'
```
Expected: visible message enumerates two invites by their delivery times (`14:07` and `13:40`), references "数学课" once per row, and asks "你要对哪一条邀请操作？".

- [ ] **Step 4: Have olivers pick one invite explicitly and verify the accept completes durably**

Have `olivers` reply with a disambiguating utterance such as `"接受14点07分那条"`. Expected: one of the two pending requests moves to `accepted` and the requester receives a `shared_reminder_accepted` product notification; the other request stays `pending_invitee_confirmation`. Capture the postgres state to evidence.

If the runtime still cannot disambiguate even with an explicit reference, treat that as a *separate* issue (semantic interpreter scope, not this plan) and record it without forcing this plan green.

- [ ] **Step 5: Record evidence and close the local issue**

Append a `## Verification Result` block to
`docs/issues/2026-05-27-shared-reminder-multi-pending-accept-fail-closed.md` with:

- Local unit run output snippet
- `suggest-verification` + `verify-surface` evidence paths
- Production deploy timestamp
- Production outbound message text (full)
- Postgres state before and after Step 4

Flip the frontmatter `status: open` → `status: resolved` and `updated_at` to the current date.

Add a new row to `docs/issues/2026-05-27-real-user-happy-path-matrix.md`:

```
| Shared reminder multi-pending clarification | <marker> | production bridge, agent runtime | passed-production | Multi-pending focus listed both invites with delivery times; explicit pick by time completed durable accept. |
```

- [ ] **Step 6: Commit**

```bash
git add docs/issues/2026-05-27-shared-reminder-multi-pending-accept-fail-closed.md docs/issues/2026-05-27-real-user-happy-path-matrix.md
git commit -m "docs(issues): resolve multi-pending focus clarification with production verification"
```

---

## Out-of-Plan Follow-Up

After this plan is shipped and verified, file a new gateway issue:
`docs/issues/2026-05-XX-shared-reminder-create-dedup.md`, asking whether
`create_shared_reminder` should treat
`(requester_account_id, invitee_account_id, title, fire_at, timezone, duration_minutes)`
as an idempotency target when a `pending_invitee_confirmation` row already
exists, so the duplicate-invite case stops being produced in the first place.
Do not bundle that work here.
