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
- import all calendar events
- convert imported events into Coke-owned reminders
- do not keep an ongoing Google connection
- do not sync updates back to Google
- do not re-sync future Google edits into Coke

This design must also support the shared WhatsApp path where a user already
exists in Coke as an auto-provisioned, `unclaimed` customer before they ever
visit the web app.

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
- past single events become non-triggering historical reminder records
- open-ended recurring events should become Coke recurring reminders
- users auto-created from WhatsApp must claim their account before importing
- WhatsApp claim entry opens with an "enter your email" page first
- claim completion reuses the existing password-setting flow

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

### 4. Persist only import-run audit, not a long-lived Google connection

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

### 5. Use least-privilege Google access

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
3. Coke creates an import run in `authorizing` state.
4. Gateway redirects the user to Google OAuth.
5. Google redirects back to Coke.
6. Gateway exchanges the code for a short-lived access token.
7. Gateway reads the user's `primary` calendar events.
8. Gateway hands the normalized payload to a Coke internal import endpoint.
9. Coke runtime creates reminders in `deferred_actions`.
10. Gateway records the final import result and shows a summary screen.

### Flow B: Unclaimed shared WhatsApp customer imports Google Calendar

1. User asks for a web-only capability in WhatsApp, such as calendar import.
2. Coke replies with a short-lived claim-entry link.
3. User opens the link and lands on a claim-entry page.
4. User enters an email address.
5. Gateway sends a claim email to that address.
6. User opens the claim email and lands on the existing `/auth/claim` page.
7. User sets a password.
8. Claim completes and the identity becomes `active`.
9. The user is redirected into the calendar import entry screen.
10. The normal claimed-user import flow begins.

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

No phone-number-specific branch is added.

### Import screen

The import screen should clearly state:

- this imports the user's Google `primary` calendar
- imported events become Coke reminders
- changes made later in Google will not sync automatically
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

## API And Route Additions

### Gateway web

- add a claim-entry page, for example `/auth/claim-entry`
- add an authenticated customer import entry page in the account area

### Gateway API

- add a public claim-request endpoint, for example `POST /api/auth/claim/request`
- add an authenticated calendar import start endpoint
- add a Google OAuth callback endpoint
- add an import-run status endpoint

### Coke bridge / internal import surface

Add a new bridge-authenticated internal endpoint for Google Calendar import.

The exact path name can follow the current bridge naming style, but the design
requires:

- gateway must not write reminders directly into Mongo
- gateway must not reimplement reminder recurrence logic
- runtime reminder creation must stay in Coke-owned code

## Mapping Rules: Google Event -> Coke Reminder

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

Method-specific Google reminder channels such as `email` versus `popup` are not
preserved because Coke reminder delivery is governed by Coke's own delivery
system.

### Single events

- future single events become active one-shot Coke reminders
- past single events become historical non-triggering reminders
- historical imported events should use a non-active lifecycle state so they do
  not schedule future work

### Recurring events

The importer must preserve recurring series as faithfully as Coke's runtime can
represent them.

Rules:

- simple recurring series become one Coke recurring reminder
- open-ended recurring series remain recurring Coke reminders
- the recurring reminder keeps the original series start so recurrence stays
  semantically correct

### Recurring exceptions

Google recurring events may contain:

- moved instances
- cancelled instances
- exception instances keyed by `recurringEventId` and `originalStartTime`

The importer must not silently flatten away those exceptions.

Required behavior:

- if Coke can represent the recurrence set losslessly, import the recurrence
  set directly
- if Coke cannot represent the series losslessly, degrade safely by importing
  concrete one-shot reminders for the affected series or affected exception
  window rather than silently dropping exceptions

This is the main correctness rule for recurring-event import.

### History interpretation for recurring series

The product asked to import all history, but per-occurrence backfill for
infinite recurring series is not a sane first-version behavior.

Therefore:

- one-shot historical events are materialized as historical reminder records
- recurring series are imported as recurring reminders anchored at their
  original series start
- v1 does not materialize every historical instance of an open-ended recurring
  series as separate completed reminders

This preserves the user's recurring system without creating unbounded record
explosions.

## Duplicate Protection

The first version is intentionally not a sync product, but it still should not
accidentally create obvious duplicates inside a single customer account.

Required behavior:

- within one import run, deduplicate repeated Google payload entries by source
  event identity
- when possible, skip creating a second imported Coke reminder if an existing
  reminder already carries the same Google source metadata for the same user
- do not overwrite or mutate an existing Coke reminder that the user has
  already edited locally

The UI should still warn that rerunning import is a migration action and may
pull in additional data that the user already imported previously.

## Security And Auth Rules

- Google import requires an authenticated customer session whose `claimStatus`
  is `active`
- unclaimed or pending identities cannot start Google OAuth
- claim-entry links must be signed and short-lived
- Google OAuth must use signed `state`
- Google OAuth must use PKCE
- Google access tokens must be discarded after run completion
- no long-lived Google refresh token is stored in v1
- bridge import endpoint must use the existing bridge auth pattern, not a
  public customer token

## Failure Handling

### Claim entry failures

- invalid or expired entry token -> show a recovery page that tells the user to
  request a fresh link from WhatsApp
- email already belongs to another active identity -> show a clear error and
  tell the user to log in or use another email

### Google import failures

- user cancels Google consent -> mark the run failed and return to the import
  page with a retry message
- Google callback or token exchange fails -> mark the run failed
- Google API partial fetch issues -> if any reminders were imported, prefer
  `succeeded_with_errors` over hard failure
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
- Recurring exceptions are preserved or degraded safely; they are never
  silently dropped.
- The system records batch-level import audit state in Postgres.
