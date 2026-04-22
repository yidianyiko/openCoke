# Google Calendar One-Time Import And WhatsApp Claim Entry (Design)

**Status:** draft for review
**Date:** 2026-04-22
**Surfaces:** `gateway/packages/api`, `gateway/packages/web`,
`connector/clawscale_bridge`, `agent/agno_agent/tools/deferred_action`,
`agent/runner`
**References:** `docs/architecture.md`,
`docs/design-docs/coke-working-contract.md`,
`gateway/packages/api/prisma/schema.prisma`,
`gateway/packages/api/src/lib/shared-channel-provisioning.ts`,
`gateway/packages/api/src/lib/claim-token.ts`,
Google Calendar API `events.list`,
Google Calendar API recurring events guide,
Google Calendar API reminders guide,
Google OAuth 2.0 web server apps guide

## Goal

Allow a Coke user to migrate their existing Google Calendar reminders into Coke
as one-time imported reminders.

The first version is intentionally a migration, not a sync product:

- read only the user's Google `primary` calendar
- attempt import of all visible calendar events, with explicit partial-failure
  reporting for unsupported recurrence shapes
- convert imported events into Coke-owned reminders
- do not keep an ongoing Google connection
- do not sync updates back to Google
- do not re-sync future Google edits into Coke

This design must also support the shared WhatsApp path where a user already
exists in Coke as an auto-provisioned, `unclaimed` customer before they ever
visit the web app.

Because today's reminder runtime is conversation-scoped, this design also needs
to define exactly which existing Coke conversation an imported reminder belongs
to. V1 does not invent a synthetic "web-only reminder inbox".

## Non-Goals

- No bidirectional sync.
- No periodic or webhook-based re-import.
- No Google Tasks support.
- No multi-calendar picker.
- No phone-number login, SMS OTP, or WhatsApp-as-password flow.
- No generic external reminders platform abstraction in v1.
- No requirement to preserve a long-lived Google event binding after import.

## Product Decisions

The user approved the following product rules during design:

- import source is Google Calendar, not Google Tasks
- import source is the authenticated user's `primary` calendar only
- all imported events become Coke reminders
- imported reminders become Coke-owned reminders immediately after import
- event reminder time uses the effective Google reminder if present
- if an event has no Google reminder, the Coke reminder fires at event start
- if an all-day event has no Google reminder, the Coke reminder fires at
  `09:00` on that day
- history is included
- past single events become imported historical reminder records in the
  existing `completed` lifecycle
- open-ended recurring events without exception instances should become Coke
  recurring reminders
- users auto-created from WhatsApp must claim their account before importing
- WhatsApp claim entry opens with an "enter your email" page first
- claim completion reuses the existing password-setting flow
- import only starts when Coke can resolve a valid target private conversation
- recurring-series fidelity is intentionally narrow in v1: exception-bearing
  Google series are reported as partial import failures instead of being
  silently misrepresented

## Users

### 1. Claimed Coke customer

This user already has an `active` web identity and can log in normally with
email and password.

They can start Google Calendar import directly from the web account area.

### 2. Auto-provisioned shared WhatsApp customer

This user was created by first inbound contact on a shared WhatsApp channel.
The customer graph exists, but the owner `Identity` starts as `unclaimed`, not
as a normal web-login user. This is how the current runtime provisions shared
channel users today.

They cannot start Google Calendar import until they claim that account.

## Core Decisions

### 1. Treat Google Calendar import as a one-time migration

The imported reminders are not "external reminders that stay owned by Google".
They are migrated into Coke.

As soon as an event is imported successfully:

- the runtime creates a normal Coke reminder in `deferred_actions`
- future edits inside Coke are local Coke edits
- there is no later attempt to reconcile those edits against Google

This is the key simplification that keeps the first version small and aligned
with the approved product intent.

### 2. Require account claim before any Google integration

Google import is a web-account capability, not a pure channel capability.

For shared WhatsApp users, the system must first convert the auto-provisioned
customer into a claimed customer account:

1. WhatsApp sends a short-lived claim-entry link.
2. The user opens that link in the browser.
3. The first page asks for an email address.
4. The server sends a claim email to that address.
5. The user opens the email link and lands on the existing `/auth/claim`
   password-setting flow.
6. After password creation, the identity becomes `active`.
7. The user is now logged in and can start Google Calendar import.

This keeps the existing auth model intact and avoids inventing a phone login
system that does not exist in the current repository.

### 3. Split responsibilities between gateway and Coke runtime

The import flow crosses both the gateway and Coke runtime on purpose.

`gateway` owns:

- web entry points
- customer session and claim state checks
- Google OAuth redirect and callback handling
- calling Google APIs
- import-run audit state

Coke runtime owns:

- the canonical reminder creation logic
- recurrence handling
- historical reminder lifecycle mapping
- writing `deferred_actions`

This follows the current repository boundary:

- `gateway` already owns web auth and customer identity state
- Coke runtime already owns reminder semantics and scheduling

### 4. Attach imported reminders to an existing private Coke conversation

The current reminder runtime is not account-global. Every reminder belongs to a
specific `conversation_id`, `user_id`, and `character_id`, and later execution
re-enters the normal conversation turn pipeline.

V1 therefore uses this rule:

- every imported reminder must attach to one existing private conversation
  between the customer and Coke's default character
- the import run stores that target conversation identity up front
- imported reminders reuse that conversation's `conversation_id`, `user_id`,
  and `character_id`
- v1 does not import into group conversations
- v1 does not create a synthetic web-only reminder destination

Resolution rules:

- if the import starts from a shared WhatsApp claim-entry flow, carry the
  originating private conversation forward and reuse it as the target
- if the import starts from a normal claimed web session, resolve the user's
  most recent deliverable private conversation with the default Coke character
- if no valid private conversation can be resolved, block import and instruct
  the user to start a Coke conversation first

This is a product constraint for v1, not an implementation detail.

### 5. Persist only import-run audit, not a long-lived Google connection

The first version should not create a long-lived Google integration model.

We will persist:

- the fact that an import was attempted
- who ran it
- whether it succeeded
- summary counts and failure information

We will not persist:

- refresh tokens
- a reusable Google connection row
- a durable Google-event-to-Coke-reminder link table

This means the product remains a one-time importer, not a sync substrate.

### 6. Use least-privilege Google access

Because the product is a one-time read-only import:

- use the OAuth authorization code flow for web server apps
- include PKCE and a signed `state` parameter
- request the minimum read-only calendar scope needed for events import
- do not request offline access unless the implementation later proves it is
  required for a real background continuation
- discard the Google access token after the import run completes

The current best-practice references for this decision are Google's web-server
OAuth guidance and Calendar API docs:

- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- https://developers.google.com/calendar/api/concepts/reminders
- https://developers.google.com/calendar/api/guides/recurringevents

## End-To-End Flows

### Flow A: Claimed customer imports Google Calendar

1. User logs into Coke web.
2. User opens the calendar import screen.
3. Gateway resolves a valid target private conversation for imported reminders.
4. If no target conversation exists, the UI blocks import and explains how to
   start a Coke conversation first.
5. Coke creates an import run in `authorizing` state, including the target
   conversation identity.
6. Gateway redirects the user to Google OAuth.
7. Google redirects back to Coke.
8. Gateway exchanges the code for a short-lived access token.
9. Gateway reads the user's `primary` calendar events.
10. Gateway hands the normalized payload plus the target conversation identity
    to a Coke internal import endpoint.
11. Coke runtime creates reminders in `deferred_actions`.
12. Gateway records the final import result and shows a summary screen.

### Flow B: Unclaimed shared WhatsApp customer imports Google Calendar

1. User asks for a web-only capability in WhatsApp, such as calendar import.
2. Coke replies with a short-lived claim-entry link.
3. User opens the link and lands on a claim-entry page.
4. User enters an email address.
5. Gateway sends a claim email to that address.
6. User opens the claim email and lands on the existing `/auth/claim` page.
7. User sets a password.
8. Claim completes, the identity becomes `active`, and the user is redirected
   to a validated continuation
   destination that preserves the calendar-import intent.
9. The normal claimed-user import flow begins.

## UX Rules

### Claim entry page

Add a new page dedicated to auto-provisioned customer claim entry.

Requirements:

- the page is reachable only through a short-lived signed entry token
- the page does not show the normal login form
- the page asks for one thing first: the user's email
- on success it tells the user to check their inbox
- on invalid or expired entry token it instructs the user to request a fresh
  link from WhatsApp

### Existing claim page

Keep the current `/auth/claim` behavior:

- accept claim token
- ask for password and confirm password
- complete claim
- sign the user in
- honor a validated post-claim continuation target when one is present
- otherwise fall back to the current default post-claim destination

No phone-number-specific branch is added.

### Import screen

The import screen should clearly state:

- this imports the user's Google `primary` calendar
- imported events become Coke reminders
- changes made later in Google will not sync automatically
- import requires an existing Coke private conversation
- advanced Google recurring series with exception instances may be skipped with
  warning in v1
- running import again may duplicate reminders that the user has already chosen
  to keep as Coke-only data

## Minimal Data Model Changes

### Postgres: `calendar_import_runs`

Add one small audit table in the gateway Prisma schema.

Purpose:

- show the user import status
- capture summary counts and failure reasons
- give operators enough visibility to debug import failures

Recommended fields:

- `id`
- `customerId`
- `identityId`
- `targetConversationId`
- `targetCharacterId`
- `provider` with fixed value `google_calendar`
- `triggerSource` such as `manual_web` or `whatsapp_claim_redirect`
- `status`
  - `authorizing`
  - `importing`
  - `succeeded`
  - `succeeded_with_errors`
  - `failed`
- `providerAccountEmail` nullable
- `startedAt`
- `finishedAt` nullable
- `importedCount`
- `skippedCount`
- `failedCount`
- `errorSummary` nullable
- `createdAt`
- `updatedAt`

This table is intentionally batch-level only. There is no per-event audit row
in v1.

### Mongo: imported reminder metadata only

Do not add a new Mongo collection.

Imported reminders remain normal `deferred_actions` rows. The importer may add
lightweight metadata inside `payload.metadata` for observability and duplicate
protection, for example:

- `import_provider: "google_calendar"`
- `import_run_id`
- `source_calendar_id: "primary"`
- `source_event_id`
- `source_original_start_time`

These fields are implementation support metadata, not a public product
contract.

V1 should also add a best-effort non-unique Mongo index for imported reminder
lookup, keyed by:

- `user_id`
- `payload.metadata.import_provider`
- `payload.metadata.source_event_id`
- `payload.metadata.source_original_start_time`

## API And Route Additions

### Gateway web

- add a claim-entry page, for example `/auth/claim-entry`
- add an authenticated customer import entry page in the account area

### Gateway API

- add a public claim-request endpoint, for example `POST /api/auth/claim/request`
- add an authenticated calendar import start endpoint
- add a Google OAuth callback endpoint
- add an import-run status endpoint

The claim-request and claim-complete flow must carry a validated continuation
state so the successful claim can return to the import entry flow instead of
always falling back to the default channels page.

### Coke runtime internal import surface

Add a new internal runtime mutation surface for Google Calendar import.

The exact wiring can extend the bridge or use another internal service adapter,
but the design requires:

- gateway must not write reminders directly into Mongo
- gateway must not reimplement reminder recurrence logic
- runtime reminder creation must stay in Coke-owned code
- this is a new batch-mutation surface, not a variant of today's
  request-response `/bridge/inbound` endpoint

## Mapping Rules: Google Event -> Coke Reminder

### Import target identity

Every imported reminder must be created against one resolved private Coke
conversation:

- `conversation_id` comes from the resolved target conversation
- `user_id` is the human participant in that conversation
- `character_id` is the default Coke character in that conversation

If Coke cannot resolve such a conversation for the importing user, the import
must not start.

### Calendar scope

- only the authenticated user's `primary` calendar is imported
- the import includes history and future data from that calendar

### Event selection

- import all visible event types returned from the primary calendar
- ignore tombstone-only records that are only cancellation artifacts with no
  usable reminder meaning outside their series

### Effective reminder time

Google events can define:

- event-specific reminder overrides
- or `useDefault=true`, which means calendar defaults apply

The importer should calculate one effective Coke reminder time per imported
event:

1. If the event has effective Google reminders, choose the earliest reminder
   minute among the effective reminders.
2. If the event has no effective Google reminders:
   - timed event -> reminder at event start
   - all-day event -> reminder at `09:00` local calendar time on that day

Timezone precedence for import interpretation:

1. the event's explicit timezone, when Google provides one
2. otherwise the source calendar timezone
3. otherwise the Coke account timezone selected for the target conversation

Method-specific Google reminder channels such as `email` versus `popup` are not
preserved because Coke reminder delivery is governed by Coke's own delivery
system.

### Single events

- future single events become active one-shot Coke reminders
- past single events become imported historical reminders in the existing
  `completed` lifecycle
- historical imported events must be written with `next_run_at = null`
- historical imported events must not be created through the default
  end-user reminder helper unchanged, because that helper always seeds an
  `active` reminder

### Recurring events

The importer must preserve recurring series as faithfully as Coke's runtime can
represent them.

Rules:

- only recurring series with no exception instances become one Coke recurring
  reminder in v1
- open-ended recurring series remain recurring Coke reminders
- the recurring reminder keeps the original series start so recurrence stays
  semantically correct
- the runtime import path must seed `next_run_at` to the first future
  occurrence, not to `now`, even when the original series start is in the past
- recurring imports therefore require an import-aware runtime creation path,
  not the generic end-user create helper unchanged

### Recurring exceptions

Google recurring events may contain:

- moved instances
- cancelled instances
- exception instances keyed by `recurringEventId` and `originalStartTime`

The importer must not silently flatten away those exceptions.

Required behavior:

- v1 does not import exception-bearing Google recurring series as Coke `rrule`
  reminders
- if a Google recurring series contains moved or cancelled exception instances,
  v1 records that series as skipped/failed-with-warning in the import result
- v1 must never create a simplified Coke recurring reminder that would
  reintroduce cancelled occurrences or lose moved-instance semantics silently

This is the main correctness rule for recurring-event import.

### History interpretation for recurring series

The product asked to import all history, but per-occurrence backfill for
infinite recurring series is not a sane first-version behavior.

Therefore:

- one-shot historical events are materialized as imported `completed` reminder
  records
- exception-free recurring series are imported as recurring reminders anchored
  at their original series start
- v1 does not materialize every historical instance of an open-ended recurring
  series as separate completed reminders
- exception-bearing recurring series are surfaced as partial import failures,
  not backfilled into an unbounded set of one-shot reminders

This preserves the user's recurring system without creating unbounded record
explosions.

## Duplicate Protection

The first version is intentionally not a sync product, but it still should not
accidentally create obvious duplicates inside a single customer account.

Required behavior:

- within one import run, deduplicate repeated Google payload entries by source
  event identity
- across import runs, duplicate avoidance is best-effort only and uses the
  imported reminder metadata index described above
- when possible, skip creating a second imported Coke reminder if an existing
  reminder already carries the same Google source metadata for the same user
- do not overwrite or mutate an existing Coke reminder that the user has
  already edited locally

The UI should still warn that rerunning import is a migration action and may
pull in additional data that the user already imported previously.

## Security And Auth Rules

- Google import requires an authenticated customer session whose email is
  verified and whose identity is `active`
- unclaimed or pending identities cannot start Google OAuth
- normal web users in `pending` state must verify email before import
- import requires a resolved target private conversation before OAuth begins
- claim-entry links must be signed and short-lived
- Google OAuth must use signed `state`
- Google OAuth must use PKCE
- Google access tokens must be discarded after run completion
- no long-lived Google refresh token is stored in v1
- the internal runtime import surface must use server-to-server auth, not a
  public customer token
- v1 does not add a new subscription-specific gate inside this feature; any
  broader subscription gating remains a separate product decision

## Failure Handling

### Claim entry failures

- invalid or expired entry token -> show a recovery page that tells the user to
  request a fresh link from WhatsApp
- email already belongs to another active identity -> show a clear error and
  tell the user to log in or use another email
- missing or invalid post-claim continuation target -> safely fall back to the
  default post-claim destination

### Google import failures

- no valid target private conversation -> block import and tell the user to
  start or resume a Coke conversation first
- user cancels Google consent -> mark the run failed and return to the import
  page with a retry message
- Google callback or token exchange fails -> mark the run failed
- Google fetch exceeds the single interactive run budget or access token
  lifetime -> fail cleanly and require the user to rerun import
- Google API partial fetch issues -> if any reminders were imported, prefer
  `succeeded_with_errors` over hard failure
- exception-bearing recurring series -> count them in `skippedCount` or
  `failedCount` with a user-visible warning
- runtime import rejects specific events -> count them in `failedCount`, keep
  the batch result visible, and do not roll back successfully imported
  reminders

## Verification Expectations

Implementation should include at least:

- gateway API tests for:
  - claim-request entry flow
  - Google OAuth start/callback handling
  - import-run status handling
- gateway web tests for:
  - claim-entry page
  - post-claim redirect into import flow
  - import summary UI states
- worker/bridge tests for:
  - batch import endpoint auth
  - single-event import
  - all-day event import
  - recurring series import
  - recurring exception safe fallback behavior
  - historical event lifecycle mapping

## Rejected Alternatives

### 1. Keep a long-lived Google connection from day one

Rejected because it pushes the first version into full sync territory:

- refresh token storage
- incremental sync tokens
- event-link mapping
- resync conflict rules

This is too heavy for the approved product scope.

### 2. Let gateway write Mongo reminders directly

Rejected because it duplicates reminder business logic and breaks the current
repository boundary where Coke runtime owns reminder semantics.

### 3. Add phone login for WhatsApp users

Rejected because the current repository does not implement a phone/SMS auth
stack, while the existing claim flow already supports password setup on top of
an owned email identity.

## Acceptance Criteria

- A claimed Coke customer can import their Google `primary` calendar into Coke
  reminders.
- Imported reminders become Coke-owned reminders immediately after import.
- No long-lived Google token or connection is stored.
- Shared WhatsApp auto-provisioned users are guided through email claim before
  import.
- The import preserves Google reminder timing semantics within Coke's single
  reminder model.
- Imported reminders always attach to a resolved private Coke conversation.
- Historical single events do not schedule future work after import.
- Exception-bearing recurring Google series are not silently flattened into
  misleading Coke recurrence rules.
- The system records batch-level import audit state in Postgres.
