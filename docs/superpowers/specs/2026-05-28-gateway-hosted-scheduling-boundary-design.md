---
status: active
created_at: 2026-05-28
owner: architecture
kind: design
---

# Gateway-Hosted Scheduling Boundary Design

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

## Canonical Documentation Changes Required

Implementation of this spec must update the canonical docs in the same change
set that changes behavior or ownership boundaries.

Required doc sync:

- `docs/ARCHITECTURE.md`
  - Add a Scheduling System boundary section.
  - State that Scheduling is Gateway-hosted but contract-owned.
  - State that Scheduling depends on Reminder Runtime only through a port.
- `docs/design-docs/interface-contract.md`
  - Add `/api/customer/scheduling/*` to the public customer API surface.
  - Add `/api/internal/scheduling/*` to the internal API surface.
  - Classify them as Scheduling System routes, not generic Gateway routes.
- `docs/product-specs/FEATURE_TREE.md`
  - Keep Friend Link and Shared Reminders discoverable.
  - Clarify that route location is not ownership.
- Boundary spec reference cleanup
  - Restore, replace, or remove stale references to
    `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`
    if the file is not present in the current checkout.

## Implementation Phases

### Phase 1: Contract Inventory And Tests

Create contract fixtures or tests before moving code.

Coverage should include:

- tool names and accepted field shapes
- stable success DTOs
- stable error codes
- read/write classification
- idempotency for write operations
- `create_shared_reminder`
- `list_friend_calendar_facts`
- `list_shared_reminders`
- accept/reject/cancel shared reminder actions
- missing friend
- ambiguous friend or request
- stale focused request
- runtime projection failure
- privacy filtering for friend calendar facts

This phase should catch agent/Gateway contract drift before runtime smoke tests.

### Phase 2: Introduce SchedulingDomainContract

Add the contract facade and wire it to existing scheduling services.

No behavior should change in this phase. The goal is to make ownership visible
and give routes a single domain entrypoint.

### Phase 3: Thin Scheduling Routes

Refactor internal and customer scheduling route handlers to call the contract.

Move route-local request resolution, shared-reminder lookup, error taxonomy, and
tool dispatch into the contract or domain service layer.

Keep HTTP paths stable unless a separate interface migration spec explicitly
changes them.

### Phase 4: Make Ports Explicit

Split or clarify the ports used by shared-reminder behavior:

- Prisma repository/client boundary
- Reminder Runtime projection port
- Product notification port
- delivery/outbound port

This phase should focus on reducing saga ambiguity, not changing user-visible
behavior.

### Phase 5: Harden Agent Contract

Rename or wrap the agent-side Gateway scheduling client as a Scheduling
contract client.

Add golden checks so the Python tool contract and Gateway-supported contract
cannot silently diverge.

Ensure agent-facing DTOs are domain-shaped and do not require the agent to know
Gateway storage columns.

### Phase 6: Runtime Smoke

After behavior-affecting phases, run a user-path smoke that proves:

- a friend link or existing friendship path works
- a shared reminder request can be created
- invite notification is delivered
- invitee can accept
- both runtime reminder projections exist
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

## Open Questions

None for the boundary decision.

Future implementation plans may still choose exact file names, DTO names, and
test fixture layout. Those are execution details, not unresolved architecture
questions.
