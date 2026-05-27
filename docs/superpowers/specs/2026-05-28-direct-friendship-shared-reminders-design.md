---
status: active
created_at: 2026-05-28
owner: scheduling
kind: design
---

# Direct Friendship And Active Shared Reminders Design

## Decision

Friend links and shared reminders no longer use invitee confirmation.

This is a destructive product-contract change:

- Friend links directly create active friendships.
- The `friend_requests` business model is retired and removed.
- Account blocking is retired and removed.
- Shared reminders are direct shared facts, not requests awaiting acceptance.
- Shared-reminder pending, accept, reject, and bulk pending flows are removed.
- Current product docs, API maps, code, and tests must stop presenting
  confirmation or block/unblock behavior as active.
- Historical `docs/issues/` and generated evidence are audit material. They are
  not broadly deleted, but active docs and references must mark old behavior as
  retired when needed.

The target user model is:

```text
Friend link opened by another logged-in account
  -> active friendship is created or reused
  -> link owner is notified

Friend creates a shared reminder for another friend
  -> receiver busy time is checked only when duration is present
  -> if receiver has no conflict, both reminder projections are created
  -> shared reminder is active immediately
  -> receiver is notified
```

## Scope

This design covers the Gateway-hosted Scheduling system and its worker-facing
agent contract:

- public user-link and link-session friend creation
- customer scheduling routes and UI affordances
- internal scheduling domain tools
- product notifications for direct friendship and shared reminders
- Postgres schema and migrations
- Reminder Runtime projection orchestration
- production deployment and real-account smoke verification

The design does not move Scheduling out of the Gateway API process. It refines
the existing boundary described by
`2026-05-28-gateway-hosted-scheduling-boundary-design.md`: Gateway may host the
Scheduling system, while route handlers remain adapters over a Scheduling
domain contract.

## Non-Goals

- Do not preserve compatibility routes for removed pending/accept/reject APIs.
- Do not preserve `friend_requests` as an audit table.
- Do not preserve account block/unblock behavior, tables, API routes, agent
  tools, UI, or tests.
- Do not merge shared-reminder relationship facts into Reminder Runtime as the
  only source of truth.
- Do not expose another user's private reminder title or details when a busy
  conflict blocks shared-reminder creation.

## Data Model

### Friendships

`friendships` becomes the only durable friend relationship table.

Required shape:

- `id`
- canonical ordered pair: `account_a_id`, `account_b_id`
- `status`: `active | removed`
- optional source fields such as `source`, `source_user_link_id`,
  `source_link_session_id`, or equivalent migration-safe metadata if useful
- `removed_at`
- timestamps

The old `friend_request_id` relationship is removed. Active friendship
deduplication is enforced by the canonical pair. Re-opening the same friend link
between already-active friends is an idempotent success and must not send a
duplicate product notification.

Removed friendships may be recreated by opening a valid friend link again. The
system no longer has account blocking, so no block check may prevent future
re-addition.

### Removed Friend Requests

The following are removed from the active schema and generated client:

- `FriendRequest`
- `FriendRequestStatus`
- relations from `Customer`, `LinkSession`, `Friendship`, and
  `ProductNotification`
- product-notification foreign key `friend_request_id`
- route/service/tool/test code whose only purpose is friend-request
  pending/accept/reject/cancel/list behavior

### Removed Account Blocks

Account-blocking is retired entirely. The current schema already has no active
`AccountBlock` model. This change must assert that account-block tables,
relations, indexes, routes, services, tests, docs, and agent tools are absent
and must fail review if block/unblock behavior is reintroduced.

### Shared Reminders

The current `SharedReminderRequest` model is renamed and redefined as a shared
reminder fact model. The existing center-table plus projection structure stays,
but request semantics are removed.

Target model name: `SharedReminder`

Target table name: `shared_reminders`

Required shape:

- `id`
- `creator_account_id`
- `receiver_account_id`
- `friendship_id`
- `title`
- `fire_at`
- `timezone`
- nullable `duration_minutes`
- nullable `idempotency_key`
- `status`: `active | cancelled | invalidated`
- `creator_reminder_id`
- `receiver_reminder_id`
- `cancelled_at`
- `invalidated_at`
- timestamps

`accepted`, `pending_invitee_confirmation`, `rejected`, and `expired` are not
active shared-reminder states. The center record represents whether the shared
relationship fact exists. Reminder execution lifecycle remains owned by the
participant runtime reminders and projections.

`ReminderProjection` remains as the bridge between the shared-reminder center
record and each participant's Reminder Runtime record.

Target `ReminderProjection` shape:

- `shared_reminder_id`
- `owner_account_id`
- `runtime_reminder_id`
- `role`: `creator | receiver`

The old `requester/invitee` naming is replaced in active code and docs with
`creator/receiver`.

### Shared Reminder Events And Notifications

Shared-reminder events remain useful for audit and compensation, but names must
match the new model:

- `SharedReminderEvent`
- foreign key `shared_reminder_id`
- `from_state` and `to_state` use `SharedReminderStatus`
- actor role: `creator | receiver | system`
- nullable `reason` for cancellation, invalidation, migration, and compensation
  evidence

`ProductNotification` must reference `shared_reminder_id` instead of
`shared_reminder_request_id`.

Direct-friendship notifications must also have a current relation after
`friend_request_id` is removed. `ProductNotification` must reference
`friendship_id` for direct-friendship notifications, or use an equivalent
typed resource reference that can express:

- `resource_type = friendship`
- `resource_id = friendships.id`
- unique idempotency key for `friendship:<friendship_id>:direct-add`
- recipient account id equal to the link owner

The notification enqueue contract must stop accepting
`requestType: friend_request`. It must support direct friendship and shared
reminder notification resources only.

Notification metadata for shared-reminder creation and cancellation includes:

- `shared_reminder_id`
- `status`
- `actor_account_id`
- `creator_account_id`
- `receiver_account_id`
- display names when available
- `title`
- `fire_at`
- `timezone`
- viewer-local date and time
- `duration_minutes`

Creation and cancellation notifications must not include `allowed_actions`.
They are informational, not actionable confirmation prompts.

## Friend Link Flow

### Public User Link

When a logged-in account opens or submits another user's friend link:

1. Validate the link or link session using the existing public-link mechanics.
2. Reject self-friend attempts.
3. Canonicalize the account pair.
4. If an active friendship already exists, return success and do not notify.
5. If a removed friendship exists, reactivate it or create a new active
   friendship according to the cleanest migration-safe implementation path.
6. Notify only the link owner that the opener added them as a friend.
7. Return success to the opener.

There is no pending friend request, accept action, reject action, or requester
notification.

### Friend Removal

Friend removal remains active behavior.

Removing a friend:

- marks the friendship `removed`
- prevents future shared-reminder creation until a valid friend link recreates
  the friendship
- does not cancel existing active shared reminders
- does not block future re-addition

## Shared Reminder Flow

### Create

Creating a shared reminder requires an active friendship between creator and
receiver.

The `createSharedReminder` domain port must include `listRuntimeCalendarFacts`
in addition to runtime create/cancel operations. Duration conflict checks use
the receiver's runtime calendar facts for the half-open interval
`[fire_at, fire_at + duration_minutes)`.

On create:

1. Validate creator, receiver, title, `fire_at`, timezone, optional duration,
   and idempotency key.
2. Reject self-shared reminders.
3. Confirm active friendship.
4. If `duration_minutes` is present, check only the receiver's busy intervals
   for the occupied interval.
5. If receiver time conflicts, fail the whole operation. Do not create the
   center record, either runtime reminder projection, or a receiver
   notification. The error code is `receiver_time_conflict`; response metadata
   may include the requested interval but no private title/details.
6. If no conflict, resolve the idempotency key:
   - active row with same participants/key returns the existing shared reminder
   - same key with different participants/title/time returns
     `idempotency_conflict`
   - no row continues creation
7. Generate the future `shared_reminder_id` before runtime calls.
8. Create the creator runtime reminder projection using that id.
9. Create the receiver runtime reminder projection using that id.
10. Insert the shared-reminder center row and both projection rows in one DB
    transaction with `status = active` and both runtime reminder ids.
11. Notify only the receiver.
12. Return success to the creator.

Projection creation is a two-runtime side-effect flow and must be idempotent:

- If creator projection creation succeeds and receiver projection creation
  fails, cancel the creator runtime reminder and return failure. No
  shared-reminder center row or projection row may remain.
- If receiver projection creation succeeds but final DB activation fails,
  cancel both runtime reminders and return failure. No shared-reminder center
  row or projection row may remain unless the transaction already committed.
- If retry finds an active center row with both projections for the same
  idempotency key, return the existing active shared reminder without creating
  new runtime reminders or notifications.
- If retry occurs after runtime reminders were created but before DB commit, the
  runtime idempotency keys must let the retry reuse or safely cancel those
  runtime reminders before the single active insert.
- Tests must cover creator-created/receiver-failed, both-created/finalize-failed,
  retry-active, runtime-idempotent retry, and receiver-conflict-no-write cases.

Point reminders without `duration_minutes` do not perform busy-interval
conflict checks.

Conflict responses may reveal a privacy-safe busy interval result, but they
must not reveal the receiver's reminder title or private reminder details.

### Cancel

Either participant may cancel an active shared reminder.

On cancel:

1. Verify actor is the creator or receiver.
2. Transition the shared reminder from `active` to `cancelled`.
3. Cancel both participant runtime reminders.
4. Keep the center record for history/listing/audit.
5. Notify only the other participant.

Cancellation is actor-neutral:

- `actor_account_id` may equal `creator_account_id` or `receiver_account_id`.
- `recipient_account_id` is always the other participant.
- notification metadata includes `actor_role`, `actor_account_id`,
  `recipient_account_id`, `creator_account_id`, `receiver_account_id`, `title`,
  `fire_at`, `timezone`, viewer-local date/time, and `duration_minutes`.
- notification text must describe who cancelled and which shared reminder was
  cancelled without implying requester/invitee confirmation.
- cancellation idempotency uses
  `shared-reminder:<shared_reminder_id>:cancel:<actor_account_id>`.
- repeated cancellation of an already-cancelled shared reminder by either
  participant returns the existing cancelled state and does not send a duplicate
  notification.

There is no single-side conversion from shared reminder to personal reminder in
this contract.

### List And Query

The active product surface supports:

- list friends
- remove friend
- create shared reminder
- cancel shared reminder
- list/query shared reminders by participant, friend, status, and date range

The active product surface does not support:

- list pending friend requests
- accept/reject/cancel friend request
- list pending shared reminders
- accept/reject shared reminder
- bulk accept/reject pending shared reminders
- focus binding for pending invitation actions
- block/unblock account

## Agent And Focus Contract

The agent-facing Scheduling contract must remove pending invitation tools and
focus candidates.

Remove active tool intents and callable operations for:

- accepting friend requests
- rejecting friend requests
- cancelling friend requests
- listing pending friend requests
- accepting shared reminders
- rejecting shared reminders
- listing pending shared reminders
- bulk accepting/rejecting pending shared reminders
- account block/unblock

Keep or provide operations for:

- reading or creating the user's friend link
- direct friend creation by user-link code
- list friends
- remove friendship
- create shared reminder
- cancel shared reminder
- list/query shared reminders
- list friend calendar facts

Product notifications for direct friendship and direct shared-reminder creation
are informational. They may help conversation context, but they must not create
pending Focus actions or allowed action sets.

## UI And API Contract

Customer and public APIs should expose direct actions only. Removed routes
should return normal route-not-found behavior rather than compatibility
responses.

Route/tool/type rename table:

| Current removed contract | Replacement active contract |
| --- | --- |
| `POST /api/public/link-sessions/:token/friend-requests` | `POST /api/public/link-sessions/:token/friendships` |
| `send_friend_request_by_user_link_code` | `create_friendship_by_user_link_code` |
| `FriendRequestResponse` shared type | `DirectFriendshipResponse` |
| `FriendRequestStatus` shared type | no replacement; friendship response status is `active` |
| `list_friend_requests` | no replacement |
| `accept_friend_request` / `reject_friend_request` / `cancel_friend_request` | no replacement |

`DirectFriendshipResponse` contains:

- `id`: friendship id
- `status`: `active`
- `friend_account_id`: the link owner for opener-facing responses, or the
  opener for owner-facing contexts
- `created`: boolean indicating whether this call created/reactivated the
  friendship or reused an existing active friendship

Removed public/customer/internal route paths must have route-not-found tests.
Removed agent tools must return `unknown_tool` from the scheduling domain
contract if called.

Customer web surfaces should remove pending invitation panels, accept/reject
buttons, and block/unblock controls. They should keep friend list, friend-link
sharing, remove friend, shared-reminder list/query, create, and cancel flows.

`docs/product-specs/FEATURE_TREE.md` must be updated so route discovery no
longer describes removed pending or blocking surfaces.

## Migration

This change requires a release migration because the new code removes handlers
for old pending records.

Migration requirements:

1. Convert existing accepted shared-reminder request rows to active shared
   reminder rows.
2. Convert pending shared-reminder request rows:
   - activate only when friendship is active, fire time is still valid for the
     current product policy, existing/requester projection can be reconciled,
     receiver projection can be created or reused, and receiver duration
     conflict check passes when duration is present
   - invalidate with a reason when friendship is missing/removed, participants
     are invalid, receiver conflict exists, projection reconciliation fails, or
     the row is stale according to migration policy
3. Convert old accepted friend requests into active friendships when necessary.
4. Convert old pending friend requests into active friendships only when the
   requester, target, and link/session lineage are valid and the canonical pair
   is not already active. Duplicate pending rows for the same canonical pair
   collapse into one active friendship; older duplicates are counted as skipped.
5. Drop friend-request schema after data is represented in friendships.
6. Assert account-block schema and data are absent; do not recreate or reference
   the retired account-block model.
7. Rename shared-reminder request tables/columns/indexes/foreign keys to
   shared-reminder fact names.
8. Update product notification foreign keys from request names to current
   direct-friendship and shared-reminder names.

Migration decision table:

| Legacy row | Activate | Invalidate | Skip |
| --- | --- | --- | --- |
| accepted friend request | when no active friendship exists for canonical pair | never | when active friendship already exists |
| pending friend request | when requester/target/link lineage are valid and pair is not active | when requester or target is missing or self-pair | duplicate canonical pair |
| accepted shared-reminder request | when both participant runtime projections can be reconciled | when required projection data is missing and cannot be rebuilt | when already represented by migrated shared reminder |
| pending shared-reminder request | when active friendship exists, receiver has no duration conflict, and both projections can be completed | when friendship is absent/removed, receiver conflict exists, stale policy rejects it, or projection compensation fails | duplicate idempotency/business key already migrated |

Migration must not enqueue new product notifications for converted legacy
pending rows. The migration is a data-shape conversion, not a new user action.
Every invalidated shared reminder must have a `SharedReminderEvent.reason`
entry. Migration evidence must include reason counts and representative ids for
each invalidation reason.

Migration evidence must include counts of:

- friend requests converted
- friend requests skipped or invalidated
- shared reminders activated
- shared reminders invalidated
- account-block schema/data absence asserted

The deploy runbook must state that the migration is part of the release window
and is a non-rolling change. Deployment order is:

1. Announce/enter the scheduling maintenance window.
2. Stop old Gateway API and worker/scheduling processes, or otherwise block
   scheduling writes.
3. Take a database backup.
4. Run the schema/data migration.
5. Deploy the new Gateway/API/worker code.
6. Run migration evidence checks and production smoke.
7. Resume scheduling traffic.

Zero-downtime expand/contract compatibility is explicitly not part of this
design because compatibility routes and legacy pending models are being removed.

## Testing And Verification

Use TDD for implementation.

Required focused tests:

- user link creates active friendship directly
- repeated user-link open for existing friendship is idempotent and does not
  duplicate notifications
- removed friendship can be recreated through a valid user link
- friend-request APIs/tools are removed
- block/unblock APIs/tools are removed
- shared reminder create returns `active`
- shared reminder create creates both runtime projections
- shared reminder create notifies only the receiver
- point shared reminder skips busy conflict checking
- duration shared reminder checks only receiver busy intervals
- receiver conflict fails without creating projections or notifications
- either participant can cancel and both projections are cancelled
- cancel notifies only the other participant
- pending shared-reminder tools/routes/focus candidates are removed
- schema contract no longer contains `FriendRequest`, account blocks, or
  request-status enums

Required broader verification:

- Gateway API scheduling tests
- Gateway route tests for public and customer scheduling flows
- worker scheduling capability tests affected by tool removal
- schema/migration checks
- repo verification suggested by `zsh scripts/suggest-verification --base HEAD~1`
- risk report from `zsh scripts/review-trigger --base HEAD~1`

Production happy-path smoke must be updated to the new contract and then run
after deployment with real server accounts:

- direct friend-link add creates an active friendship and sends only an
  informational notification to the link owner
- direct shared-reminder create with duration and no receiver conflict creates
  both runtime reminders, returns active, and sends only an informational
  notification to the receiver
- shared-reminder cancel by either participant cancels both runtime reminders
  and notifies only the other participant
- conflict create path fails without projections and without receiver
  notification
- cleanup removes only uniquely marked smoke data

The production smoke can send real push messages to real accounts. It must use
unique markers and must not print secrets.

## Rollout Notes

Implementation occurs on `main` with explicit approval already given for this
task.

Every completed repository change must be committed before handoff. Because
this change is destructive, commits should be small and reviewable:

1. spec
2. plan
3. schema/migration
4. friend-link direct friendship
5. shared-reminder active model
6. route/tool/UI cleanup
7. docs and production smoke update
8. deployment evidence

If a production migration cannot safely complete, deployment must stop before
removing operational support for the old pending data.
