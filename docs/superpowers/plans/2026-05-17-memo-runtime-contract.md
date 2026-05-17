# Memo Runtime Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless flomo-like memo runtime as an embedded Python package, then add a narrow Coke adapter surface that calls its contract.

**Architecture:** Create a new package repository at `/data/projects/coke-memo-runtime` that owns memo models, storage, search, review, proposals, and the `MemoRuntimeContract`. Coke consumes the package through adapter code only; frontend pages and reminder runtime changes are outside this plan.

**Tech Stack:** Python 3.12, dataclasses, pytest, psycopg 3, Postgres with pgvector, optional in-memory test storage, existing Coke pytest and repo-OS checks.

---

**Plan Status:** draft
**Status Date:** 2026-05-17
**Freshness Check:** Verify against current `main`, `docs/ARCHITECTURE.md`, `docs/design-docs/agent-capability-contract.md`, and `docs/superpowers/specs/2026-05-17-memo-runtime-contract-design.md` before execution.

## Scope

Included:

- Create `/data/projects/coke-memo-runtime` as a Python package repository.
- Implement `MemoRuntimeContract` with card CRUD, search, review queue, and proposal lifecycle.
- Implement package-owned storage with Postgres/pgvector schema and an in-memory storage for tests.
- Add Coke-side adapter stubs that call the memo contract and prove adapter boundaries with tests.
- Document how the frontend/API layer should consume the memo runtime without owning business behavior.

Excluded:

- Frontend UI implementation.
- Standalone memo HTTP service.
- Reminder Runtime Contract changes.
- Bulk migration from Coke legacy `embeddings`.
- Rich editor, graph view, sharing, collaboration, import/export, and public API.

## File Map

New repository: `/data/projects/coke-memo-runtime`

- `pyproject.toml`: package metadata and dependencies.
- `memo_runtime/__init__.py`: public exports.
- `memo_runtime/errors.py`: stable error taxonomy.
- `memo_runtime/models.py`: dataclasses and literal types.
- `memo_runtime/config.py`: runtime configuration object.
- `memo_runtime/storage/base.py`: storage protocol.
- `memo_runtime/storage/memory.py`: in-memory storage for tests.
- `memo_runtime/storage/postgres.py`: Postgres/pgvector storage implementation.
- `memo_runtime/storage/migrations/001_initial.sql`: schema, indexes, pgvector extension.
- `memo_runtime/embeddings.py`: embedding provider protocol and deterministic test provider.
- `memo_runtime/search.py`: keyword/semantic search orchestration.
- `memo_runtime/review.py`: review queue selection.
- `memo_runtime/proposals.py`: proposal lifecycle helpers.
- `memo_runtime/idempotency.py`: mutation replay helper for create/update/review/proposal writes.
- `memo_runtime/contract.py`: `MemoRuntimeContract`.
- `tests/`: package unit and contract tests.

Coke repository: `/data/projects/coke`

- `docs/superpowers/specs/2026-05-17-memo-runtime-contract-design.md`: design reference.
- `docs/superpowers/plans/2026-05-17-memo-runtime-contract.md`: this plan.
- `agent/agno_agent/capabilities/memo.py`: future agent adapter over the memo contract.
- `tests/unit/agent/test_memo_capability_adapter.py`: adapter boundary tests.
- `docs/ARCHITECTURE.md`: add memo runtime note after implementation is verified.
- `docs/product-specs/FEATURE_TREE.md`: add memo API/product surface after adapter exists.

## Dependency Order

The Coke adapter must not be implemented until the package is importable from
Coke's environment. Execute the wiring task before the adapter task:

1. Build and test `/data/projects/coke-memo-runtime`.
2. Add it to Coke as `memo-runtime/`.
3. Install it in Coke's virtualenv with `.venv/bin/python -m pip install -e memo-runtime`.
4. Only then add Coke adapter tests and adapter code.

## Task 1: Create The Package Skeleton

**Files:**

- Create: `/data/projects/coke-memo-runtime/pyproject.toml`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/__init__.py`
- Create: `/data/projects/coke-memo-runtime/tests/test_import.py`

- [ ] **Step 1: Create the repository root**

Run:

```bash
mkdir -p /data/projects/coke-memo-runtime/memo_runtime
mkdir -p /data/projects/coke-memo-runtime/tests
cd /data/projects/coke-memo-runtime
git init
```

Expected: `Initialized empty Git repository`.

- [ ] **Step 2: Write package metadata**

Create `/data/projects/coke-memo-runtime/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "coke-memo-runtime"
version = "0.1.0"
description = "Headless memo runtime contract for Coke"
requires-python = ">=3.12"
dependencies = [
  "psycopg[binary]>=3.1",
]

[project.optional-dependencies]
test = [
  "pytest>=8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3: Add a public import surface**

Create `/data/projects/coke-memo-runtime/memo_runtime/__init__.py`:

```python
from memo_runtime.contract import MemoRuntimeContract
from memo_runtime.config import MemoRuntimeConfig

__all__ = ["MemoRuntimeConfig", "MemoRuntimeContract"]
```

- [ ] **Step 4: Add an import test**

Create `/data/projects/coke-memo-runtime/tests/test_import.py`:

```python
def test_public_imports():
    import memo_runtime

    assert "MemoRuntimeContract" in memo_runtime.__all__
    assert "MemoRuntimeConfig" in memo_runtime.__all__
```

- [ ] **Step 5: Run the test and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_import.py -q
```

Expected before later files exist: FAIL with `ModuleNotFoundError` for
`memo_runtime.contract`.

After Task 2 adds the referenced modules, rerun the same command and expect:
`1 passed`.

Commit after Task 2 passes:

```bash
git add pyproject.toml memo_runtime tests
git commit -m "chore: initialize memo runtime package"
```

## Task 2: Define Domain Models And Errors

**Files:**

- Create: `/data/projects/coke-memo-runtime/memo_runtime/errors.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/models.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/config.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/contract.py`
- Test: `/data/projects/coke-memo-runtime/tests/test_models.py`

- [ ] **Step 1: Write model tests**

Create `/data/projects/coke-memo-runtime/tests/test_models.py`:

```python
from datetime import UTC, datetime

from memo_runtime.models import MemoCard, MemoVisibility


def test_memo_card_requires_title_or_body():
    now = datetime(2026, 5, 17, tzinfo=UTC)

    try:
        MemoCard(
            id="card-1",
            owner_id="owner-1",
            kind="note",
            title="",
            body="",
            tags=(),
            visibility="agent_visible",
            lifecycle="active",
            created_by="user",
            created_at=now,
            updated_at=now,
        )
    except ValueError as exc:
        assert "title or body" in str(exc)
    else:
        raise AssertionError("empty memo card should be rejected")


def test_visibility_literal_accepts_private_and_agent_visible():
    values: tuple[MemoVisibility, MemoVisibility] = ("private", "agent_visible")
    assert values == ("private", "agent_visible")
```

- [ ] **Step 2: Implement errors**

Create `/data/projects/coke-memo-runtime/memo_runtime/errors.py`:

```python
class MemoRuntimeError(Exception):
    code = "memo_runtime_error"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


class MemoInvalidRequest(MemoRuntimeError):
    code = "memo_invalid_request"


class MemoOwnerRequired(MemoRuntimeError):
    code = "memo_owner_required"


class MemoNotFound(MemoRuntimeError):
    code = "memo_not_found"


class MemoPermissionDenied(MemoRuntimeError):
    code = "memo_permission_denied"


class MemoConflict(MemoRuntimeError):
    code = "memo_conflict"


class MemoStorageUnavailable(MemoRuntimeError):
    code = "memo_storage_unavailable"


class MemoEmbeddingFailed(MemoRuntimeError):
    code = "memo_embedding_failed"


class MemoProposalNotFound(MemoRuntimeError):
    code = "memo_proposal_not_found"


class MemoProposalNotPending(MemoRuntimeError):
    code = "memo_proposal_not_pending"
```

- [ ] **Step 3: Implement models**

Create `/data/projects/coke-memo-runtime/memo_runtime/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MemoKind = Literal[
    "note",
    "goal",
    "commitment",
    "blocker",
    "preference",
    "reflection",
    "fact",
    "open_loop",
]
MemoVisibility = Literal["private", "agent_visible"]
MemoLifecycle = Literal["active", "archived", "deleted"]
MemoActorType = Literal["user", "agent", "import", "api", "system"]
MemoProposalType = Literal[
    "create_card",
    "update_card",
    "merge_cards",
    "add_tags",
    "review_prompt",
]
MemoProposalStatus = Literal["pending", "accepted", "rejected", "expired"]
MemoReviewStatus = Literal["pending", "reviewed", "dismissed"]


@dataclass(frozen=True)
class MemoCard:
    id: str
    owner_id: str
    kind: MemoKind
    title: str
    body: str
    tags: tuple[str, ...]
    visibility: MemoVisibility
    lifecycle: MemoLifecycle
    created_by: MemoActorType
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    deleted_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    review_count: int = 0
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.owner_id.strip():
            raise ValueError("owner_id is required")
        if not self.title.strip() and not self.body.strip():
            raise ValueError("memo card requires title or body")
        object.__setattr__(self, "tags", tuple(sorted({tag.strip() for tag in self.tags if tag.strip()})))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class MemoEvent:
    id: str
    owner_id: str
    card_id: str | None
    event_type: str
    actor_type: MemoActorType
    actor_id: str | None
    occurred_at: datetime
    trace_id: str | None
    idempotency_key: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class MemoProposal:
    id: str
    owner_id: str
    proposal_type: MemoProposalType
    status: MemoProposalStatus
    candidate_card: dict[str, Any]
    target_card_id: str | None
    rationale: str
    created_by: MemoActorType
    created_at: datetime
    decided_at: datetime | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class MemoReviewItem:
    id: str
    owner_id: str
    card_id: str
    reason: str
    score: float
    status: MemoReviewStatus
    created_at: datetime
    reviewed_at: datetime | None = None
    next_eligible_at: datetime | None = None


@dataclass(frozen=True)
class MemoSearchHit:
    card: MemoCard
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MemoSearchResult:
    hits: tuple[MemoSearchHit, ...]
```

- [ ] **Step 4: Implement config and a temporary contract shell**

Create `/data/projects/coke-memo-runtime/memo_runtime/config.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class MemoRuntimeConfig:
    database_url: str | None = None
    embedding_model: str = "test-deterministic"
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
```

Create `/data/projects/coke-memo-runtime/memo_runtime/contract.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from memo_runtime.config import MemoRuntimeConfig
from memo_runtime.models import MemoActorType, MemoKind, MemoProposalType, MemoVisibility


@dataclass(frozen=True)
class CreateMemoCardRequest:
    owner_id: str
    kind: MemoKind
    title: str
    body: str
    tags: tuple[str, ...]
    visibility: MemoVisibility
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class UpdateMemoCardRequest:
    owner_id: str
    card_id: str
    title: str | None
    body: str | None
    tags: tuple[str, ...] | None
    visibility: MemoVisibility | None
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ArchiveMemoCardRequest:
    owner_id: str
    card_id: str
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class DeleteMemoCardRequest:
    owner_id: str
    card_id: str
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class GetMemoCardRequest:
    owner_id: str
    card_id: str


@dataclass(frozen=True)
class SearchMemoCardsRequest:
    owner_id: str
    query: str
    tags: tuple[str, ...]
    kinds: tuple[str, ...]
    include_private: bool
    limit: int


@dataclass(frozen=True)
class GetMemoReviewQueueRequest:
    owner_id: str
    limit: int
    include_private: bool


@dataclass(frozen=True)
class RecordMemoReviewActionRequest:
    owner_id: str
    card_id: str
    action: Literal["mark_reviewed", "dismiss", "accept_proposal", "reject_proposal"]
    actor_type: MemoActorType
    actor_id: str | None
    proposal_id: str | None = None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class CreateMemoProposalRequest:
    owner_id: str
    proposal_type: MemoProposalType
    candidate_card: dict
    target_card_id: str | None
    rationale: str
    created_by: MemoActorType
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class AcceptMemoProposalRequest:
    owner_id: str
    proposal_id: str
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class RejectMemoProposalRequest:
    owner_id: str
    proposal_id: str
    actor_type: MemoActorType
    actor_id: str | None
    trace_id: str | None = None
    idempotency_key: str | None = None


class MemoRuntimeContract:
    def __init__(self, config: MemoRuntimeConfig | None = None, *, storage=None, embedder=None) -> None:
        self.config = config or MemoRuntimeConfig()
        self.storage = storage
        self.embedder = embedder
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_import.py tests/test_models.py -q
```

Expected: `3 passed`.

Commit:

```bash
git add memo_runtime tests
git commit -m "feat: define memo runtime domain models"
```

## Task 3: Add Storage And Contract Card CRUD

**Files:**

- Create: `/data/projects/coke-memo-runtime/memo_runtime/storage/base.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/storage/memory.py`
- Modify: `/data/projects/coke-memo-runtime/memo_runtime/contract.py`
- Test: `/data/projects/coke-memo-runtime/tests/test_contract_cards.py`

- [ ] **Step 1: Write card CRUD contract tests**

Create `/data/projects/coke-memo-runtime/tests/test_contract_cards.py`:

```python
from datetime import UTC, datetime

from memo_runtime.config import MemoRuntimeConfig
from memo_runtime.contract import (
    ArchiveMemoCardRequest,
    CreateMemoCardRequest,
    DeleteMemoCardRequest,
    GetMemoCardRequest,
    MemoRuntimeContract,
    SearchMemoCardsRequest,
    UpdateMemoCardRequest,
)
from memo_runtime.storage.memory import InMemoryMemoStorage


def _runtime():
    return MemoRuntimeContract(
        MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, 12, 0, tzinfo=UTC)),
        storage=InMemoryMemoStorage(),
    )


def test_create_update_archive_delete_card_records_events():
    runtime = _runtime()

    card = runtime.create_card(
        CreateMemoCardRequest(
            owner_id="owner-1",
            kind="goal",
            title="Launch memo workspace",
            body="Make browse and review the core user loop.",
            tags=("product", "memo"),
            visibility="agent_visible",
            actor_type="user",
            actor_id="user-1",
            trace_id="trace-1",
            idempotency_key="create-1",
        )
    )
    updated = runtime.update_card(
        UpdateMemoCardRequest(
            owner_id="owner-1",
            card_id=card.id,
            title="Launch memo review workspace",
            body=None,
            tags=("product", "review"),
            visibility=None,
            actor_type="user",
            actor_id="user-1",
            trace_id="trace-2",
            idempotency_key="update-1",
        )
    )
    archived = runtime.archive_card(
        ArchiveMemoCardRequest(
            owner_id="owner-1",
            card_id=card.id,
            actor_type="user",
            actor_id="user-1",
            trace_id="trace-3",
            idempotency_key="archive-1",
        )
    )
    deleted = runtime.delete_card(
        DeleteMemoCardRequest(
            owner_id="owner-1",
            card_id=card.id,
            actor_type="user",
            actor_id="user-1",
            trace_id="trace-4",
            idempotency_key="delete-1",
        )
    )

    assert updated.title == "Launch memo review workspace"
    assert archived.lifecycle == "archived"
    assert deleted.lifecycle == "deleted"
    assert runtime.get_card(GetMemoCardRequest(owner_id="owner-1", card_id=card.id)).lifecycle == "deleted"
    assert [event.event_type for event in runtime.storage.events] == [
        "card.created",
        "card.updated",
        "card.archived",
        "card.deleted",
    ]


def test_search_excludes_deleted_and_other_owner_cards():
    runtime = _runtime()
    own = runtime.create_card(CreateMemoCardRequest("owner-1", "note", "Review loop", "", ("memo",), "agent_visible", "user", "u1"))
    other = runtime.create_card(CreateMemoCardRequest("owner-2", "note", "Review loop", "", ("memo",), "agent_visible", "user", "u2"))
    runtime.delete_card(DeleteMemoCardRequest(owner_id="owner-1", card_id=own.id, actor_type="user", actor_id="u1"))

    result = runtime.search_cards(SearchMemoCardsRequest(owner_id="owner-1", query="Review", tags=(), kinds=(), include_private=True, limit=10))

    assert result.hits == ()
    assert other.owner_id == "owner-2"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_contract_cards.py -q
```

Expected: FAIL because request classes and storage do not exist.

- [ ] **Step 3: Implement storage protocol and memory storage**

Create `/data/projects/coke-memo-runtime/memo_runtime/storage/base.py`:

```python
from __future__ import annotations

from typing import Protocol

from memo_runtime.models import MemoCard, MemoEvent, MemoProposal


class MemoStorage(Protocol):
    def replay_mutation(self, owner_id: str, operation: str, idempotency_key: str | None) -> tuple[str, str] | None: ...
    def record_mutation(self, owner_id: str, operation: str, idempotency_key: str | None, result_type: str, result_id: str) -> None: ...
    def insert_card(self, card: MemoCard, event: MemoEvent, *, idempotency_key: str | None) -> MemoCard: ...
    def get_card(self, owner_id: str, card_id: str) -> MemoCard: ...
    def update_card(self, card: MemoCard, event: MemoEvent, *, idempotency_key: str | None) -> MemoCard: ...
    def list_cards(self, owner_id: str) -> tuple[MemoCard, ...]: ...
    def insert_event(self, event: MemoEvent, *, idempotency_key: str | None) -> MemoEvent: ...
    def insert_proposal(self, proposal: MemoProposal, event: MemoEvent, *, idempotency_key: str | None) -> MemoProposal: ...
    def get_proposal(self, owner_id: str, proposal_id: str) -> MemoProposal: ...
    def update_proposal(self, proposal: MemoProposal, event: MemoEvent, *, idempotency_key: str | None) -> MemoProposal: ...
```

Create `/data/projects/coke-memo-runtime/memo_runtime/storage/memory.py` with deterministic id counters, owner-scoped maps, mutation replay keyed by `(owner_id, operation, idempotency_key)`, and `events` as a public tuple/list for tests.

- [ ] **Step 4: Implement CRUD using the existing request classes**

The request dataclasses were created in Task 2. Implement `create_card`,
`update_card`, `archive_card`, `delete_card`, `get_card`, and `search_cards`
with request-object signatures only. The first search implementation may score
keyword/tag matches without embeddings.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_contract_cards.py tests/test_models.py tests/test_import.py -q
```

Expected: all tests pass.

Commit:

```bash
git add memo_runtime tests
git commit -m "feat: add memo card contract operations"
```

## Task 4: Add Search, Embeddings, And Review Queue

**Files:**

- Create: `/data/projects/coke-memo-runtime/memo_runtime/embeddings.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/search.py`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/review.py`
- Modify: `/data/projects/coke-memo-runtime/memo_runtime/contract.py`
- Test: `/data/projects/coke-memo-runtime/tests/test_search_review.py`

- [ ] **Step 1: Write search and review tests**

Create `/data/projects/coke-memo-runtime/tests/test_search_review.py`:

```python
from datetime import UTC, datetime

from memo_runtime.config import MemoRuntimeConfig
from memo_runtime.contract import (
    CreateMemoCardRequest,
    GetMemoCardRequest,
    GetMemoReviewQueueRequest,
    MemoRuntimeContract,
    RecordMemoReviewActionRequest,
    SearchMemoCardsRequest,
)
from memo_runtime.storage.memory import InMemoryMemoStorage


def test_agent_search_excludes_private_cards():
    runtime = MemoRuntimeContract(MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, tzinfo=UTC)), storage=InMemoryMemoStorage())
    runtime.create_card(CreateMemoCardRequest("owner-1", "note", "Private health note", "", ("health",), "private", "user", "u1"))
    runtime.create_card(CreateMemoCardRequest("owner-1", "note", "Agent visible goal", "", ("goal",), "agent_visible", "user", "u1"))

    result = runtime.search_cards(SearchMemoCardsRequest(owner_id="owner-1", query="", tags=(), kinds=(), include_private=False, limit=10))

    assert [hit.card.title for hit in result.hits] == ["Agent visible goal"]


def test_review_queue_prioritizes_open_loops_and_commitments():
    runtime = MemoRuntimeContract(MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, tzinfo=UTC)), storage=InMemoryMemoStorage())
    runtime.create_card(CreateMemoCardRequest("owner-1", "note", "Ordinary note", "", (), "agent_visible", "user", "u1"))
    runtime.create_card(CreateMemoCardRequest("owner-1", "open_loop", "Unclosed payment issue", "", (), "agent_visible", "user", "u1"))
    runtime.create_card(CreateMemoCardRequest("owner-1", "commitment", "Call customer", "", (), "agent_visible", "user", "u1"))

    queue = runtime.get_review_queue(GetMemoReviewQueueRequest(owner_id="owner-1", limit=2, include_private=True))

    assert [item.reason for item in queue.items] == ["open_loop", "commitment"]


def test_record_review_action_marks_card_reviewed_and_records_event():
    runtime = MemoRuntimeContract(MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, tzinfo=UTC)), storage=InMemoryMemoStorage())
    card = runtime.create_card(CreateMemoCardRequest("owner-1", "open_loop", "Unclosed payment issue", "", (), "agent_visible", "user", "u1"))

    item = runtime.record_review_action(
        RecordMemoReviewActionRequest(
            owner_id="owner-1",
            card_id=card.id,
            action="mark_reviewed",
            actor_type="user",
            actor_id="u1",
            trace_id="trace-review",
            idempotency_key="review-1",
        )
    )
    replayed = runtime.record_review_action(
        RecordMemoReviewActionRequest(
            owner_id="owner-1",
            card_id=card.id,
            action="mark_reviewed",
            actor_type="user",
            actor_id="u1",
            trace_id="trace-review",
            idempotency_key="review-1",
        )
    )

    assert item.status == "reviewed"
    assert replayed.id == item.id
    assert runtime.get_card(GetMemoCardRequest(owner_id="owner-1", card_id=card.id)).review_count == 1
    assert [event.event_type for event in runtime.storage.events][-1] == "review.mark_reviewed"
```

- [ ] **Step 2: Implement deterministic search and review modules**

Create `/data/projects/coke-memo-runtime/memo_runtime/search.py`:

```python
from __future__ import annotations

from memo_runtime.models import MemoCard, MemoSearchHit, MemoSearchResult


def search_cards(cards: tuple[MemoCard, ...], *, query: str, tags: tuple[str, ...], kinds: tuple[str, ...], include_private: bool, limit: int) -> MemoSearchResult:
    query_text = query.strip().lower()
    tag_set = {tag.lower() for tag in tags}
    hits: list[MemoSearchHit] = []
    for card in cards:
        if card.lifecycle != "active":
            continue
        if card.visibility == "private" and not include_private:
            continue
        if kinds and card.kind not in kinds:
            continue
        if tag_set and not tag_set.intersection({tag.lower() for tag in card.tags}):
            continue
        haystack = f"{card.title}\n{card.body}".lower()
        score = 1.0
        reasons: list[str] = []
        if query_text:
            if query_text not in haystack:
                continue
            score += 2.0
            reasons.append("keyword")
        if tag_set:
            score += 1.0
            reasons.append("tag")
        hits.append(MemoSearchHit(card=card, score=score, reasons=tuple(reasons)))
    return MemoSearchResult(hits=tuple(sorted(hits, key=lambda hit: (-hit.score, hit.card.updated_at))[:limit]))
```

Create `/data/projects/coke-memo-runtime/memo_runtime/review.py` with a
`build_review_queue(cards, owner_id, now, limit, include_private)` function
that assigns base reasons in this order: `open_loop`, `commitment`, `goal`,
`blocker`, `reflection`, `note`, `preference`, `fact`.

- [ ] **Step 3: Wire review methods into the contract**

Modify `/data/projects/coke-memo-runtime/memo_runtime/contract.py` to add:

```python
@dataclass(frozen=True)
class MemoReviewQueue:
    items: tuple[MemoReviewItem, ...]
```

The review request dataclasses were created in Task 2. Implement
`get_review_queue()` by calling `review.build_review_queue()`.
Implement `record_review_action()` so `mark_reviewed` increments
`review_count`, updates `last_reviewed_at`, writes a `review.mark_reviewed`
event, and supports idempotency replay. Implement `dismiss` as a review event
without changing `review_count`.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_search_review.py tests/test_contract_cards.py -q
```

Expected: all tests pass.

Commit:

```bash
git add memo_runtime tests
git commit -m "feat: add memo search and review queue"
```

## Task 5: Add Proposal Lifecycle

**Files:**

- Create: `/data/projects/coke-memo-runtime/memo_runtime/proposals.py`
- Modify: `/data/projects/coke-memo-runtime/memo_runtime/contract.py`
- Modify: `/data/projects/coke-memo-runtime/memo_runtime/storage/memory.py`
- Test: `/data/projects/coke-memo-runtime/tests/test_proposals.py`

- [ ] **Step 1: Write proposal lifecycle tests**

Create `/data/projects/coke-memo-runtime/tests/test_proposals.py`:

```python
from datetime import UTC, datetime

from memo_runtime.config import MemoRuntimeConfig
from memo_runtime.contract import AcceptMemoProposalRequest, CreateMemoProposalRequest, MemoRuntimeContract, RejectMemoProposalRequest
from memo_runtime.errors import MemoProposalNotPending
from memo_runtime.storage.memory import InMemoryMemoStorage


def test_create_and_accept_create_card_proposal():
    runtime = MemoRuntimeContract(MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, tzinfo=UTC)), storage=InMemoryMemoStorage())
    proposal = runtime.create_proposal(CreateMemoProposalRequest(
        owner_id="owner-1",
        proposal_type="create_card",
        candidate_card={"kind": "reflection", "title": "User wants review", "body": "Browse and review are core.", "tags": ["memo"], "visibility": "agent_visible"},
        target_card_id=None,
        rationale="User explicitly elevated review workspace.",
        created_by="agent",
        trace_id="trace-1",
        idempotency_key="proposal-1",
    ))

    card = runtime.accept_proposal(AcceptMemoProposalRequest(owner_id="owner-1", proposal_id=proposal.id, actor_type="user", actor_id="u1"))

    assert card.kind == "reflection"
    assert card.title == "User wants review"


def test_rejected_proposal_cannot_be_accepted():
    runtime = MemoRuntimeContract(MemoRuntimeConfig(clock=lambda: datetime(2026, 5, 17, tzinfo=UTC)), storage=InMemoryMemoStorage())
    proposal = runtime.create_proposal(CreateMemoProposalRequest("owner-1", "create_card", {"kind": "note", "title": "X", "body": "", "tags": [], "visibility": "agent_visible"}, None, "reason", "agent"))
    runtime.reject_proposal(RejectMemoProposalRequest(owner_id="owner-1", proposal_id=proposal.id, actor_type="user", actor_id="u1"))

    try:
        runtime.accept_proposal(AcceptMemoProposalRequest(owner_id="owner-1", proposal_id=proposal.id, actor_type="user", actor_id="u1"))
    except MemoProposalNotPending:
        pass
    else:
        raise AssertionError("rejected proposal should not be accepted")
```

- [ ] **Step 2: Implement proposal transitions**

The proposal request dataclasses were created in Task 2. Implement
`create_proposal`, `accept_proposal`, and `reject_proposal`.

For `create_card` proposals, `accept_proposal` must validate the candidate
fields and call the same internal card-creation path as user-created cards.

- [ ] **Step 3: Run tests and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest tests/test_proposals.py tests/test_contract_cards.py tests/test_search_review.py -q
```

Expected: all tests pass.

Commit:

```bash
git add memo_runtime tests
git commit -m "feat: add memo proposal lifecycle"
```

## Task 6: Add Postgres Storage And Migration

**Files:**

- Create: `/data/projects/coke-memo-runtime/memo_runtime/storage/migrations/001_initial.sql`
- Create: `/data/projects/coke-memo-runtime/memo_runtime/storage/postgres.py`
- Test: `/data/projects/coke-memo-runtime/tests/test_postgres_schema.py`

- [ ] **Step 1: Add schema file**

Create `/data/projects/coke-memo-runtime/memo_runtime/storage/migrations/001_initial.sql` with tables:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memo_cards (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}',
  visibility TEXT NOT NULL,
  lifecycle TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  archived_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  last_reviewed_at TIMESTAMPTZ,
  review_count INTEGER NOT NULL DEFAULT 0,
  confidence DOUBLE PRECISION,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS memo_events (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  card_id TEXT,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL,
  actor_id TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  trace_id TEXT,
  idempotency_key TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS memo_events_owner_idempotency_idx
  ON memo_events(owner_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS memo_mutations (
  owner_id TEXT NOT NULL,
  operation TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  result_type TEXT NOT NULL,
  result_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (owner_id, operation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS memo_cards_owner_lifecycle_updated_idx
  ON memo_cards(owner_id, lifecycle, updated_at DESC);

CREATE INDEX IF NOT EXISTS memo_cards_owner_visibility_idx
  ON memo_cards(owner_id, visibility);

CREATE TABLE IF NOT EXISTS memo_embeddings (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  card_id TEXT NOT NULL REFERENCES memo_cards(id),
  embedding_model TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding vector(1536),
  indexed_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS memo_embeddings_owner_card_idx
  ON memo_embeddings(owner_id, card_id);

CREATE TABLE IF NOT EXISTS memo_proposals (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  proposal_type TEXT NOT NULL,
  status TEXT NOT NULL,
  candidate_card JSONB NOT NULL,
  target_card_id TEXT,
  rationale TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  decided_at TIMESTAMPTZ,
  trace_id TEXT
);

CREATE INDEX IF NOT EXISTS memo_proposals_owner_status_idx
  ON memo_proposals(owner_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS memo_review_items (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  card_id TEXT NOT NULL REFERENCES memo_cards(id),
  reason TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  reviewed_at TIMESTAMPTZ,
  next_eligible_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS memo_review_items_owner_status_idx
  ON memo_review_items(owner_id, status, created_at DESC);
```

- [ ] **Step 2: Add a schema text test**

Create `/data/projects/coke-memo-runtime/tests/test_postgres_schema.py`:

```python
from pathlib import Path


def test_initial_schema_contains_core_tables_and_indexes():
    sql = Path("memo_runtime/storage/migrations/001_initial.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS memo_cards" in sql
    assert "CREATE TABLE IF NOT EXISTS memo_events" in sql
    assert "CREATE TABLE IF NOT EXISTS memo_embeddings" in sql
    assert "CREATE TABLE IF NOT EXISTS memo_proposals" in sql
    assert "CREATE TABLE IF NOT EXISTS memo_mutations" in sql
    assert "CREATE TABLE IF NOT EXISTS memo_review_items" in sql
    assert "memo_events_owner_idempotency_idx" in sql
    assert "memo_cards_owner_lifecycle_updated_idx" in sql
```

- [ ] **Step 3: Implement Postgres storage**

Create `/data/projects/coke-memo-runtime/memo_runtime/storage/postgres.py` with
`PostgresMemoStorage(database_url: str)`. It must implement the same methods
as `MemoStorage`, map rows to dataclasses, and never expose raw SQL callers to
Coke. Use parameterized psycopg queries only. `replay_mutation()` and
`record_mutation()` must use `memo_mutations`, not the event table, so retries
can return the original card/proposal/review item.

- [ ] **Step 4: Add gated Postgres contract tests**

Create `/data/projects/coke-memo-runtime/tests/test_postgres_contract.py`:

```python
import os

import pytest

from memo_runtime.config import MemoRuntimeConfig
from memo_runtime.contract import (
    ArchiveMemoCardRequest,
    CreateMemoCardRequest,
    DeleteMemoCardRequest,
    MemoRuntimeContract,
    UpdateMemoCardRequest,
)
from memo_runtime.storage.postgres import PostgresMemoStorage


pytestmark = pytest.mark.skipif(
    not os.environ.get("MEMO_RUNTIME_DATABASE_URL"),
    reason="MEMO_RUNTIME_DATABASE_URL is not configured",
)


def test_postgres_storage_satisfies_card_contract():
    storage = PostgresMemoStorage(os.environ["MEMO_RUNTIME_DATABASE_URL"])
    storage.apply_migrations()
    storage.clear_owner("owner-pg-test")
    runtime = MemoRuntimeContract(MemoRuntimeConfig(), storage=storage)

    card = runtime.create_card(
        CreateMemoCardRequest(
            "owner-pg-test",
            "goal",
            "Postgres memo contract",
            "Verify real SQL storage.",
            ("postgres",),
            "agent_visible",
            "user",
            "u1",
            idempotency_key="pg-create-1",
        )
    )
    replayed = runtime.create_card(
        CreateMemoCardRequest(
            "owner-pg-test",
            "goal",
            "Postgres memo contract",
            "Verify real SQL storage.",
            ("postgres",),
            "agent_visible",
            "user",
            "u1",
            idempotency_key="pg-create-1",
        )
    )
    updated = runtime.update_card(
        UpdateMemoCardRequest("owner-pg-test", card.id, "Updated", None, None, None, "user", "u1")
    )
    archived = runtime.archive_card(ArchiveMemoCardRequest("owner-pg-test", card.id, "user", "u1"))
    deleted = runtime.delete_card(DeleteMemoCardRequest("owner-pg-test", card.id, "user", "u1"))

    assert replayed.id == card.id
    assert updated.title == "Updated"
    assert archived.lifecycle == "archived"
    assert deleted.lifecycle == "deleted"
```

`PostgresMemoStorage.apply_migrations()` runs packaged SQL migrations.
`clear_owner()` is a test helper that deletes rows for the named owner only.
Do not claim production Postgres storage is complete unless this gated test
passes in an environment with `MEMO_RUNTIME_DATABASE_URL`.

- [ ] **Step 5: Run package tests and commit**

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest -q
```

Expected: all package tests pass.

Commit:

```bash
git add memo_runtime tests
git commit -m "feat: add postgres memo storage"
```

## Task 7: Add Package Dependency Wiring

**Files:**

- Modify: `/data/projects/coke/.gitmodules`
- Modify: `/data/projects/coke/requirements.txt` or project-local developer setup docs if needed.

- [ ] **Step 1: Add the memo runtime as a pinned local dependency**

Use a local submodule after creating the package repository:

```bash
cd /data/projects/coke
git submodule add /data/projects/coke-memo-runtime memo-runtime
```

Expected: `.gitmodules` gains `path = memo-runtime`.

- [ ] **Step 2: Install the package into Coke's virtualenv**

Run:

```bash
cd /data/projects/coke
.venv/bin/python -m pip install -e memo-runtime
```

Expected: pip reports an editable install for `coke-memo-runtime`.

- [ ] **Step 3: Verify Coke can import the package**

Run:

```bash
cd /data/projects/coke
.venv/bin/python -c "from memo_runtime.contract import MemoRuntimeContract; print(MemoRuntimeContract.__name__)"
```

Expected: `MemoRuntimeContract`.

- [ ] **Step 4: Commit dependency wiring**

```bash
cd /data/projects/coke
git add .gitmodules memo-runtime
git commit -m "chore(memo): add memo runtime package dependency"
```

## Task 8: Add Coke Adapter Boundary

**Files:**

- Create: `/data/projects/coke/agent/agno_agent/capabilities/memo.py`
- Create: `/data/projects/coke/tests/unit/agent/test_memo_capability_adapter.py`

- [ ] **Step 1: Add a failing Coke adapter test**

Create `/data/projects/coke/tests/unit/agent/test_memo_capability_adapter.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_memo_capability_adapter_calls_contract_search_only():
    from agent.agno_agent.capabilities.memo import MemoCapabilityPort, RuntimeOwnerMapper

    class RecordingContract:
        def __init__(self):
            self.calls = []

        def search_cards(self, request):
            self.calls.append(("search_cards", request))
            return {"hits": []}

    contract = RecordingContract()
    port = MemoCapabilityPort(
        contract_factory=lambda _context: contract,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = await port.run(
        "what did I say about memo review?",
        run_context=type("Context", (), {"user_id": "owner-1"})(),
        args={"query": "memo review", "limit": 5},
    )

    assert result.ok is True
    assert contract.calls[0][0] == "search_cards"
    assert contract.calls[0][1].owner_id == "owner-1"


@pytest.mark.asyncio
async def test_memo_capability_adapter_fails_closed_without_owner():
    from agent.agno_agent.capabilities.memo import MemoCapabilityPort, RuntimeOwnerMapper

    port = MemoCapabilityPort(
        contract_factory=lambda _context: None,
        owner_mapper=RuntimeOwnerMapper(),
    )

    result = await port.run(
        "memo review",
        run_context=type("Context", (), {})(),
        args={"query": "memo review"},
    )

    assert result.ok is False
    assert result.error == "memo_owner_required"
```

- [ ] **Step 2: Verify the adapter test fails**

Run:

```bash
cd /data/projects/coke
.venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -q
```

Expected: FAIL because `agent.agno_agent.capabilities.memo` does not exist.

- [ ] **Step 3: Implement the adapter**

Create `/data/projects/coke/agent/agno_agent/capabilities/memo.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from agent.agno_agent.runtime.result import CapabilityResult


class RuntimeOwnerMapper:
    def owner_id(self, run_context: Any) -> str:
        for attr in ("owner_user_id", "customer_id", "user_id"):
            value = str(getattr(run_context, attr, "") or "").strip()
            if value:
                return value
        return ""


class MemoCapabilityPort:
    def __init__(self, *, contract_factory: Callable[[Any], Any], owner_mapper: RuntimeOwnerMapper | None = None) -> None:
        self.contract_factory = contract_factory
        self.owner_mapper = owner_mapper or RuntimeOwnerMapper()

    async def run(self, input_message: str, run_context: Any, args: dict[str, Any]) -> CapabilityResult:
        from memo_runtime.contract import SearchMemoCardsRequest

        query = str(args.get("query") or input_message or "").strip()
        limit = int(args.get("limit") or 5)
        owner_id = self.owner_mapper.owner_id(run_context)
        if not owner_id:
            return CapabilityResult(
                name="memo",
                ok=False,
                content={"summary": "Memo owner identity is missing."},
                error="memo_owner_required",
            )
        contract = self.contract_factory(run_context)
        result = contract.search_cards(
            SearchMemoCardsRequest(
                owner_id=owner_id,
                query=query,
                tags=(),
                kinds=(),
                include_private=False,
                limit=limit,
            )
        )
        return CapabilityResult(
            name="memo",
            ok=True,
            content={"hits": getattr(result, "hits", [])},
            metadata={"requires_response_synthesis": True},
        )
```

- [ ] **Step 4: Run the adapter test and commit**

Run:

```bash
cd /data/projects/coke
.venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -q
```

Expected: `1 passed`.

Commit only Coke adapter files:

```bash
git add agent/agno_agent/capabilities/memo.py tests/unit/agent/test_memo_capability_adapter.py
git commit -m "feat(agent): add memo capability adapter boundary"
```

## Task 9: Add Docs And Verification Evidence

**Files:**

- Modify: `/data/projects/coke/docs/ARCHITECTURE.md`
- Modify: `/data/projects/coke/docs/product-specs/FEATURE_TREE.md`
- Create: `/data/projects/coke/artifacts/evidence/2026-05-17-memo-runtime-contract.md`

- [ ] **Step 1: Document the architecture**

In `/data/projects/coke/docs/ARCHITECTURE.md`, add a short memo section near
the agent capability section:

```markdown
The Memo Runtime is a headless embedded Python package consumed through a
Memo Runtime Contract. Coke agent adapters and future frontend/API adapters
must call the contract instead of writing memo storage directly. The package
owns memo cards, events, proposals, search, review, and storage migrations;
frontend implementation is intentionally separate.
```

- [ ] **Step 2: Document product surface discovery**

In `/data/projects/coke/docs/product-specs/FEATURE_TREE.md`, add a memo entry:

```markdown
- Memo runtime contract
  - headless embedded package: `memo-runtime/`
  - Coke agent adapter: `agent/agno_agent/capabilities/memo.py`
  - product behavior: memo cards, search, review queue, and agent proposals
  - frontend implementation is a consumer and must not own memo business rules
```

- [ ] **Step 3: Record verification evidence**

Create `/data/projects/coke/artifacts/evidence/2026-05-17-memo-runtime-contract.md`:

```markdown
# Memo Runtime Contract Verification

Date: 2026-05-17

## Commands

- `cd /data/projects/coke-memo-runtime && python -m pytest -q`
- `cd /data/projects/coke && .venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -q`
- `cd /data/projects/coke && zsh scripts/check`
- `cd /data/projects/coke && zsh scripts/suggest-verification --base HEAD~1`
- `cd /data/projects/coke && zsh scripts/review-trigger --base HEAD~1`

## Results

- `cd /data/projects/coke-memo-runtime && python -m pytest -q`: record actual
  result here after execution.
- `cd /data/projects/coke && .venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -q`:
  record actual result here after execution.
- `cd /data/projects/coke && zsh scripts/check`: record actual result here
  after execution.
- `cd /data/projects/coke && zsh scripts/suggest-verification --base HEAD~1`:
  record actual result here after execution.
- `cd /data/projects/coke && zsh scripts/review-trigger --base HEAD~1`:
  record actual result here after execution.

Do not mark the memo runtime complete without fresh package and Coke adapter
verification.
```

- [ ] **Step 4: Run repo checks and commit**

Run:

```bash
cd /data/projects/coke
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: `scripts/check` passes. The verification suggestion and review
trigger outputs should be copied into the evidence file.

Commit:

```bash
git add docs/ARCHITECTURE.md docs/product-specs/FEATURE_TREE.md artifacts/evidence/2026-05-17-memo-runtime-contract.md
git commit -m "docs(memo): wire memo runtime contract surface"
```

## Final Verification

Run:

```bash
cd /data/projects/coke-memo-runtime
python -m pytest -q

cd /data/projects/coke
.venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -q
zsh scripts/check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected evidence:

- memo-runtime package tests pass
- Coke adapter test passes
- repo structure checks pass
- verification routing is captured in the evidence file
- review-trigger output is either below threshold or explicitly handed to a
  human reviewer

## Implementation Notes

- Keep frontend implementation out of `coke-memo-runtime`.
- Keep direct storage writes out of Coke adapters.
- Keep memo and reminder objects separate.
- Store provenance in events and proposal records, not first-class
  `source_*` card fields.
- Do not migrate legacy Coke `embeddings` during this plan.
