# Pre-Reply Input Coalescing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the architecture contract where a same-conversation inbound message arriving before the first close decision interrupts the active interactive turn and reprocesses the full ordered input window.

**Architecture:** ConversationRuntime owns input-window boundaries, close freshness, and staged command materialization. Agno remains the agent execution substrate through async `Agent.arun(...)`; Coke uses durable freshness plus local task cancellation to interrupt pre-close work. The worker acknowledges inbound wake-up events quickly, supervises interactive turns per conversation, and recovers open windows from Postgres.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, Postgres, Redis Streams, Agno 2.5.9, pytest.

---

## Sources

- Canonical architecture: `docs/ARCHITECTURE.md`, section "Interactive Input Windows And Pre-Reply Interruption"
- Design spec: `docs/superpowers/specs/2026-05-31-coke-pre-reply-interrupt-coalescing-design.md`
- Current implementation seams:
  - `coke/domains/conversation_runtime/service.py`
  - `coke/domains/conversation_runtime/models.py`
  - `coke/domains/conversation_runtime/repository.py`
  - `coke/turn/runner.py`
  - `coke/turn/freshness.py`
  - `coke/turn/agent.py`
  - `coke/llm/agno_interaction_agent.py`
  - `coke/worker/__main__.py`

## Scope Check

This plan touches multiple files, but it is one runtime feature: durable input-window interruption. Splitting it into separate independent plans would leave intermediate states where the schema, worker, Agno adapter, or tool mutation contract disagree. The tasks below are ordered so every commit has a testable behavior and preserves the architecture contract.

## File Structure

- Modify `docs/ARCHITECTURE.md`: already updated before this plan; keep it as the canonical runtime contract.
- Modify `docs/superpowers/specs/2026-05-31-coke-pre-reply-interrupt-coalescing-design.md`: already aligned to `docs/ARCHITECTURE.md`; keep spec wording in sync during implementation.
- Create `migrations/versions/20260531_0001_pre_reply_input_windows.py`: schema migration for input windows and staged commands.
- Modify `coke/schema.py`: declarative schema for the new migration shape.
- Modify `coke/domains/conversation_runtime/models.py`: add window, current-input, and staged-command dataclasses.
- Modify `coke/domains/conversation_runtime/repository.py`: add in-memory and Postgres repository methods for input-window messages, active turns, and staged commands.
- Modify `coke/domains/conversation_runtime/service.py`: implement window claim, close compare-and-set, supersede, and staged-command close materialization.
- Modify `coke/turn/freshness.py`: replace single `based_on_inbound_seq` freshness with window freshness and staged command helpers.
- Modify `coke/turn/context.py`: carry current input messages in the turn context.
- Modify `coke/turn/agent.py`: add async agent protocol and current-input fields.
- Modify `coke/turn/runner.py`: read the current input window, use async interactive execution, and close through ConversationRuntime.
- Modify `coke/llm/config.py` and `coke/config.py`: add interaction model timeout configuration.
- Modify `coke/llm/agno_interaction_agent.py`: implement `ainvoke(...)`, deterministic Agno `run_id`, and cancellation.
- Modify `coke/composition.py`: wire async agent, staged command materializers, and runtime factories.
- Create `coke/turn/staged_commands.py`: materialize staged commands at close using domain services.
- Create `coke/worker/interactive_supervisor.py`: per-conversation active task registry and cancellation supervisor.
- Modify `coke/worker/__main__.py`: route inbound events through the supervisor while render turns stay synchronous.
- Modify tests under `tests/unit/coke/conversation_runtime/`, `tests/unit/coke/turn/`, `tests/unit/coke/llm/`, `tests/unit/coke/worker/`, and `tests/integration/coke/`.

## Task 1: Schema, Models, And Migration

**Files:**
- Create: `migrations/versions/20260531_0001_pre_reply_input_windows.py`
- Modify: `coke/schema.py`
- Modify: `coke/domains/conversation_runtime/models.py`
- Modify: `tests/unit/coke/conversation_runtime/test_schema_contract.py`
- Modify: `tests/unit/coke/test_clean_schema_contract.py`

- [ ] **Step 1: Write failing schema contract tests**

Add this assertion block to `tests/unit/coke/conversation_runtime/test_schema_contract.py`:

```python
def test_conversation_runtime_schema_tracks_input_windows_and_staged_commands():
    from coke.schema import metadata

    conversation = metadata.tables["conversation"]
    turn = metadata.tables["turn"]
    staged_command = metadata.tables["staged_command"]

    assert "latest_inbound_seq" in conversation.c
    assert "last_closed_inbound_seq" in conversation.c
    assert "input_from_seq" in turn.c
    assert "input_to_seq" in turn.c
    assert "superseded_by_inbound_seq" in turn.c
    assert "based_on_inbound_seq" not in turn.c
    assert {
        "turn_id",
        "domain",
        "operation",
        "idempotency_key",
        "command_payload",
        "preview_facts",
        "status",
        "materialized_at",
    }.issubset(set(staged_command.c.keys()))
    assert _unique_columns(staged_command, "uq_staged_command_idempotency") == (
        "idempotency_key",
    )
```

Update the table column inventory in `tests/unit/coke/test_clean_schema_contract.py` so the expected `conversation`, `turn`, and new `staged_command` entries match the new schema.

- [ ] **Step 2: Run schema tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_schema_contract.py::test_conversation_runtime_schema_tracks_input_windows_and_staged_commands tests/unit/coke/test_clean_schema_contract.py -q
```

Expected: FAIL because `last_closed_inbound_seq`, turn window columns, and `staged_command` do not exist yet.

- [ ] **Step 3: Update `coke/schema.py`**

Change the conversation and turn tables, and add `staged_command`:

```python
conversation = Table(
    "conversation",
    metadata,
    _id_column(),
    Column("account_id", UUID(as_uuid=False), ForeignKey("account.id"), nullable=False),
    Column("latest_inbound_seq", BigInteger(), nullable=False),
    Column("last_closed_inbound_seq", BigInteger(), nullable=False),
    _created_at(),
    _updated_at(),
    UniqueConstraint("account_id", name="uq_conversation_account"),
    CheckConstraint(
        "last_closed_inbound_seq >= 0 and latest_inbound_seq >= last_closed_inbound_seq",
        name="ck_conversation_input_window_order",
    ),
)

turn = Table(
    "turn",
    metadata,
    _id_column(),
    Column("conversation_id", UUID(as_uuid=False), ForeignKey("conversation.id"), nullable=False),
    Column("trigger_id", String(255), nullable=False),
    Column("trigger_type", String(64), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("input_from_seq", BigInteger(), nullable=True),
    Column("input_to_seq", BigInteger(), nullable=True),
    Column("superseded_by_inbound_seq", BigInteger(), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("trigger_id", name="uq_turn_trigger_id"),
    CheckConstraint(
        "(input_from_seq is null and input_to_seq is null) or "
        "(input_from_seq is not null and input_to_seq is not null and input_from_seq <= input_to_seq)",
        name="ck_turn_input_window_order",
    ),
)

staged_command = Table(
    "staged_command",
    metadata,
    _id_column(),
    Column("turn_id", UUID(as_uuid=False), ForeignKey("turn.id"), nullable=False),
    Column("domain", String(64), nullable=False),
    Column("operation", String(128), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("command_payload", JSONB(), nullable=False),
    Column("preview_facts", JSONB(), nullable=False),
    Column("status", String(32), nullable=False),
    Column("materialized_at", DateTime(timezone=True), nullable=True),
    _created_at(),
    _updated_at(),
    UniqueConstraint("idempotency_key", name="uq_staged_command_idempotency"),
    CheckConstraint(
        "status in ('staged', 'materialized', 'superseded')",
        name="ck_staged_command_status",
    ),
)
```

- [ ] **Step 4: Create the Alembic migration**

Create `migrations/versions/20260531_0001_pre_reply_input_windows.py`:

```python
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260531_0001"
down_revision = "20260529_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation",
        sa.Column(
            "last_closed_inbound_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_conversation_input_window_order",
        "conversation",
        "last_closed_inbound_seq >= 0 and latest_inbound_seq >= last_closed_inbound_seq",
    )
    op.add_column("turn", sa.Column("input_from_seq", sa.BigInteger(), nullable=True))
    op.add_column("turn", sa.Column("input_to_seq", sa.BigInteger(), nullable=True))
    op.add_column(
        "turn",
        sa.Column("superseded_by_inbound_seq", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "update turn set input_from_seq = based_on_inbound_seq, "
        "input_to_seq = based_on_inbound_seq "
        "where based_on_inbound_seq is not null"
    )
    op.drop_column("turn", "based_on_inbound_seq")
    op.create_check_constraint(
        "ck_turn_input_window_order",
        "turn",
        "(input_from_seq is null and input_to_seq is null) or "
        "(input_from_seq is not null and input_to_seq is not null and input_from_seq <= input_to_seq)",
    )
    op.create_table(
        "staged_command",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("command_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preview_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_staged_command"),
        sa.ForeignKeyConstraint(["turn_id"], ["turn.id"], name="fk_staged_command_turn_id_turn"),
        sa.UniqueConstraint("idempotency_key", name="uq_staged_command_idempotency"),
        sa.CheckConstraint(
            "status in ('staged', 'materialized', 'superseded')",
            name=op.f("ck_staged_command_status"),
        ),
    )


def downgrade() -> None:
    op.drop_table("staged_command")
    op.drop_constraint("ck_turn_input_window_order", "turn", type_="check")
    op.add_column("turn", sa.Column("based_on_inbound_seq", sa.BigInteger(), nullable=True))
    op.execute("update turn set based_on_inbound_seq = input_to_seq")
    op.drop_column("turn", "superseded_by_inbound_seq")
    op.drop_column("turn", "input_to_seq")
    op.drop_column("turn", "input_from_seq")
    op.drop_constraint("ck_conversation_input_window_order", "conversation", type_="check")
    op.drop_column("conversation", "last_closed_inbound_seq")
```

- [ ] **Step 5: Update conversation runtime dataclasses**

In `coke/domains/conversation_runtime/models.py`, change `Conversation` and `Turn`, and add these dataclasses:

```python
@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    account_id: str
    latest_inbound_seq: int
    last_closed_inbound_seq: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Turn:
    id: str
    conversation_id: str
    trigger_id: str
    trigger_type: str
    mode: str
    input_from_seq: int | None
    input_to_seq: int | None
    superseded_by_inbound_seq: int | None
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentInputMessage:
    message_id: str
    seq: int
    text: str | None
    payload: Mapping[str, Any]
    causal_inbound_event_id: str | None


@dataclass(frozen=True, slots=True)
class StagedCommand:
    id: str
    turn_id: str
    domain: str
    operation: str
    idempotency_key: str
    command_payload: Mapping[str, Any]
    preview_facts: Mapping[str, Any]
    status: Literal["staged", "materialized", "superseded"]
    materialized_at: datetime | None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 6: Run schema tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_schema_contract.py tests/unit/coke/test_clean_schema_contract.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add coke/schema.py coke/domains/conversation_runtime/models.py migrations/versions/20260531_0001_pre_reply_input_windows.py tests/unit/coke/conversation_runtime/test_schema_contract.py tests/unit/coke/test_clean_schema_contract.py
git commit -m "feat: add input-window schema"
```

## Task 2: ConversationRuntime Window Claim And Close

**Files:**
- Modify: `coke/domains/conversation_runtime/repository.py`
- Modify: `coke/domains/conversation_runtime/service.py`
- Modify: `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`
- Modify: `tests/integration/coke/repositories/test_conversation_runtime_repository_contract.py`

- [ ] **Step 1: Write failing service tests**

Add tests to `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py`:

```python
def test_interactive_turn_claims_open_input_window(service):
    first = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="first",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    result = service.start_turn(
        conversation_id=first.conversation.id,
        trigger_id="inbound:provider:message-2",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    assert result.turn.input_from_seq == 1
    assert result.turn.input_to_seq == 2
    assert [message.text for message in result.input_messages] == ["first", "second"]


def test_close_advances_last_closed_inbound_seq(service, repository):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="hello",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )

    service.commit_reply(turn_id=turn.turn.id, segments=["hello"])

    saved = repository.get_conversation(inbound.conversation.id)
    assert saved is not None
    assert saved.last_closed_inbound_seq == 1


def test_newer_inbound_before_close_supersedes_old_turn_without_closing(service, repository):
    inbound = service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-1",
        text="old",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )
    turn = service.start_turn(
        conversation_id=inbound.conversation.id,
        trigger_id="inbound:provider:message-1",
        trigger_type="InboundTurn",
        mode="interactive",
    )
    service.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="new",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    with pytest.raises(ConversationRuntimeError, match="turn_superseded"):
        service.commit_reply(turn_id=turn.turn.id, segments=["stale"])

    saved = repository.get_conversation(inbound.conversation.id)
    assert saved is not None
    assert saved.last_closed_inbound_seq == 0
    superseded = service.get_disposition(turn.turn.id)
    assert superseded.disposition == "superseded"
    assert superseded.reason_code == "newer_inbound_seq"
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py -q
```

Expected: FAIL because `TurnStartResult.input_messages`, `last_closed_inbound_seq`, and window close checks do not exist yet.

- [ ] **Step 3: Add repository APIs**

Extend `ConversationRuntimeRepository`:

```python
def inbound_messages_for_window(
    self, conversation_id: str, input_from_seq: int, input_to_seq: int
) -> list[Message]:
    raise NotImplementedError

def active_interactive_turns(self, conversation_id: str) -> list[Turn]:
    raise NotImplementedError

def save_staged_command(self, command: StagedCommand) -> StagedCommand:
    raise NotImplementedError

def staged_commands_for_turn(self, turn_id: str) -> list[StagedCommand]:
    raise NotImplementedError

def save_conversation_and_turn(
    self, conversation: Conversation, turn: Turn
) -> None:
    raise NotImplementedError
```

Implement `inbound_messages_for_window(...)` in memory with:

```python
messages = [
    message
    for message in self.messages_by_id.values()
    if (
        message.conversation_id == conversation_id
        and message.direction == "inbound"
        and message.seq is not None
        and input_from_seq <= message.seq <= input_to_seq
    )
]
messages.sort(key=lambda message: (message.seq or 0, message.id))
return messages
```

Implement the Postgres method with:

```python
rows = many(
    self.session.execute(
        sa.select(schema.message)
        .where(
            schema.message.c.conversation_id == db_id(conversation_id),
            schema.message.c.direction == "inbound",
            schema.message.c.seq >= input_from_seq,
            schema.message.c.seq <= input_to_seq,
        )
        .order_by(schema.message.c.seq.asc(), schema.message.c.id.asc())
    )
)
return [_message(row) for row in rows]
```

- [ ] **Step 4: Update `TurnStartResult`**

Change the dataclass in `coke/domains/conversation_runtime/models.py`:

```python
@dataclass(frozen=True, slots=True)
class TurnStartResult:
    turn: Turn
    replayed: bool
    input_messages: tuple[CurrentInputMessage, ...] = ()
```

- [ ] **Step 5: Update `ConversationRuntimeService.start_turn(...)`**

For `mode == "interactive"`, compute the open window from the conversation:

```python
input_from_seq = conversation.last_closed_inbound_seq + 1
input_to_seq = conversation.latest_inbound_seq
if input_to_seq < input_from_seq:
    raise ConversationRuntimeError("no_open_inbound_window")
messages = self.repository.inbound_messages_for_window(
    conversation_id,
    input_from_seq,
    input_to_seq,
)
turn = Turn(
    id=self._id_factory("turn"),
    conversation_id=conversation_id,
    trigger_id=trigger_id,
    trigger_type=trigger_type,
    mode=mode,
    input_from_seq=input_from_seq,
    input_to_seq=input_to_seq,
    superseded_by_inbound_seq=None,
    started_at=now,
    completed_at=None,
    created_at=now,
    updated_at=now,
)
```

For render turns, set `input_from_seq=None`, `input_to_seq=None`, and `input_messages=()`.

- [ ] **Step 6: Replace freshness checks**

Replace `_ensure_fresh(turn, based_on_inbound_seq)` with:

```python
def _ensure_turn_can_close(self, turn: Turn) -> Conversation:
    conversation = self._require_conversation(turn.conversation_id)
    if turn.input_from_seq is None or turn.input_to_seq is None:
        return conversation
    if conversation.last_closed_inbound_seq != turn.input_from_seq - 1:
        self._record_superseded(turn, "window_already_closed")
        raise ConversationRuntimeError("turn_superseded")
    if conversation.latest_inbound_seq != turn.input_to_seq:
        self._record_superseded(turn, "newer_inbound_seq")
        raise ConversationRuntimeError("turn_superseded")
    return conversation
```

Change `commit_reply`, `commit_no_reply`, `mark_pending_async_reply`, and `guard_state_change` callers so they no longer pass `based_on_inbound_seq`.

- [ ] **Step 7: Advance the close boundary atomically**

In successful `commit_reply`, `commit_no_reply`, and `mark_pending_async_reply`, save the conversation with:

```python
if turn.input_to_seq is not None:
    conversation = replace(
        conversation,
        last_closed_inbound_seq=turn.input_to_seq,
        updated_at=now,
    )
    self.repository.save_conversation(conversation)
```

Do this in the same repository/session transaction as disposition and outbound persistence.

- [ ] **Step 8: Run service and repository tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/integration/coke/repositories/test_conversation_runtime_repository_contract.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add coke/domains/conversation_runtime/models.py coke/domains/conversation_runtime/repository.py coke/domains/conversation_runtime/service.py tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py tests/integration/coke/repositories/test_conversation_runtime_repository_contract.py
git commit -m "feat: claim and close input windows"
```

## Task 3: Current Input Window In TurnRunner And Prompt

**Files:**
- Modify: `coke/turn/context.py`
- Modify: `coke/turn/freshness.py`
- Modify: `coke/turn/agent.py`
- Modify: `coke/turn/runner.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [ ] **Step 1: Write failing prompt and runner tests**

Add to `tests/unit/coke/turn/test_turn_runner.py`:

```python
def test_inbound_turn_sends_ordered_input_window_to_agent(harness):
    harness.runtime.record_inbound(
        account_id="account_1",
        channel_identity_id="channel_identity_1",
        causal_inbound_event_id="provider:message-2",
        text="second",
        payload={"provider": "whatsapp_evolution"},
        traceparent=TRACEPARENT,
    )

    result = harness.runner.run_inbound_turn(harness.trigger)

    assert result.disposition == "replied"
    request = harness.agent.requests[0]
    assert [message.seq for message in request.current_input_messages] == [1, 2]
    assert [message.text for message in request.current_input_messages] == [
        "hello",
        "second",
    ]
```

Add to `tests/unit/coke/llm/test_interaction_agent.py`:

```python
def test_current_input_block_renders_ordered_inbound_window():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    agent = AgnoInteractionAgent(model=object(), agent_factory=FakeAgentFactory(fake_agent))

    agent.invoke(
        _request(
            memory_enabled=True,
            current_input_messages=(
                {"seq": 1, "text": "first", "message_id": "message_1"},
                {"seq": 2, "text": "actually second", "message_id": "message_2"},
            ),
        )
    )

    input_text = fake_agent.calls[0]["input"]
    assert "kind: user_message_window" in input_text
    assert "seq: 1" in input_text
    assert "text: first" in input_text
    assert "seq: 2" in input_text
    assert "text: actually second" in input_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_inbound_turn_sends_ordered_input_window_to_agent tests/unit/coke/llm/test_interaction_agent.py::test_current_input_block_renders_ordered_inbound_window -q
```

Expected: FAIL because `AgentRequest.current_input_messages` does not exist and the prompt renders only one message.

- [ ] **Step 3: Add current input to `AgentRequest`**

In `coke/turn/agent.py`:

```python
@dataclass(frozen=True, slots=True)
class AgentRequest:
    turn_id: str
    conversation_id: str
    account_id: str
    mode: TurnMode
    trigger_type: str
    payload: Mapping[str, Any]
    trusted_facts: Mapping[str, Any]
    tool_profile: ToolProfile
    freshness_guard: Any
    context: Any
    current_input_messages: tuple[Any, ...] = ()
    run_id: str | None = None
```

- [ ] **Step 4: Pass input messages through `TurnRunner`**

In `run_inbound_turn`, keep `start.input_messages` and pass it to the agent request:

```python
context = self.context_assembler.build(
    trigger=trigger,
    trusted_facts=trusted_facts,
    semantic_decision=semantic_decision,
    focus_subject=focus_subject,
    reference_resolution=self.reference_resolver.resolve_all([]),
    memory_context=self.memory_manager.load(
        account_id=trigger.account_id,
        conversation_id=trigger.conversation_id,
        long_term_enabled=bool(gate.trust_facts.get("memory_enabled", True)),
    ),
    freshness_guard=freshness_guard,
    tool_profile=tool_profile,
    onboarding_guidance_required=gate.activation_guidance_required,
    turn_source=trusted_facts["turn_source"],
)
return self._invoke_agent_and_record(
    trigger,
    context,
    semantic_decision,
    current_input_messages=start.input_messages,
)
```

Update `_invoke_agent_and_record(...)` to set:

```python
agent_request = AgentRequest(
    turn_id=context.freshness_guard.turn_id,
    conversation_id=trigger.conversation_id,
    account_id=trigger.account_id,
    mode=trigger.mode,
    trigger_type=trigger.trigger_type,
    payload=trigger.payload,
    trusted_facts=context.trusted_facts,
    tool_profile=context.tool_profile,
    freshness_guard=context.freshness_guard,
    context=context,
    current_input_messages=tuple(current_input_messages),
    run_id=context.freshness_guard.turn_id,
)
```

- [ ] **Step 5: Update `FreshnessGuard`**

In `coke/turn/freshness.py`, replace the old field with:

```python
@dataclass(frozen=True, slots=True)
class FreshnessGuard:
    conversation_runtime: Any
    turn_id: str
    input_from_seq: int | None
    input_to_seq: int | None

    def guard_state_change(self) -> None:
        self.conversation_runtime.guard_state_change(self.turn_id)

    def stage_command(
        self,
        *,
        domain: str,
        operation: str,
        command_payload: Mapping[str, Any],
        preview_facts: Mapping[str, Any],
        item_index: int,
    ):
        return self.conversation_runtime.stage_command(
            turn_id=self.turn_id,
            domain=domain,
            operation=operation,
            command_payload=command_payload,
            preview_facts=preview_facts,
            item_index=item_index,
        )
```

- [ ] **Step 6: Render the input window in Agno prompt**

Change `_current_input_block(...)`:

```python
def _current_input_block(request: AgentRequest) -> str:
    if request.trigger_type == "InboundTurn":
        lines = [
            "kind: user_message_window",
            "instruction: These are adjacent user messages in the current open input window. Answer the combined intent in sequence order.",
        ]
        for message in request.current_input_messages:
            lines.extend(
                [
                    "---",
                    f"seq: {getattr(message, 'seq', None) or message.get('seq')}",
                    f"text: {_input_message_text(message)}",
                ]
            )
        return "\n".join(lines)
    return _render_trigger_input_block(request)
```

Implement `_input_message_text(...)` without changing render-turn prompt behavior:

```python
def _render_trigger_input_block(request: AgentRequest) -> str:
    return "\n".join(
        [
            "kind: trusted_turn_fact",
            f"trigger_type: {request.trigger_type}",
            f"payload: {json.dumps(dict(request.payload), ensure_ascii=False, sort_keys=True)}",
            "instruction: Render the trusted turn fact according to its source.",
        ]
    )


def _input_message_text(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("text") or "")
    return str(getattr(message, "text", "") or "")
```

- [ ] **Step 7: Run turn and LLM tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add coke/turn/context.py coke/turn/freshness.py coke/turn/agent.py coke/turn/runner.py coke/llm/agno_interaction_agent.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m "feat: render current input windows"
```

## Task 4: Staged Interactive Commands

**Files:**
- Create: `coke/turn/staged_commands.py`
- Modify: `coke/composition.py`
- Modify: `coke/domains/conversation_runtime/service.py`
- Modify: `tests/unit/coke/turn/test_turn_runner.py`
- Modify: `tests/unit/coke/reminder/test_reminder_service.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`

- [ ] **Step 1: Write failing staged-command tests**

Add to `tests/unit/coke/turn/test_turn_runner.py`:

```python
def test_superseded_interactive_turn_leaves_no_active_reminder(harness):
    harness.trigger.payload["execute_reminder_tool"] = True

    def new_inbound_before_agent_returns():
        harness.runtime.record_inbound(
            account_id="account_1",
            channel_identity_id="channel_identity_1",
            causal_inbound_event_id="provider:message-2",
            text="actually make it 10",
            payload={"provider": "whatsapp_evolution"},
            traceparent=TRACEPARENT,
        )

    harness.agent.before_tool = new_inbound_before_agent_returns

    result = harness.runner.run_inbound_turn(harness.trigger)

    assert result.disposition == "superseded"
    assert harness.reminder_repository.list_reminders("account_1") == []
```

Add to `tests/unit/coke/test_social_scheduling_tool_adapter.py`:

```python
def test_interactive_shared_reminder_tool_stages_before_close():
    guard = FakeStagingGuard(turn_id="turn_1", input_from_seq=1, input_to_seq=1)
    service = FakeSocialSchedulingService()
    adapter = SocialSchedulingToolAdapter(service)

    result = adapter.execute(
        {
            "operation": "create_shared_reminder",
            "creator_account_id": "account_1",
            "receiver_account_ids": ["account_2"],
            "title": "Dinner",
            "captured_timezone": "UTC",
        },
        guard,
    )

    assert result.ok is True
    assert result.facts["status"] == "staged"
    assert service.calls == []
    assert guard.staged[0]["domain"] == "social_scheduling"
    assert guard.staged[0]["operation"] == "create_shared_reminder"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_superseded_interactive_turn_leaves_no_active_reminder tests/unit/coke/test_social_scheduling_tool_adapter.py::test_interactive_shared_reminder_tool_stages_before_close -q
```

Expected: FAIL because tools still call domain services directly before close.

- [ ] **Step 3: Add staged command service methods**

In `ConversationRuntimeService`, implement:

```python
def stage_command(
    self,
    *,
    turn_id: str,
    domain: str,
    operation: str,
    command_payload: Mapping[str, Any],
    preview_facts: Mapping[str, Any],
    item_index: int,
) -> StagedCommand:
    turn = self._require_turn(turn_id)
    self._ensure_turn_can_close(turn)
    now = self._now()
    command = StagedCommand(
        id=self._id_factory("staged_command"),
        turn_id=turn_id,
        domain=domain,
        operation=operation,
        idempotency_key=(
            f"staged:{turn.conversation_id}:{turn.input_from_seq}:"
            f"{turn.input_to_seq}:{domain}:{operation}:{item_index}"
        ),
        command_payload=dict(command_payload),
        preview_facts=dict(preview_facts),
        status="staged",
        materialized_at=None,
        created_at=now,
        updated_at=now,
    )
    return self.repository.save_staged_command(command)
```

- [ ] **Step 4: Change interactive tool adapters to stage writes**

In `ReminderToolAdapter.execute(...)`, before calling `ReminderService` for state-changing operations, detect staging support:

```python
if hasattr(guard, "stage_command"):
    staged = guard.stage_command(
        domain="reminder",
        operation=operation,
        command_payload=dict(command),
        preview_facts={
            "status": "staged",
            "operation": operation,
            "owner_account_id": owner,
        },
        item_index=int(command.get("item_index") or 1),
    )
    return ToolExecutionResult(
        ok=True,
        facts={
            "status": "staged",
            "staged_command_id": staged.id,
            "preview": dict(staged.preview_facts),
        },
    )
```

Apply the same staging pattern for state-changing operations in `SocialSchedulingToolAdapter`, `CalendarImportToolAdapter`, `IdentityAccessToolAdapter`, and `SettingsToolAdapter`. Read-only operations such as `list_friends`, `query_availability`, `get_access_status`, and `view_settings` continue to execute immediately.

- [ ] **Step 5: Add materializer**

Create `coke/turn/staged_commands.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from coke.domains.conversation_runtime.models import StagedCommand


@dataclass(frozen=True, slots=True)
class MaterializedCommand:
    staged_command_id: str
    facts: Mapping[str, Any]


class StagedCommandMaterializer:
    def __init__(self, *, reminder_tool, social_scheduling_tool, calendar_import_tool, identity_access_tool, settings_tool) -> None:
        self._tools = {
            "reminder": reminder_tool,
            "social_scheduling": social_scheduling_tool,
            "calendar_import": calendar_import_tool,
            "identity_access": identity_access_tool,
            "settings": settings_tool,
        }

    def materialize(self, command: StagedCommand, guard: Any) -> MaterializedCommand:
        tool = self._tools.get(command.domain)
        if tool is None:
            raise RuntimeError(f"staged_command_domain_unsupported:{command.domain}")
        result = tool.execute_without_staging(command.command_payload, guard)
        if not result.ok:
            raise RuntimeError(result.reason_code or "staged_command_materialization_failed")
        return MaterializedCommand(staged_command_id=command.id, facts=result.facts)
```

Add `execute_without_staging(...)` to each adapter and move the existing write path into that method. `execute(...)` stages interactive writes; `execute_without_staging(...)` performs the domain write during close.

- [ ] **Step 6: Materialize staged commands during close**

Before persisting `replied`, `no_reply`, or `pending_async_reply`, call the materializer for staged commands belonging to the turn. Mark each command `materialized` in the same transaction after the domain operation succeeds. If any materialization fails, do not persist a success reply.

Use this close order inside `ConversationRuntimeService` plus a runner-provided materializer callback:

```python
commands = self.repository.staged_commands_for_turn(turn.id)
for command in commands:
    if command.status == "staged":
        materialize(command)
        self.repository.save_staged_command(
            replace(command, status="materialized", materialized_at=now, updated_at=now)
        )
```

- [ ] **Step 7: Run staged-command tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/reminder/test_reminder_service.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add coke/turn/staged_commands.py coke/composition.py coke/domains/conversation_runtime/service.py tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/reminder/test_reminder_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py
git commit -m "feat: stage interactive commands until close"
```

## Task 5: Async Agno Invocation And Provider Timeout

**Files:**
- Modify: `coke/turn/agent.py`
- Modify: `coke/llm/config.py`
- Modify: `coke/config.py`
- Modify: `coke/llm/agno_interaction_agent.py`
- Modify: `tests/unit/coke/llm/test_config.py`
- Modify: `tests/unit/coke/llm/test_interaction_agent.py`

- [ ] **Step 1: Write failing async Agno tests**

Add to `tests/unit/coke/llm/test_interaction_agent.py`:

```python
@pytest.mark.asyncio
async def test_ainvoke_uses_arun_with_deterministic_run_id():
    fake_agent = FakeAgentInstance(content={"type": "reply", "segments": ["ok"]})
    factory = FakeAgentFactory(fake_agent)
    agent = AgnoInteractionAgent(model=object(), agent_factory=factory)

    result = await agent.ainvoke(_request(memory_enabled=True, run_id="turn_1"))

    assert result.output == {"type": "reply", "segments": ["ok"]}
    assert fake_agent.calls[0]["method"] == "arun"
    assert fake_agent.calls[0]["kwargs"]["run_id"] == "turn_1"


@pytest.mark.asyncio
async def test_cancel_run_calls_agno_cancel_hook(monkeypatch):
    called = []

    async def fake_cancel(run_id: str):
        called.append(run_id)
        return True

    monkeypatch.setattr(agno_agent_module.Agent, "acancel_run", fake_cancel)
    agent = AgnoInteractionAgent(model=object(), agent_factory=FakeAgentFactory(FakeAgentInstance()))

    await agent.cancel("turn_1")

    assert called == ["turn_1"]
```

Update `FakeAgentInstance` with:

```python
async def arun(self, input, **kwargs):
    self.calls.append({"method": "arun", "input": input, "kwargs": kwargs})
    if self.raise_timeout_once:
        self.raise_timeout_once = False
        raise TimeoutError("budget exceeded")
    return RunOutput(content=self.content)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_ainvoke_uses_arun_with_deterministic_run_id tests/unit/coke/llm/test_interaction_agent.py::test_cancel_run_calls_agno_cancel_hook -q
```

Expected: FAIL because async methods are missing.

- [ ] **Step 3: Extend the agent protocol**

In `coke/turn/agent.py`:

```python
class InteractionAgent(Protocol):
    def invoke(self, request: AgentRequest) -> AgentResult:
        raise NotImplementedError

    async def ainvoke(self, request: AgentRequest) -> AgentResult:
        raise NotImplementedError

    async def cancel(self, run_id: str) -> bool:
        raise NotImplementedError

    def complete_async(self, task_id: str) -> AgentResult:
        raise NotImplementedError
```

- [ ] **Step 4: Add timeout configuration**

In `coke/llm/config.py`, add:

```python
DEFAULT_INTERACTION_TIMEOUT_S = 45.0

@dataclass(frozen=True, slots=True)
class SiliconFlowLLMConfig:
    api_key: str
    base_url: str = SILICONFLOW_BASE_URL
    interaction_model: str = DEFAULT_INTERACTION_MODEL
    interpreter_model: str = DEFAULT_INTERPRETER_MODEL
    detector_model: str = DEFAULT_DETECTOR_MODEL
    agno_database_url: str | None = None
    agno_create_schema: bool = False
    interaction_timeout_s: float = DEFAULT_INTERACTION_TIMEOUT_S
```

Pass timeout only to the interaction model:

```python
def create_interaction_model(self) -> OpenAILike:
    return self._create_model(
        self.interaction_model,
        timeout=self.interaction_timeout_s,
    )

def _create_model(self, model_id: str, *, extra_body: dict | None = None, timeout: float | None = None) -> OpenAILike:
    return OpenAILike(
        id=model_id,
        api_key=self.api_key,
        base_url=self.base_url,
        extra_body=extra_body,
        timeout=timeout,
    )
```

In `coke/config.py`, add `interaction_timeout_s` and parse `COKE_INTERACTION_TIMEOUT_S` with `_positive_float`.

- [ ] **Step 5: Implement async Agno invocation**

In `coke/llm/agno_interaction_agent.py`:

```python
async def ainvoke(self, request: AgentRequest) -> AgentResult:
    return await self._arun_request(request, store_timeout=True)

async def cancel(self, run_id: str) -> bool:
    return bool(await Agent.acancel_run(run_id))

async def _arun_request(self, request: AgentRequest, *, store_timeout: bool) -> AgentResult:
    agent = self._build_agent(request)
    try:
        run_output = await agent.arun(
            _agent_input(request),
            user_id=request.account_id,
            session_id=request.conversation_id,
            run_id=request.run_id or request.turn_id,
            metadata={
                "turn_id": request.turn_id,
                "trigger_type": request.trigger_type,
                "mode": str(request.mode),
            },
            add_session_state_to_context=False,
        )
    except TimeoutError:
        if not store_timeout:
            return AgentResult.timeout(self.task_id_factory())
        task_id = self.task_id_factory()
        self._async_requests[task_id] = request
        return AgentResult.timeout(task_id)
    return _agent_result_from_content(getattr(run_output, "content", None))
```

Refactor the duplicated agent construction from `_run_request(...)` into `_build_agent(...)` so sync render paths still work.

- [ ] **Step 6: Run async agent and config tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py tests/unit/coke/llm/test_config.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add coke/turn/agent.py coke/llm/config.py coke/config.py coke/llm/agno_interaction_agent.py tests/unit/coke/llm/test_config.py tests/unit/coke/llm/test_interaction_agent.py
git commit -m "feat: add async agno interaction path"
```

## Task 6: Interactive Turn Supervisor And Worker Interrupts

**Files:**
- Create: `coke/worker/interactive_supervisor.py`
- Modify: `coke/worker/__main__.py`
- Modify: `coke/composition.py`
- Modify: `tests/unit/coke/worker/test_worker_topic_resilience.py`
- Modify: `tests/unit/coke/worker/test_notification_render_trigger.py`
- Create: `tests/unit/coke/worker/test_interactive_supervisor.py`

- [ ] **Step 1: Write failing supervisor tests**

Create `tests/unit/coke/worker/test_interactive_supervisor.py`:

```python
from __future__ import annotations

import asyncio

import pytest

from coke.turn.context import TurnMode, TurnTrigger
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor


class FakeAgent:
    def __init__(self) -> None:
        self.cancelled = []

    async def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True


class FakeRunner:
    def __init__(self) -> None:
        self.started = []
        self.released = asyncio.Event()

    async def run_inbound_turn_async(self, trigger):
        self.started.append(trigger)
        await self.released.wait()
        return "finished"


@pytest.mark.asyncio
async def test_new_inbound_cancels_active_pre_close_turn():
    runner = FakeRunner()
    agent = FakeAgent()
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runner,
        interaction_agent=agent,
    )
    first = TurnTrigger(
        trigger_id="inbound:1",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={"causal_inbound_event_id": "provider:1"},
    )
    second = TurnTrigger(
        trigger_id="inbound:2",
        trigger_type="InboundTurn",
        mode=TurnMode.INTERACTIVE,
        conversation_id="conversation_1",
        account_id="account_1",
        payload={"causal_inbound_event_id": "provider:2"},
    )

    await supervisor.submit(first)
    await supervisor.submit(second)

    assert agent.cancelled == ["inbound:1"]
    assert runner.started[0].trigger_id == "inbound:1"
    assert runner.started[1].trigger_id == "inbound:2"
```

- [ ] **Step 2: Run supervisor test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/worker/test_interactive_supervisor.py -q
```

Expected: FAIL because `InteractiveTurnSupervisor` does not exist.

- [ ] **Step 3: Implement the supervisor**

Create `coke/worker/interactive_supervisor.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from coke.turn.context import TurnTrigger


@dataclass(slots=True)
class ActiveInteractiveTurn:
    trigger: TurnTrigger
    task: asyncio.Task
    run_id: str


class InteractiveTurnSupervisor:
    def __init__(self, *, turn_runner: Any, interaction_agent: Any) -> None:
        self.turn_runner = turn_runner
        self.interaction_agent = interaction_agent
        self._active: dict[str, ActiveInteractiveTurn] = {}

    async def submit(self, trigger: TurnTrigger) -> None:
        existing = self._active.get(trigger.conversation_id)
        if existing is not None and not existing.task.done():
            await self.interaction_agent.cancel(existing.run_id)
            existing.task.cancel()
        run_id = trigger.trigger_id
        task = asyncio.create_task(self.turn_runner.run_inbound_turn_async(trigger))
        self._active[trigger.conversation_id] = ActiveInteractiveTurn(
            trigger=trigger,
            task=task,
            run_id=run_id,
        )

    async def drain_completed(self) -> list[tuple[TurnTrigger, Any]]:
        completed = []
        for conversation_id, active in list(self._active.items()):
            if not active.task.done():
                continue
            try:
                result = active.task.result()
            except asyncio.CancelledError:
                self._active.pop(conversation_id, None)
                continue
            completed.append((active.trigger, result))
            self._active.pop(conversation_id, None)
        return completed
```

After this passes, extend the implementation to use a runtime factory with a fresh SQLAlchemy session per task. The final supervisor must not share one mutable `Session` across concurrent tasks.

- [ ] **Step 4: Add async inbound runner wrapper**

In `coke/turn/runner.py`, add:

```python
async def run_inbound_turn_async(self, trigger: TurnTrigger) -> TurnRunResult:
    return await self._run_inbound_turn_async(trigger)
```

Move interactive Agno execution to `await self.interaction_agent.ainvoke(...)`. Keep render turns synchronous.

- [ ] **Step 5: Route inbound events through the supervisor**

In `coke/worker/__main__.py`, construct the supervisor once per worker loop. For `turn.inbound`, submit to supervisor and commit the wake-up ack quickly. For render topics, keep the current synchronous execution path.

Use this routing shape:

```python
if trigger.mode == TurnMode.INTERACTIVE:
    await supervisor.submit(trigger)
else:
    result = runtime.turn_runner.run_render_turn(trigger)
    results.append((trigger, result))
```

After each poll iteration, call:

```python
completed = await supervisor.drain_completed()
for trigger, result in completed:
    _publish_reply(runtime, event_id=result.event_id, trigger=trigger, result=result)
```

- [ ] **Step 6: Add recovery for open windows**

On worker startup, query conversations where `latest_inbound_seq > last_closed_inbound_seq` and enqueue one synthetic `InboundTurn` trigger per conversation. Use trigger id:

```python
trigger_id = f"recover:{conversation.id}:{conversation.latest_inbound_seq}"
```

This recovery trigger must claim the same open input window through ConversationRuntime.

- [ ] **Step 7: Run worker tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/worker/test_interactive_supervisor.py tests/unit/coke/worker/test_worker_topic_resilience.py tests/unit/coke/worker/test_notification_render_trigger.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add coke/worker/interactive_supervisor.py coke/worker/__main__.py coke/composition.py tests/unit/coke/worker/test_interactive_supervisor.py tests/unit/coke/worker/test_worker_topic_resilience.py tests/unit/coke/worker/test_notification_render_trigger.py
git commit -m "feat: supervise interruptible inbound turns"
```

## Task 7: End-To-End Coalescing And Reply Publication

**Files:**
- Modify: `coke/worker/__main__.py`
- Modify: `coke/turn/runner.py`
- Modify: `tests/integration/coke/test_composition_turn_integration.py`
- Create: `tests/integration/coke/test_pre_reply_interrupt_coalescing.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/coke/test_pre_reply_interrupt_coalescing.py`:

```python
from __future__ import annotations

import asyncio

import pytest

from coke.turn.agent import AgentResult
from coke.worker.interactive_supervisor import InteractiveTurnSupervisor


class SlowInterruptibleAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.requests = []
        self.cancelled_run_ids = []
        self.output = {"type": "reply", "segments": ["I set it for 10."]}

    async def ainvoke(self, request):
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        return AgentResult.completed(self.output)

    async def cancel(self, run_id: str) -> bool:
        self.cancelled_run_ids.append(run_id)
        self.release.set()
        return True

    def invoke(self, request):
        raise AssertionError("interactive coalescing test must use ainvoke")

    def complete_async(self, task_id: str):
        return AgentResult.completed(self.output)


@pytest.mark.asyncio
async def test_two_inbounds_during_slow_agent_produce_one_coalesced_reply(composed):
    runtime, _semantic, _agent, _outbound, identity = composed
    slow_agent = SlowInterruptibleAgent()
    runtime.turn_runner.interaction_agent = slow_agent
    supervisor = InteractiveTurnSupervisor(
        turn_runner=runtime.turn_runner,
        interaction_agent=slow_agent,
    )

    first = _record_inbound(runtime, identity, "provider:1", "remind me at 9")
    await supervisor.submit(_trigger(first, identity, "provider:1", "remind me at 9"))
    await slow_agent.started.wait()

    second = _record_inbound(runtime, identity, "provider:2", "actually 10")
    await supervisor.submit(_trigger(second, identity, "provider:2", "actually 10"))
    slow_agent.release.set()
    completed = []
    for _ in range(20):
        completed.extend(await supervisor.drain_completed())
        if completed:
            break
        await asyncio.sleep(0.01)

    turns = runtime.repositories.conversation_runtime.latest_turn_ids(first.conversation.id, limit=10)
    dispositions = [
        runtime.conversation_runtime_service.get_disposition(turn_id).disposition
        for turn_id in turns
    ]
    assert "superseded" in dispositions
    assert "replied" in dispositions
    assert [message.text for message in slow_agent.requests[-1].current_input_messages] == [
        "remind me at 9",
        "actually 10",
    ]
    assert completed[-1][1].visible_text == "I set it for 10."
```

This test uses a local harness with a fake async agent. Keep it in-process; do not call a live LLM provider.

- [ ] **Step 2: Run integration test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/integration/coke/test_pre_reply_interrupt_coalescing.py -q
```

Expected: FAIL until the worker publishes the coalesced reply against the latest causal inbound event.

- [ ] **Step 3: Publish coalesced replies to latest causal inbound**

When a turn closes, the result must carry `latest_causal_inbound_event_id` from the last message in the input window. In `TurnRunResult`, add:

```python
latest_causal_inbound_event_id: str | None = None
coalesced_causal_inbound_event_ids: tuple[str, ...] = ()
```

Populate it from `current_input_messages` in `_result_from_disposition(...)` for interactive turns.

- [ ] **Step 4: Complete older waiters**

In reply pub/sub publishing, send the visible reply to `latest_causal_inbound_event_id`. For older causal ids in the same window, publish a terminal coalesced result:

```python
{
    "event_id": event_id,
    "turn_id": result.turn_id,
    "disposition": "superseded",
    "reason_code": "coalesced_into_newer_inbound",
    "visible_text": None,
}
```

- [ ] **Step 5: Run integration tests**

Run:

```bash
.venv/bin/python -m pytest tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/integration/coke/test_composition_turn_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add coke/worker/__main__.py coke/turn/runner.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/integration/coke/test_composition_turn_integration.py
git commit -m "feat: publish coalesced inbound replies"
```

## Task 8: Provider Cancellation Smoke And Final Verification

**Files:**
- Create: `tests/integration/coke/test_agno_cancellation_contract.py`
- Modify: `docs/superpowers/specs/2026-05-31-coke-pre-reply-interrupt-coalescing-design.md` if implementation discovers a sharper provider-cancellation constraint.
- Modify: `docs/ARCHITECTURE.md` only if implementation changes the architecture contract.

- [ ] **Step 1: Write provider-cancellation contract test**

Create `tests/integration/coke/test_agno_cancellation_contract.py` using a fake async Agno agent instance. The assertion must distinguish cancelled, timeout-bounded, and blocked behavior:

```python
from __future__ import annotations

import asyncio
from time import monotonic

import pytest
from agno.run.agent import RunOutput

import coke.llm.agno_interaction_agent as agno_agent_module
from coke.llm.agno_interaction_agent import AgnoInteractionAgent
from tests.unit.coke.llm.test_interaction_agent import FakeAgentFactory, _request


class BlockingAsyncAgentInstance:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = []

    async def arun(self, input, **kwargs):
        self.calls.append({"input": input, "kwargs": kwargs})
        self.started.set()
        await self.release.wait()
        return RunOutput(content={"type": "reply", "segments": ["late"]})

    def run(self, input, **kwargs):
        raise AssertionError("cancellation contract test must use arun")


@pytest.mark.asyncio
async def test_async_agno_call_task_can_be_cancelled(monkeypatch):
    cancelled = []

    async def fake_cancel(run_id: str) -> bool:
        cancelled.append(run_id)
        return True

    monkeypatch.setattr(agno_agent_module.Agent, "acancel_run", fake_cancel)
    fake_instance = BlockingAsyncAgentInstance()
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(fake_instance),
    )
    task = asyncio.create_task(agent.ainvoke(_request(memory_enabled=True, run_id="turn_cancel")))
    await fake_instance.started.wait()

    await agent.cancel("turn_cancel")
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled == ["turn_cancel"]
```

Add a timeout-bounded test for providers that do not abort promptly:

```python
class TimeoutAsyncAgentInstance:
    async def arun(self, input, **kwargs):
        raise TimeoutError("provider timeout")

    def run(self, input, **kwargs):
        raise AssertionError("timeout contract test must use arun")


@pytest.mark.asyncio
async def test_async_agno_timeout_bounds_uncancellable_provider():
    agent = AgnoInteractionAgent(
        model=object(),
        agent_factory=FakeAgentFactory(TimeoutAsyncAgentInstance()),
    )
    started = monotonic()
    result = await agent.ainvoke(_request(memory_enabled=True, run_id="turn_timeout"))
    elapsed = monotonic() - started

    assert result.timed_out is True
    assert elapsed < 1.0
```

- [ ] **Step 2: Run focused integration tests**

Run:

```bash
.venv/bin/python -m pytest tests/integration/coke/test_agno_cancellation_contract.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py -q
```

Expected: PASS for the CI-safe timeout-bounded contract. If socket cancellation is environment-dependent, record that distinction in the test name and spec.

- [ ] **Step 3: Run backend unit tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
```

Expected: PASS.

- [ ] **Step 4: Run integration tests for touched runtime surfaces**

Run:

```bash
.venv/bin/python -m pytest tests/integration/coke/test_conversation_runtime_repository_contract.py tests/integration/coke/test_composition_turn_integration.py tests/integration/coke/test_pre_reply_interrupt_coalescing.py tests/integration/coke/test_agno_cancellation_contract.py -v
```

Expected: PASS.

- [ ] **Step 5: Run repository verification routing**

Run:

```bash
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
zsh scripts/review-trigger --base HEAD~1
```

Expected: no whitespace errors; backend and docs surfaces pass; review trigger reports risks without requiring human review.

- [ ] **Step 6: Commit final verification/doc alignment**

```bash
git add tests/integration/coke/test_agno_cancellation_contract.py docs/ARCHITECTURE.md docs/superpowers/specs/2026-05-31-coke-pre-reply-interrupt-coalescing-design.md
git commit -m "test: verify interruptible agno cancellation contract"
```

Skip the final commit only if all touched files were already committed by earlier tasks.

## Plan Self-Review

- Spec coverage: Tasks 1-2 cover input-window schema, claim, freshness, and close. Task 3 covers prompt semantics. Task 4 covers staged commands. Task 5 covers Agno async/cancellation and provider timeout. Task 6 covers worker supervision and recovery. Task 7 covers pub/sub and coalesced reply delivery. Task 8 covers cancellation smoke and final verification.
- Placeholder scan: The plan contains concrete file paths, commands, expected results, and code snippets for each implementation task.
- Type consistency: The plan uses `input_from_seq`, `input_to_seq`, `superseded_by_inbound_seq`, `last_closed_inbound_seq`, `CurrentInputMessage`, `StagedCommand`, `AgentRequest.current_input_messages`, and `AgentRequest.run_id` consistently across tasks.
- Architecture dependency: `docs/ARCHITECTURE.md` was updated before this plan, and the spec now references that architecture section.
