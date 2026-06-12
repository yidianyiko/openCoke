# WeChat Channel Auto QR Design

## Status

approved-for-plan (2026-06-12). The product decision is to reduce first-use
friction by automatically starting the personal-WeChat QR login when an eligible
logged-in user lands on an empty WeChat channel page.

## Context

Registration and login already route web-first users to
`/channels/wechat-personal`. The current page then loads channel status and, if
the account has no active personal channel, shows a manual "Create my WeChat
channel" call to action. The next click calls the same clean channel endpoint
that starts the iLink login and returns a pending QR state.

The current product contract remains unchanged:

- Web-first onboarding completion still requires registration or login, one
  usable personal channel, and one successfully received personal-channel
  inbound message.
- Personal WeChat remains web-first and connection-first.
- A pending QR is not a connected channel and must not be treated as onboarding
  complete.
- Account access gates still fail closed before channel connection.

## Decision

When `/channels/wechat-personal` finishes profile/access checks and receives a
fresh channel status of `missing`, the page starts the WeChat connection flow
automatically. The user should land directly on the QR/pending experience when
the provider can produce a QR.

This applies whenever an eligible account opens the page with a `missing`
personal-WeChat state, not only immediately after registration. Existing
non-missing states are left alone:

- `pending`: keep showing the current QR and polling its session.
- `connected`: show the connected state.
- `disconnected`: keep the explicit reconnect action.
- `error`: keep retry/archive actions.
- `archived`: keep the explicit create-again action.

## Alternatives Considered

1. Keep the manual create button. This preserves maximum explicitness, but it
   adds a redundant step after registration or login and delays the QR that the
   user already needs.
2. Auto-start only when registration/login passes a special `source=auth`
   marker. This avoids surprising repeat visits, but it creates a second
   routing contract and leaves other legitimate empty-channel landings with the
   same unnecessary click.
3. Auto-start on any eligible `missing` state. This is the selected approach:
   the status machine stays authoritative, the backend remains idempotent for
   active channels, and the empty first-use page becomes immediately actionable.

## Frontend Behavior

The WeChat channel page keeps the existing load order:

1. Verify a customer token exists.
2. Refresh the customer profile.
3. Stop on suspended, unverified, or inactive-subscription access states.
4. Load channel status.
5. If the loaded status is `missing`, run the create/connect mutation once for
   the current page instance.

The auto-start guard must prevent loops:

- Do not auto-start while another channel mutation is busy.
- Do not auto-start more than once for the same page instance after a `missing`
  status response.
- Do not auto-start after a mutation failure unless the user clicks the visible
  retry/create action.
- Do not auto-start from stale refresh responses that lose to a newer mutation.

The visible loading state should say that the QR is being prepared. If auto-start
succeeds, the existing pending QR UI is shown. If it fails, the page falls back to
the existing missing-channel UI with an error message and the manual create
button still available.

## Backend And Data Flow

No backend endpoint change is required. The frontend continues to use
`POST /api/channels/wechat-personal/connect` through
`createCustomerWechatChannel()`.

The backend remains the source of truth:

- If there is no active channel, `start_wechat_personal_connection` starts the
  iLink QR login and returns `connection_state: connecting`.
- If an active channel already exists, the service returns current status instead
  of creating a second reachable channel.
- Login polling still uses the returned `session_id`.

## Error Handling

Automatic QR generation failure is recoverable and user-visible:

- Preserve the current `missing` state when the create/connect call fails.
- Show the existing channel error copy.
- Keep the manual create button enabled after the failed mutation finishes.
- Do not sign the user out or clear auth for provider/connect failures.

Profile refresh, account-access, and initial status-load failures retain their
current behavior.

## Testing

Focused frontend tests should cover:

- A `missing` status auto-calls `createCustomerWechatChannel` and renders the
  returned pending QR without requiring a click.
- The auto-start does not fire for `pending`, `connected`, blocked-access, or
  status-load failure states.
- A failed auto-start keeps the missing-channel action visible and surfaces the
  recoverable error.
- Existing refresh ordering still keeps fresher mutation QR data over stale poll
  results.

Existing API helper and backend channel reachability tests are sufficient unless
implementation reveals a backend contract gap; the intended change is a
frontend state-machine behavior change.
