# Memo Runtime Contract Design

**Status:** draft for review
**Date:** 2026-05-17
**Owner:** Codex

## Summary

Build a headless flomo-like memo system for Coke as an embedded Python runtime
package. The memo system is not a frontend, not a Reminder variant, and not a
generic action platform. It is a domain runtime for storing, finding, editing,
reviewing, and agent-enriching durable personal memos.

The intended product shape is:

```text
Frontend / Coke agent / future MCP
  -> adapter
  -> Memo Runtime Contract
  -> Memo runtime core
  -> storage, search index, review queue, proposal/event log
```

The web surface is a high-priority consumer because browsing, searching,
editing, and reviewing memos are part of how the human and the agent interact.
The memo-runtime repository should still stay headless: it provides contract,
service, storage, search, and review behavior; frontend implementation lives in
the frontend/gateway surface.

## Product Intent

The system should borrow the useful product loop from flomo:

- capture small pieces of durable personal context
- make them easy to browse and search later
- bring selected old memos back for review
- let the user correct, enrich, and reuse them

For Coke, the differentiator is that the agent participates in the same memo
substrate. The agent can suggest memos, retrieve relevant memos, propose
connections, and help review old memos. User confirmation and editability are
part of the product, not an afterthought.

The first version prioritizes:

1. browse and search
2. review and resurfacing
3. simple capture and edit
4. agent suggestions that stay reviewable

## Relationship To Reminder

Memo and Reminder are separate domain objects.

Reminder means:

```text
at a future time, bring something back into a context
```

Memo means:

```text
durable personal context that can be captured, found, edited, and reviewed
```

Do not model memo as a reminder, and do not model reminder as a memo. A later
adapter may let a user create a reminder while viewing a memo, or let a
reminder carry a memo reference in metadata or an event relation, but that is
not the core memo model.

Provenance should not become first-class business identity fields such as
`source_memo_id` or generic `source_*` columns. If the system needs to
preserve where a card came from, store that in memo events, proposal records,
or relation metadata. The core card should read as a product object, not an
audit envelope.

## Runtime Boundary

The memo system should live in a separate Python package repository, embedded
by Coke at runtime.

It should not run a separate service in the first version:

- no independent daemon
- no independent port
- no queue worker requirement
- no frontend bundle

The package owns its storage implementation and schema. Callers provide
configuration, not repositories:

```text
MemoRuntimeConfig(
    database_url=...,
    embedding_provider=...,
    clock=...,
)
```

Callers must not implement storage rules. Coke, frontend APIs, future MCP
tools, and any CLI adapter should all call the same Memo Runtime Contract.

The first Coke integration pins the package as a local submodule at
`memo-runtime/` and installs it into Coke's Python environment with
`pip install -e memo-runtime`. Adapter tests must not depend on sibling
directory imports or implicit `PYTHONPATH` behavior.

## Contract Shape

The first contract should expose a small synchronous Python API:

```python
class MemoRuntimeContract:
    def create_card(self, request: CreateMemoCardRequest) -> MemoCard: ...
    def update_card(self, request: UpdateMemoCardRequest) -> MemoCard: ...
    def archive_card(self, request: ArchiveMemoCardRequest) -> MemoCard: ...
    def delete_card(self, request: DeleteMemoCardRequest) -> MemoCard: ...
    def get_card(self, request: GetMemoCardRequest) -> MemoCard: ...
    def search_cards(self, request: SearchMemoCardsRequest) -> MemoSearchResult: ...
    def get_review_queue(self, request: GetMemoReviewQueueRequest) -> MemoReviewQueue: ...
    def record_review_action(self, request: RecordMemoReviewActionRequest) -> MemoReviewItem: ...
    def create_proposal(self, request: CreateMemoProposalRequest) -> MemoProposal: ...
    def accept_proposal(self, request: AcceptMemoProposalRequest) -> MemoCard: ...
    def reject_proposal(self, request: RejectMemoProposalRequest) -> MemoProposal: ...
```

Adapters may choose which methods to expose. The web adapter needs card CRUD,
search, and review. The agent adapter needs retrieval and proposal methods.
Future MCP can expose the same contract without owning storage behavior.

## Domain Model

### MemoCard

`MemoCard` is the human-editable product object.

Fields:

- `id`
- `owner_id`
- `kind`
- `title`
- `body`
- `tags`
- `visibility`
- `lifecycle`
- `created_by`
- `created_at`
- `updated_at`
- `archived_at`
- `deleted_at`
- `last_reviewed_at`
- `review_count`
- `confidence`
- `metadata`

Allowed `kind` values:

- `note`
- `goal`
- `commitment`
- `blocker`
- `preference`
- `reflection`
- `fact`
- `open_loop`

Allowed `visibility` values:

- `private`: visible to the owner; not included in agent retrieval
- `agent_visible`: visible to the owner and eligible for agent retrieval

Allowed `lifecycle` values:

- `active`
- `archived`
- `deleted`

Allowed `created_by` values:

- `user`
- `agent`
- `import`
- `api`

Rules:

- `owner_id`, `title` or `body`, `kind`, `visibility`, and `lifecycle` are
  required.
- `deleted` cards do not appear in normal search or review results.
- `private` cards never appear in agent retrieval unless an explicit
  owner-authorized adapter operation changes visibility.
- `metadata` is for non-business extension only. It must not be required for
  normal product behavior.

### MemoEvent

`MemoEvent` is the audit and provenance layer.

Fields:

- `id`
- `owner_id`
- `card_id`
- `event_type`
- `actor_type`
- `actor_id`
- `occurred_at`
- `trace_id`
- `idempotency_key`
- `payload`

Events record creation, edits, archives, deletes, review actions, proposal
acceptance/rejection, and agent extraction context. Events are where adapter
provenance belongs.

### MemoMutationRecord

`MemoMutationRecord` stores idempotency replay state for externally repeatable
writes. It is separate from events because an idempotent retry must return the
original domain object, not merely prove that an event row exists.

Fields:

- `owner_id`
- `operation`
- `idempotency_key`
- `result_type`
- `result_id`
- `created_at`

The unique key is `(owner_id, operation, idempotency_key)`. Operations that
accept idempotency keys must check this table before mutating state and return
the recorded card, proposal, or review item when a retry repeats the same
operation.

### MemoEmbedding

`MemoEmbedding` is the semantic retrieval index.

Fields:

- `id`
- `owner_id`
- `card_id`
- `embedding_model`
- `content_hash`
- `embedding`
- `indexed_at`
- `status`
- `last_error`

Allowed `status` values:

- `ready`
- `pending`
- `failed`

The first version may generate embeddings synchronously on card writes. If
embedding generation fails, the card write should still succeed and the
embedding row should be marked `failed` or left `pending` with a durable event.

### MemoProposal

`MemoProposal` is how the agent suggests memo changes without silently
rewriting the user's memory surface.

Fields:

- `id`
- `owner_id`
- `proposal_type`
- `status`
- `candidate_card`
- `target_card_id`
- `rationale`
- `created_by`
- `created_at`
- `decided_at`
- `trace_id`

Allowed `proposal_type` values:

- `create_card`
- `update_card`
- `merge_cards`
- `add_tags`
- `review_prompt`

Allowed `status` values:

- `pending`
- `accepted`
- `rejected`
- `expired`

The first implementation must support `create_card`, `update_card`, and
`add_tags`. `merge_cards` and `review_prompt` can be modeled but do not need
full product behavior until the first review workspace is connected.

### MemoReviewItem

Review is a product primitive. It is not a notification system.

`MemoReviewItem` is a computed or persisted item that brings a card back to
the user for reflection, correction, or action.

Fields:

- `id`
- `owner_id`
- `card_id`
- `reason`
- `score`
- `status`
- `created_at`
- `reviewed_at`
- `next_eligible_at`

Allowed `status` values:

- `pending`
- `reviewed`
- `dismissed`

The first version may compute review queues on demand using card age,
`last_reviewed_at`, kind, tags, and lightweight randomness. It does not need a
separate scheduler or daily precompute worker.

## Storage

The package should own a default production storage implementation. Prefer
Postgres with `pgvector` because memo cards, events, proposals, and review
state are structured objects that need filters, ordering, constraints, and
semantic retrieval.

The package should include:

- database schema/migrations
- index definitions
- storage implementation
- test-friendly in-memory or SQLite storage only for unit tests

Coke should not implement the repository. Coke should only provide
configuration and identity mapping.

## Search Semantics

Search combines:

- owner-scoped lifecycle filtering
- keyword search over title/body/tags
- tag filters
- kind filters
- date filters
- optional semantic retrieval

Search results should return structured cards plus scoring metadata. The
agent adapter may request only `agent_visible` cards. The web adapter may
search both `private` and `agent_visible` cards for the authenticated owner.

The existing Coke `embeddings` collection is a legacy memory surface. This
design should not require reusing it. A later migration can import selected
legacy profile or history facts into memo cards, but first-version memo
behavior should not depend on that legacy collection.

## Review Semantics

The review queue should select cards that are useful to revisit, not just old.

Initial scoring inputs:

- cards not reviewed recently
- `goal`, `commitment`, `blocker`, and `open_loop` cards get a higher base
  review weight than ordinary notes
- recently edited cards are temporarily deprioritized
- archived/deleted cards are excluded
- private cards are eligible for web review but not agent retrieval

Review actions:

- `mark_reviewed`
- `dismiss`
- `edit_card`
- `accept_proposal`
- `reject_proposal`

The review system should record events so the agent can later explain why a
card was resurfaced without inventing provenance.

`record_review_action()` is a write contract, not a UI-only convenience. The
first version must support `mark_reviewed` and `dismiss` directly. If the
review action accepts or rejects a proposal, it may delegate to the proposal
contract methods, but it must still record a review event and participate in
idempotency replay.

## Adapter Requirements

### Coke Agent Adapter

The agent adapter may:

- search `agent_visible` cards for context
- create proposals for new cards or card edits
- accept an explicit user request such as "记一下" by calling `create_card`
  through the contract

The agent adapter must not:

- directly write storage
- expose private cards unless the contract request authorizes it
- silently accept proposals that materially change user memory
- turn every chat message into a memo
- infer an owner from an unauthenticated or missing runtime context

The Coke adapter must map Coke runtime identity to `owner_id` through an
explicit identity mapper. Missing owner identity fails closed with a stable
capability error; it must not issue a memo query with an empty owner.

### Web/API Adapter

The web/API adapter may:

- expose timeline, search, tag filters, card detail, edit, archive, delete
- expose review queue and review actions
- expose pending agent proposals for user acceptance/rejection

The web/API adapter must not:

- own search ranking rules
- own review selection rules
- bypass contract visibility checks
- write storage directly

### Future MCP Or CLI Adapter

Future adapters should be thin wrappers over the same contract. They should
not introduce new product behavior unless the contract is updated first.

## Error And Safety Model

The contract should return stable errors:

- `memo_invalid_request`
- `memo_owner_required`
- `memo_not_found`
- `memo_permission_denied`
- `memo_conflict`
- `memo_storage_unavailable`
- `memo_embedding_failed`
- `memo_proposal_not_found`
- `memo_proposal_not_pending`

Writes should accept `trace_id` and `idempotency_key` where the caller may
retry. Idempotency must apply to externally repeatable writes such as create
card, create proposal, and review action.

All read and write methods must require `owner_id`.

## Non-Goals

- Do not implement frontend UI in the memo-runtime repository.
- Do not implement a standalone HTTP service in the first version.
- Do not implement public sharing, collaboration, backlinks, graph view, rich
  document editing, or bulk import.
- Do not migrate all existing Coke embeddings or chat history in the first
  version.
- Do not connect to Reminder Runtime Contract in the first version except
  through optional metadata/event relation design.
- Do not create a generic memory/action/workflow platform.

## Verification Strategy

The first implementation should prove:

- contract methods enforce owner scope and visibility
- storage writes produce events
- search returns owner-scoped results and excludes deleted cards
- agent retrieval excludes private cards
- review queue is deterministic enough to test with an injected clock and
  seeded random source
- review actions update card review state, create events, and support
  idempotent retry
- proposals require explicit accept/reject transitions
- Coke adapters call the Memo Runtime Contract instead of storage directly
- Postgres storage either passes the same contract tests under
  `MEMO_RUNTIME_DATABASE_URL` or is explicitly deferred from the completion
  claim

Expected verification surfaces:

- memo-runtime unit tests
- memo-runtime contract tests
- Coke adapter unit tests
- repo-OS docs checks after submodule/contract docs are added

## Implementation Decisions

- The local package repository is `/data/projects/coke-memo-runtime`.
- Coke pins it as a local submodule at `memo-runtime/` for the first
  implementation and installs it with `pip install -e memo-runtime`.
- The first migration format is raw SQL stored in the package.
- The first embedding integration is an adapter protocol with a deterministic
  test provider; production provider selection can be configured later.

These do not change the product boundary: memo-runtime stays headless,
embedded, contract-first, and owned by its own package.
