# Friend Management Page Design

## Plain-Language Product Story

A Kap user should not need to ask the agent to manage every friend action.
After registration and email verification, the user can open one dedicated web
page to share their own add-friend link, review incoming and outgoing friend
requests, accept or reject requests, cancel requests they sent, and remove
existing friends.

This page is the web management surface for the friend-link system already
defined by `2026-05-21-user-link-scheduling-design.md`. It does not replace the
agent tools. The web page and agent tools call the same Gateway scheduling
state transitions.

## Goal

Add a first-version customer web page for full friend management:

- show and manage the user's public add-friend link
- show incoming friend requests
- show outgoing friend requests
- show accepted friends
- support the obvious actions for each list

The page should make friend state visible and operable without requiring a chat
conversation.

## Scope

Included:

- New customer route: `/account/friends`.
- Customer navigation entry: `Friends` / `好友`.
- Frontend API wrapper for the existing scheduling endpoints.
- Page sections for:
  - My friend link
  - Incoming requests
  - Outgoing requests
  - Friends
- Actions:
  - copy current friend link in the browser
  - reset friend link
  - disable the current friend link
  - accept incoming pending request
  - reject incoming pending request
  - cancel outgoing pending request
  - remove an existing friend
- Auth handling consistent with other customer account pages.
- Focused frontend tests for route rendering, API calls, auth failure routing,
  and action refresh behavior.

Excluded from this first version:

- New backend models or route shape changes.
- Search, pagination, sorting controls, friend notes, groups, or aliases.
- Block/unblock UI, even though the backend has block APIs.
- Shared reminder management UI.
- Real-time updates or websocket refresh.
- Bulk actions.

## Existing Backend Contract

The first version must reuse the existing Gateway scheduling endpoints:

- `GET /api/customer/scheduling/user-link`
- `POST /api/customer/scheduling/user-link/reset`
- `POST /api/customer/scheduling/user-link/disable`
- `GET /api/customer/scheduling/friend-requests`
- `POST /api/customer/scheduling/friend-requests/:id/accept`
- `POST /api/customer/scheduling/friend-requests/:id/reject`
- `POST /api/customer/scheduling/friend-requests/:id/cancel`
- `GET /api/customer/scheduling/friends`
- `DELETE /api/customer/scheduling/friends/:friendshipId`

The page must not introduce a parallel friend API. If an existing response
shape is inconvenient, adapt it in the web client layer rather than changing
the product state contract in this slice.

## Page Structure

### My Friend Link

The top section shows the active public user link returned by
`GET /api/customer/scheduling/user-link`.

Controls:

- Copy: copies the URL to the clipboard and shows a short local success state.
- Reset: calls `POST /api/customer/scheduling/user-link/reset`, then refreshes
  the link and request/friend data.
- Disable current link: calls
  `POST /api/customer/scheduling/user-link/disable`, then shows a local state
  that the current link was disabled. Because the existing read endpoint is
  get-or-create, this first version must not present disable as a permanent
  "turn off friend links" setting. It only invalidates the current URL. A later
  reload or explicit refresh may create a new active link through the existing
  backend contract.

Copy is a browser-only action and must not require a backend request.

### Incoming Requests

Incoming requests are friend requests where the current user is the target.
Pending incoming requests show Accept and Reject actions.

Terminal requests may be shown as read-only rows if returned by the backend,
but they must not offer actions. If the backend returns only active or recent
requests, the page should simply render what it receives.

### Outgoing Requests

Outgoing requests are friend requests where the current user is the requester.
Pending outgoing requests show a Cancel action.

Terminal outgoing requests are read-only.

### Friends

The friends section lists active friendships returned by
`GET /api/customer/scheduling/friends`.

Each row shows the other account's public display name when available and a
Remove action. Removing a friendship calls
`DELETE /api/customer/scheduling/friends/:friendshipId`, then refreshes the
friend and request lists.

## Auth And Empty States

The page uses the same customer auth pattern as `/account/my-agent` and
`/account/reminders`.

- `unauthorized`, `invalid_or_expired_token`, or `account_not_found` redirect
  to `/auth/login?next=/account/friends`.
- `claim_inactive` redirects to `/auth/login?next=/account/friends`, matching
  the existing account-page auth failure pattern.
- Empty incoming requests, outgoing requests, and friends each have their own
  quiet empty state.
- Backend action failures stay on the page and show an inline error near the
  affected section or at the top of the page.

## Data Flow

On load, the page fetches the friend link, friend requests, and friends.

After any successful mutation, the page refreshes the affected data from the
backend. The first implementation can refresh all three datasets after each
mutation for simplicity; optimizing to partial refresh is not required.

The page should derive incoming versus outgoing requests on the client from the
current authenticated customer id and the request DTO fields returned by
`GET /api/customer/scheduling/friend-requests`.

## Internationalization

User-visible strings must use the existing `messages`/locale pattern rather
than hardcoded English-only labels.

Required English labels include:

- Friends
- My friend link
- Incoming requests
- Outgoing requests
- Current friends
- Copy link
- Reset link
- Disable link
- Accept
- Reject
- Cancel request
- Remove friend

Required Chinese labels include:

- 好友
- 我的好友链接
- 收到的请求
- 发出的请求
- 当前好友
- 复制链接
- 重置链接
- 停用链接
- 接受
- 拒绝
- 取消请求
- 删除好友

## Testing

Frontend tests should cover:

- the customer shell navigation includes `/account/friends`
- unauthenticated or inactive sessions redirect to
  `/auth/login?next=/account/friends`
- the page fetches user link, friend requests, and friends on load
- incoming pending requests render Accept and Reject actions
- outgoing pending requests render Cancel action
- friends render Remove action
- each mutation calls the expected endpoint and refreshes data
- copy uses `navigator.clipboard.writeText` when available and shows success
- API wrapper tests for all new scheduling web-client functions

Backend tests are not required for this slice unless the implementation exposes
a missing backend response field or contract mismatch. If a backend contract
gap appears, stop and update this spec before changing backend behavior.

## Completion Criteria

The page is complete when:

- `/account/friends` exists and is reachable from the customer navigation.
- A verified customer can see their friend link, requests, and friends.
- Pending incoming requests can be accepted or rejected from the page.
- Pending outgoing requests can be cancelled from the page.
- Existing friends can be removed from the page.
- Relevant frontend tests pass.
- Verification evidence is reported with the exact commands used.
