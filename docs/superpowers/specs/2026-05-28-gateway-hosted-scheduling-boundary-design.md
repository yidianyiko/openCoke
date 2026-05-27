---
status: superseded
created_at: 2026-05-28
owner: architecture
kind: design
superseded_by: 2026-05-28-direct-friendship-shared-reminders-design.md
---

# Gateway-Hosted Scheduling Boundary Design

> Superseded: this draft describes the retired pending-confirmation scheduling
> boundary. The active product contract is
> `2026-05-28-direct-friendship-shared-reminders-design.md`.

## Decision

Scheduling must become an explicit product system with a stable domain
contract. It may remain physically hosted inside the Gateway API process for
now, but it must not be owned by Gateway route handlers.

The target boundary is:

```text
Agent Runtime
  -> SchedulingCapabilityPort
  -> Scheduling HTTP adapter
  -> SchedulingDomainContract
  -> Scheduling domain services and Postgres state
  -> ReminderRuntimePort
  -> Bridge
  -> Reminder Runtime
```

Short form:

```text
Scheduling may be Gateway-hosted.
Scheduling must not be Gateway-route-owned.
```

This spec rejects two weaker alternatives:

- Do not leave the current route-shaped tool switch as the de facto Scheduling
  contract.
- Do not move the whole shared-reminder and friend graph domain into Agent
  Runtime just to make Gateway look thinner.

## Why This Is Needed

The current system already treats scheduling as an agent-facing domain:
`scheduling_domain` returns structured execution facts to the Interaction Agent,
while the agent remains responsible for language understanding, Focus,
semantic routing, and final user-visible replies.

The current implementation, however, is not cleanly expressed as a domain
contract. The Gateway internal scheduling route performs too much work:

- internal tool dispatch
- request body normalization
- friend and shared-reminder request resolution
- error mapping
- business operation selection
- direct calls into multiple scheduling services
- direct bridge/reminder-runtime projection client wiring

That makes the HTTP route look like the owner of scheduling behavior. This
conflicts with the repository's agent capability rule: tools, HTTP routes, MCP
servers, CLI commands, and web UI surfaces are adapters over a stable domain
contract; they are not separate owners of business behavior.

The 2026-05-27 production multi-pending case (see *Current Boundary
Problems*) is a concrete consequence of that ownership confusion: business
invariants, cross-turn agent state, and inbound channel metadata are each
carrying a piece of Scheduling semantics that no single layer owns. This
spec is the architectural step that closes that regression class.

## Why Gateway Hosting Is Still Defensible

Scheduling is not only Reminder behavior. It combines:

- customer identity
- public user links and link sessions
- friend requests
- active and removed friendships
- shared-reminder invitations
- shared-reminder request lifecycle state
- product notifications
- delivery-route lookup
- Reminder Runtime projections

Most of that state already belongs with Gateway/Postgres product state and the
customer/public web surfaces. Moving this entire domain into Agent Runtime would
couple the LLM worker to platform and social graph state, and would still
require it to coordinate with Gateway for customer identity, public links,
delivery routes, and product notifications.

The correct split is by system owner and contract, not by process name:

- Gateway API process may host Platform, Channel, customer API edges, and the
  Scheduling System package.
- Gateway route handlers are transport adapters.
- Scheduling domain services own social scheduling state and lifecycle rules.
- Reminder Runtime owns durable reminders, recurrence, occupied intervals,
  scheduler registration, firing, and reminder output.
- Agent Runtime owns interpretation, policy, Focus, tool selection, and final
  response synthesis.
- Bridge adapts internal HTTP requests to Coke runtime contracts and outbound
  delivery paths.

## Current Boundary Problems

### Fat Internal Scheduling Route

`gateway/packages/api/src/routes/internal-scheduling-routes.ts` should not be
the source of scheduling semantics. It currently combines auth, parsing,
operation dispatch, resolver behavior, domain calls, and response mapping.

Target rule:

```text
Route handlers may authenticate, validate transport input, call a contract
method, and serialize the contract result. They must not own lifecycle,
resolution, notification, projection, idempotency, or privacy rules.
```

### Route-Local Domain Resolution

Friend names, shared-reminder request ids, actor roles, status checks, and
ambiguous matches must be resolved by Scheduling domain services, not by Hono
route code.

Resolution can remain server-side when it requires current Postgres friend
state. The important constraint is that the resolver is a domain primitive with
typed outcomes, not route-local string matching.

### Agent/Gateway Contract Drift

The agent-side Scheduling capability and Gateway internal route duplicate tool
names, field names, read/write classification, privacy handling, and error
codes. This already created a class of bugs where the agent sent a field shape
that the Gateway internal tool did not accept.

The target contract must make drift visible through tests or fixtures.

### Storage Shape Leakage

Agent-facing responses should not expose Gateway/Prisma table shape as the
contract. Names such as `accountAId`, `accountBId`, `requesterAccountId`, or
`targetAccountId` may be implementation fields, but the agent contract should
return stable domain DTOs.

The Interaction Agent may know "this is an incoming friend request from Bob" or
"this shared reminder request is pending for the current invitee." It should not
need to understand Postgres relationship columns.

### Distributed Saga Risk

Shared reminder creation and acceptance span:

- Postgres shared-reminder request rows
- Postgres reminder projection rows
- Mongo Reminder Runtime records
- product notification rows
- outbound delivery through Gateway/Channel

This is the highest-risk area. The architecture must make projection,
reconciliation, idempotency, notification, and cleanup ports explicit.

### Boundary Reference Drift

Several canonical docs still point to
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`,
but that file is not present in the current checkout. Implementation of this
design must not add new dependencies on that missing file. It must either
replace those references with the current canonical boundary documents
(`docs/design-docs/coke-working-contract.md`, `docs/design-docs/interface-contract.md`,
and this spec) or restore the missing spec in the same change if it is still
intended to be canonical.

### Duplicate Pending Invites Can Accumulate

Production case (2026-05-27): a single requester landed three near-identical
`create_shared_reminder` requests within ninety minutes. All three rows
persisted in `shared_reminder_requests` with
`status = pending_invitee_confirmation`, byte-identical `title`, `fire_at`,
`timezone`, and `duration_minutes`, differing only by `idempotency_key`,
which the agent hashes per turn rather than per business intent.

The current unique index
`(requester_account_id, invitee_account_id, idempotency_key)` deduplicates
retries of the same agent turn but not semantic duplicates from different
agent turns or different concurrent worker sessions. The result is an
unbounded multi-pending state on the invitee side and a downstream
fail-closed loop in the agent.

This is a transactional invariant. It cannot be enforced reliably at the
language layer because concurrent worker processes do not see each other's
in-flight intent. It must live in the contract and be enforced by a
database constraint.

### Cross-Turn Disambiguation Has No Owner

When `shared_reminder_requests` carries more than one
`pending_invitee_confirmation` row for an invitee, the Channel/Bridge
inbound pipeline bundles every candidate into
`product_notification.candidates` with `ambiguity = "multi_pending"`. The
agent rebuilds Focus from that bundle on every inbound turn, and the LLM
Focus interpreter prompt instructs the model to return `ambiguous` for any
multi-candidate Focus. The user is asked to pick, the user picks ("1",
"23:01 那条"), the next turn sees the same multi_pending Focus and asks the
same question again.

The missing concept is a stable per-conversation handle for "the agent is
currently disambiguating among this candidate set." Nothing owns it today:

- Gateway exposes raw pending state through a Channel-side notification
  pipe, not through the Scheduling contract.
- Agent session storage exists but does not carry a disambiguation phase.
- The Focus interpreter prompt does not allow resolving ordinal, time, or
  summary references to a concrete candidate handle.

### Inbound Notification Pipe Bypasses The Scheduling Contract

`product_notification` is a Channel/inbound metadata channel. It currently
carries Scheduling state (`request_id`, `candidates`, `ambiguity`) directly
to the agent, which means Channel-side bundling is acting as the agent's
view of Scheduling.

This is inverted: Scheduling owns those semantics. Agent-facing focus and
candidate resolution must be requested from the Scheduling contract by
stable handle, not reconstructed from inbound channel metadata.

### Bulk Action Vocabulary Missing

Contract operations today are strictly singular: `acceptSharedReminder`,
`rejectSharedReminder`, `cancelSharedReminder` take one `request_id`. The
common user utterance "全部确认" / "all decline" cannot be expressed as a
single domain operation; the agent would have to emit N calls and reconcile
N partial outcomes in user-visible text, with no atomic guarantee. The
contract must offer bulk variants so the LLM has a faithful target for that
intent.

## Target Component Shape

### SchedulingDomainContract

Add a typed facade under `gateway/packages/api/src/scheduling/`, for example:

```text
gateway/packages/api/src/scheduling/runtime-contract.ts
```

The contract owns stable operations such as:

- `getUserLink`
- `resetUserLink`
- `disableUserLink`
- `sendFriendRequestByUserLinkCode`
- `listFriendRequests`
- `acceptFriendRequest`
- `rejectFriendRequest`
- `cancelFriendRequest`
- `listFriends`
- `removeFriendship`
- `listFriendCalendarFacts`
- `createSharedReminder`
- `listSharedReminders`
- `listPendingSharedReminders`
- `acceptSharedReminder`
- `rejectSharedReminder`
- `cancelSharedReminder`
- `retryProductNotifications`

Each method must define:

- authenticated actor
- request DTO
- response DTO
- stable error codes
- idempotency behavior for writes
- privacy constraints
- audit or event expectations where relevant
- projection side effects where relevant

The initial implementation may delegate to the existing service modules. The
first goal is to establish a clear facade and move route-level semantics behind
it, not to rewrite every service at once.

### HTTP Adapters

`customer-scheduling-routes.ts` and `internal-scheduling-routes.ts` become thin
adapters.

Allowed responsibilities:

- authenticate customer or internal caller
- parse JSON
- validate transport-level field presence and primitive types
- map route parameters into contract requests
- call `SchedulingDomainContract`
- serialize result and HTTP status

Forbidden responsibilities:

- direct domain table queries
- request lifecycle transitions
- reminder projection creation or cleanup
- product notification content construction
- friend or shared-reminder ambiguity policy
- business idempotency rules
- privacy filtering beyond transport serialization

### Agent Scheduling Client

The Python agent side should depend on a Scheduling contract client, not a
generic Gateway client. The HTTP endpoint can remain in Gateway, but naming and
tests should reflect the ownership:

```text
SchedulingCapabilityPort
  -> SchedulingContractClient
  -> /api/internal/scheduling/...
```

The agent port may add trusted runtime context:

- `customer_id`
- `conversation_id`
- `platform`
- `timezone`
- `idempotency_key`
- trace or correlation metadata

The agent port must not encode Gateway storage rules. It should convert
contract results into `DomainExecutionResult` facts for the Interaction Agent.

### Reminder Runtime Port

Scheduling may create, cancel, or query reminders only through a
`ReminderRuntimePort`.

Scheduling must not write Mongo reminder documents, scheduler jobs, or reminder
runtime state directly. Reminder Runtime remains the owner of:

- visible reminder creation and mutation
- reminder lifecycle
- recurrence
- occupied interval expansion
- firing
- output target behavior

### Notification Port

Scheduling owns the product event intent: who should be notified, which product
action is available, and which scheduling request the notification refers to.

Channel/Gateway outbound owns transport delivery.

The notification boundary should be explicit:

```text
Scheduling event
  -> ProductNotificationPort
  -> product_notifications row
  -> Gateway outbound / Channel dispatch
```

This keeps product notification semantics out of route handlers while keeping
provider delivery out of Scheduling.

### Business-Key Idempotency For createSharedReminder

`createSharedReminder` must enforce a business-key uniqueness rule, not only
a per-turn `idempotency_key`.

Required behavior:

- For rows in status `pending_invitee_confirmation`, the tuple
  `(requester_account_id, invitee_account_id, title, fire_at, timezone,
  duration_minutes)` must be unique.
- The constraint must be enforced by a database unique index on
  `shared_reminder_requests` (partial index on the pending state), so
  concurrent worker processes cannot insert duplicates. Because PostgreSQL
  treats `NULL` values as distinct in unique indexes, the index must normalize
  nullable duration before comparison, for example with
  `COALESCE(duration_minutes, -1)` or an equivalent generated key column.
- On collision, `createSharedReminder` must return the existing pending
  request as a deterministic success (idempotent upsert), with a DTO field
  that signals "already pending" so the agent can shape its reply without
  claiming a fresh create.
- `idempotency_key` remains available for replay deduplication of the same
  agent turn. It is no longer the only line of defense.
- The accept/reject/cancel transitions must clear the row out of the pending
  partial index in the same transaction that updates `status`, so a new
  invitation with the same business key after rejection or cancellation is
  not blocked by a stale unique row.

This rule is part of the contract, not an implementation detail. Phase 1
fixtures must cover it.

### Agent Focus Binding Contract

The Scheduling contract must own a stable, agent-callable focus resolution
that replaces ad-hoc reconstruction from `product_notification`.
Scheduling must persist focus bindings and candidate handles in Postgres-owned
Scheduling state or derive them from a Postgres-backed binding row. Agent
Runtime may persist only the active conversation's selected `focus_token`,
offered handles, and rendered text in `agent_sessions`; it must not be the
authority that mints or validates Scheduling handles.

Required shape (DTO names are illustrative; final names belong to the
implementation plan):

```text
resolveAgentFocus(actor: AccountId, conversation: ConversationKey)
  -> AgentFocusBinding {
       focus_token: opaque, stable for as long as the binding is valid
       state: "single" | "multi_pending" | "none_actionable" | "stale"
       candidates: list of CandidateDescriptor {
         handle:       opaque stable id (not a Postgres column)
         kind:         "shared_reminder_request" | "friend_request" | ...
         summary:      domain DTO with title, when, counterparty,
                       viewer-local fields
         offered_at:   timestamp this candidate joined the binding
       }
       expires_at: when the binding goes stale
     }

bindAgentFocusSelection(focus_token, handle)
  -> AgentFocusBindingOutcome {
       ok:               boolean
       resolved_kind:    string
       resolved_handle:  string
       conflict_reason?: "already_consumed" | "expired" | "unknown_handle"
     }
```

`focus_token` is the cross-turn anchor. The Scheduling contract guarantees
optimistic concurrency on `bindAgentFocusSelection`: if any other actor
consumed the same candidate (accept, reject, cancel, expiry) between the
binding being offered and the selection being submitted, the call fails
with a typed conflict reason and the agent must re-render focus.

Inbound `product_notification` may still carry a low-cardinality hint
(e.g. "you have N actionable items"), but the agent must not treat its
payload as the source of truth for actionable focus. Focus is obtained by
calling the contract.

### Disambiguation Session State In Agent Runtime

`agent_sessions` must persist disambiguation state across turns:

```text
DisambiguationSession {
  focus_token:           opaque, from Scheduling contract
  offered_handles:       list of handle IDs surfaced to the user this turn
  offered_summary_text:  the visible enumeration that was shown
  expected_action:       "accept" | "reject" | "cancel" | "bulk_accept" | ...
  expires_at:            mirrors the binding expiry from the contract
}
```

When a `DisambiguationSession` is present, the semantic interpreter prompt
must be allowed to resolve ordinal references ("1", "第一条"), delivery-time
references ("23:01 那条"), or summary-text references ("数学课那条")
against `offered_handles`, returning the matched `handle` in `args` instead
of `ambiguous`. The interpreter still returns `ambiguous` when the
utterance does not unambiguously match a single offered handle.

Ordinal, time, and summary-text matching are language responsibilities and
must remain LLM responsibilities. They must not be encoded as Python regex
or keyword routing in agent runtime. The session state is the
non-LLM scaffolding the interpreter binds against; the matching itself stays
in the model.

`DisambiguationSession` expiry must mirror the Scheduling focus binding
expiry so that a stale "接受" five hours later does not silently bind to a
candidate set the user has forgotten about.

### Bulk Variants On The Contract

Add bulk-shaped methods so the agent has a faithful target for "全部 X"
intents:

- `acceptPendingSharedRemindersFrom(invitee: AccountId,
  requester_filter?)`
- `rejectPendingSharedRemindersFrom(invitee: AccountId,
  requester_filter?)`
- `cancelPendingSharedRemindersFor(requester: AccountId,
  invitee_filter?)`

Bulk operations must:

- be atomic per candidate (each candidate either fully transitions or is
  reported as conflicted), but not necessarily atomic across the whole
  batch.
- return per-handle outcome arrays so the agent can produce a faithful
  summary ("3 confirmed, 1 already expired") instead of claiming a uniform
  result.
- reuse the same focus binding handles as single-candidate operations, so
  the agent does not maintain a separate state shape for bulk flows.

The semantic interpreter prompt must be extended to map "全部 X" / "all X"
phrasing to the bulk intent and emit the appropriate scoping argument.

## Canonical Documentation Changes Required

Implementation of this spec must update the canonical docs in the same change
set that changes behavior or ownership boundaries.

Required doc sync:

- `docs/ARCHITECTURE.md`
  - Add a Scheduling System boundary section.
  - State that Scheduling is Gateway-hosted but contract-owned.
  - State that Scheduling depends on Reminder Runtime only through a port.
  - State that Focus is requested by the agent from the Scheduling contract
    via `resolveAgentFocus`, not reconstructed from inbound channel
    metadata.
  - Replace the stale pointer to the missing
    `2026-05-19-frontend-platform-channel-boundary-design.md` file with the
    current boundary references.
- `docs/design-docs/interface-contract.md`
  - Add `/api/customer/scheduling/*` to the public customer API surface.
  - Add `/api/internal/scheduling/*` to the internal API surface, including
    the focus binding endpoints (`resolveAgentFocus`,
    `bindAgentFocusSelection`) and the bulk shared-reminder endpoints
    introduced in Phase 4d.
  - Classify them as Scheduling System routes, not generic Gateway routes.
- `docs/product-specs/FEATURE_TREE.md`
  - Keep Friend Link and Shared Reminders discoverable.
  - Add bulk accept/reject/cancel as supported user-visible flows once
    Phase 4d lands.
  - Clarify that route location is not ownership.
- Boundary spec reference cleanup
  - Replace or restore stale references to
    `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
    if the file is not present in the current checkout.

## Implementation Phases

Phases 1-3 establish ownership without changing user-visible behavior.
Phases 4a-4d fill the behavior gaps that the multi-pending production case
exposed. Phase 5 hardens the agent contract. Phase 6 is the user-path smoke
that proves the regression class is closed.

### Phase 1: Contract Inventory And Tests

Create the shared fixture format and executable tests for the existing
contract before moving code. Future-behavior fixtures for business-key
idempotency, focus binding, and bulk variants may be added in this phase as
non-executable fixture data, but their executable assertions must land in the
phase that implements the behavior so the repository does not carry an
intentionally red Phase 1.

Coverage must include:

- tool names and accepted field shapes
- stable success DTOs
- stable error codes
- read/write classification
- idempotency for write operations, including the business-key uniqueness
  rule for `createSharedReminder` pending state
- `create_shared_reminder`, including idempotent upsert on business-key
  collision
- `list_friend_calendar_facts`
- `list_shared_reminders`
- accept/reject/cancel shared reminder actions
- bulk accept/reject/cancel shared reminder actions, including per-handle
  outcome arrays and partial-batch reporting
- `resolveAgentFocus` / `bindAgentFocusSelection`, including
  `multi_pending` shape, optimistic-concurrency conflict reasons, and
  expiry behavior
- missing friend
- ambiguous friend or request
- stale focused request
- runtime projection failure
- privacy filtering for friend calendar facts

This phase must catch agent/Gateway contract drift before runtime smoke
tests. Fixtures live alongside the contract and are consumed by both the TS
service tests and the Python client tests so divergence shows up as a test
failure on either side.

### Phase 2: Introduce SchedulingDomainContract

Add the contract facade and wire it to existing scheduling services.

No user-visible behavior should change in this phase. The goal is to make
ownership visible and give routes a single domain entrypoint. Behavior gaps
named in Phases 4a-4d are introduced explicitly there, not silently here.

### Phase 3: Thin Scheduling Routes

Refactor internal and customer scheduling route handlers to call the
contract.

Move route-local request resolution, shared-reminder lookup, error
taxonomy, and tool dispatch into the contract or domain service layer.

Keep HTTP paths stable unless a separate interface migration spec
explicitly changes them.

### Phase 4: Fill Behavior Gaps

Subphases here change user-visible behavior. Each subphase must land with
its own unit and integration coverage from Phase 1 fixtures, and with the
relevant Reminder Runtime / Notification / Outbound ports made explicit as
called out in this phase's port-cleanup task.

#### Phase 4a: Business-Key Idempotency

- Add a Prisma migration introducing a partial unique index on
  `shared_reminder_requests`
  `(requester_account_id, invitee_account_id, title, fire_at, timezone,
  COALESCE(duration_minutes, -1)) WHERE status = 'pending_invitee_confirmation'`
  or an equivalent generated-key representation. A plain nullable
  `duration_minutes` column in the unique key is not sufficient.
- `createSharedReminder` becomes an idempotent upsert: on business-key
  collision, return the existing pending row with an `already_pending: true`
  DTO field. Existing per-turn `idempotency_key` behavior is preserved.
- accept/reject/cancel transitions must remove the row from the partial
  index in the same transaction that flips `status`, so the next legitimate
  invitation with the same business key is not blocked by a stale unique
  conflict.
- Phase 1 fixtures cover collision, post-rejection re-invite, and
  concurrent-create races.

#### Phase 4b: Agent Focus Binding Contract

- Add `resolveAgentFocus` and `bindAgentFocusSelection` to the contract and
  to `/api/internal/scheduling/*`.
- Bridge inbound stops embedding raw `candidates` and `ambiguity` in
  `product_notification`. It may keep an actionable-items hint, but Focus
  comes from a contract call.
- Agent runtime replaces `focus_from_product_notification` with a call to
  `resolveAgentFocus` keyed by `(actor, conversation)`, and stores
  `focus_token` for the next turn.
- `bindAgentFocusSelection` performs optimistic concurrency against
  `shared_reminder_requests` state; conflict reasons are typed and the
  agent re-renders focus on conflict.
- The Notification port also lands here: product notification rows are
  written via the explicit `ProductNotificationPort` from this phase
  forward, replacing inline writes from route or service code paths that
  previously assumed Channel-side coupling.

#### Phase 4c: Disambiguation Session State

- Persist `DisambiguationSession` in `agent_sessions` whenever Focus is
  rendered with `state = "multi_pending"`.
- Extend the semantic interpreter prompt to allow resolving ordinal,
  delivery-time, and summary-text references against `offered_handles`,
  returning the matched `handle` in `args`. Ordinal / time / summary
  matching remains an LLM responsibility; no Python regex or keyword
  routing is added.
- Agent runtime maps the returned `handle` plus `focus_token` into a
  `bindAgentFocusSelection` call before dispatching the matching scheduling
  intent.
- Session expiry follows the contract `expires_at`. Expired sessions are
  cleared and the next turn must re-resolve Focus.
- The Reminder Runtime projection port also lands here: scheduling writes
  to Mongo reminders only through `ReminderRuntimePort`, not directly,
  matching the saga-ambiguity reduction goal.

#### Phase 4d: Bulk Variants

- Add `acceptPendingSharedRemindersFrom`,
  `rejectPendingSharedRemindersFrom`, and
  `cancelPendingSharedRemindersFor` to the contract and to
  `/api/internal/scheduling/*`. Return per-handle outcome arrays.
- Extend the semantic interpreter prompt to recognise bulk intents
  ("全部 X", "all X") and emit the appropriate scope filter.
- The Outbound/delivery port also lands here so bulk operations dispatch
  product notifications through the same explicit `ProductNotificationPort`
  and outbound port as single-candidate flows.
- Reply contract for bulk operations summarises per-handle outcomes so the
  agent does not claim a uniform result.

### Phase 5: Harden Agent Contract

Rename or wrap the agent-side Gateway scheduling client as a Scheduling
contract client.

Add golden checks so the Python tool contract and Gateway-supported
contract cannot silently diverge.

Ensure agent-facing DTOs are domain-shaped and do not require the agent to
know Gateway storage columns. The new focus binding, business-key
idempotency, and bulk DTOs are part of this hardening.

### Phase 6: Runtime Smoke

After behavior-affecting phases, run a user-path smoke that proves:

- a friend link or existing friendship path works
- a shared reminder request can be created
- creating an identical shared reminder twice within the same business key
  is collapsed into a single pending row and the second response is
  flagged `already_pending`
- after the first invitation is rejected, a fresh invitation with the same
  business key succeeds and does not hit a stale uniqueness conflict
- invite notification is delivered
- invitee can accept
- when multiple distinct pending invitations exist for the same invitee,
  the agent renders an enumeration sourced from `resolveAgentFocus`, and
  the invitee can disambiguate by ordinal, delivery time, or summary
  reference to complete the accept
- bulk "全部确认" / "全部拒绝" resolves all currently pending invitations
  through the bulk contract method and produces a faithful per-handle
  summary
- both runtime reminder projections exist for accepted invites
- friend calendar facts expose busy intervals only
- reminder firing still routes through Reminder Runtime

## Verification

For a docs-only spec change:

```text
zsh scripts/verify-surface repo-os-docs
zsh scripts/check
```

For implementation work:

```text
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
zsh scripts/verify-surface repo-os-docs gateway-api bridge worker-runtime
```

Also run targeted tests for the touched side:

- Gateway API scheduling route and service tests
- Python scheduling capability tests
- Python execution-agent scheduling tests
- Bridge reminder management tests when ReminderRuntimePort behavior changes
- shared-reminder smoke when lifecycle, projection, or delivery behavior changes

## Non-Goals

- Do not move all Scheduling behavior into Agent Runtime in this design.
- Do not make Bridge the Scheduling product owner.
- Do not let Scheduling write Reminder Runtime storage directly.
- Do not add backend slot selection, appointment recommendation, or booking
  policy. The agent owns scheduling reasoning from privacy-safe facts.
- Do not add compatibility aliases or retired behavior just to preserve stale
  tests.
- Do not change public or internal API paths in the first refactor unless a
  separate migration plan covers callers, docs, smoke checks, and deletion of
  retired paths.
- Do not encode disambiguation language patterns (ordinal references, time
  references, summary-text references, bulk phrasing) as Python regex or
  keyword routing in agent runtime. They remain the LLM's responsibility;
  the structured pieces this spec adds (`DisambiguationSession`,
  `AgentFocusBinding`) are scaffolding the model binds against, not a
  replacement for it.
- Do not represent business-key idempotency as application-level checks
  alone. The unique index is the contract; the application path is the
  optimization.

## Open Questions

None for the boundary decision.

Future implementation plans may still choose exact file names, DTO names, and
test fixture layout. Those are execution details, not unresolved architecture
questions.
