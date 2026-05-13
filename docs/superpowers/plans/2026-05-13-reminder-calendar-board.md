# Reminder Calendar Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Build `/account/reminders` as a customer weekly calendar board for listing, creating, editing, completing, and cancelling visible reminders.

**Status:** complete

**Architecture:** The customer web app calls gateway customer routes. Gateway authenticates the customer and forwards reminder commands to bridge-internal routes. The Python bridge executes against the existing ReminderService/ReminderDAO so Mongo `reminders` and scheduler behavior remain owned by the Reminder System.

**Tech Stack:** Python 3.12, Flask bridge, Mongo/PyMongo DAO, existing ReminderService, Hono TypeScript gateway, Next.js customer web app, Vitest, pytest.

---

## Files

- Modify: `dao/reminder_dao.py` - add owner-scoped local-date range query.
- Modify: `agent/reminder/service.py` - add owner-scoped list-by-local-date-range method.
- Create: `connector/clawscale_bridge/reminder_management_service.py` - bridge-facing reminder management adapter and serializers.
- Modify: `connector/clawscale_bridge/app.py` - wire bridge internal reminder routes.
- Modify: `tests/unit/dao/test_reminder_dao.py` - DAO range query coverage.
- Create or modify: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py` - bridge service unit coverage.
- Modify: `tests/unit/connector/clawscale_bridge/test_bridge_app.py` - bridge route coverage.
- Create: `gateway/packages/api/src/lib/reminder-runtime-client.ts` - gateway-to-bridge client.
- Create: `gateway/packages/api/src/lib/reminder-runtime-client.test.ts` - runtime client tests.
- Create: `gateway/packages/api/src/routes/customer-reminder-routes.ts` - authenticated customer reminder API.
- Create: `gateway/packages/api/src/routes/customer-reminder-routes.test.ts` - route tests.
- Modify: `gateway/packages/api/src/index.ts` - mount customer reminder routes.
- Modify: `gateway/packages/web/lib/customer-api.ts` - add `patch`.
- Create: `gateway/packages/web/lib/customer-reminders.ts` - web API wrapper and types.
- Create: `gateway/packages/web/lib/customer-reminders.test.ts` - web API wrapper tests.
- Modify: `gateway/packages/web/components/customer-shell.tsx` - add Reminders nav.
- Modify: `gateway/packages/web/app/(customer)/account/layout.test.tsx` - assert Reminders nav link is present.
- Create: `gateway/packages/web/app/(customer)/account/reminders/page.tsx` - weekly calendar board page.
- Create: `gateway/packages/web/app/(customer)/account/reminders/page.test.tsx` - page behavior tests.
- Modify: `gateway/packages/web/app/public-site.css` - customer reminder board styles.
- Modify: `docs/product-specs/FEATURE_TREE.md` - add customer reminder web surface.

## Task 1: Reminder System Range Query

**Files:**
- Modify: `dao/reminder_dao.py`
- Modify: `agent/reminder/service.py`
- Test: `tests/unit/dao/test_reminder_dao.py`
- Test: `tests/unit/reminder/test_service.py`

- [x] **Step 1: Add failing ReminderService range tests**

Append tests to `tests/unit/reminder/test_service.py` using the existing `InMemoryReminderDAO`.

Add this DAO method to the test double:

```python
def list_for_owner_in_local_date_range(
    self,
    owner_user_id: str,
    *,
    from_date: date,
    to_date: date,
    lifecycle_states: list[str],
) -> list[dict]:
    results = []
    for document in self.documents.values():
        if document["owner_user_id"] != owner_user_id:
            continue
        if document["lifecycle_state"] not in lifecycle_states:
            continue
        local_date = document["schedule"]["local_date"]
        if from_date <= local_date <= to_date:
            results.append(dict(document))
    return results
```

Add tests:

```python
def test_list_for_user_in_local_date_range_scopes_by_owner_and_state():
    service, dao, _ = make_service()
    service.create(owner_user_id="user-1", command=create_command(title="in range"))
    service.create(owner_user_id="user-2", command=create_command(title="other user"))
    cancelled = service.create(owner_user_id="user-1", command=create_command(title="cancelled"))
    service.cancel(reminder_id=cancelled.id, owner_user_id="user-1")

    reminders = service.list_for_user_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 29),
        lifecycle_states=["active"],
    )

    assert [reminder.title for reminder in reminders] == ["in range"]


def test_list_for_user_in_local_date_range_can_include_terminal_states():
    service, dao, _ = make_service()
    reminder = service.create(owner_user_id="user-1", command=create_command(title="done"))
    service.complete(reminder_id=reminder.id, owner_user_id="user-1")

    reminders = service.list_for_user_in_local_date_range(
        owner_user_id="user-1",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 29),
        lifecycle_states=["completed"],
    )

    assert [reminder.title for reminder in reminders] == ["done"]
```

- [x] **Step 2: Run service tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py::test_list_for_user_in_local_date_range_scopes_by_owner_and_state tests/unit/reminder/test_service.py::test_list_for_user_in_local_date_range_can_include_terminal_states -v
```

Expected: FAIL because `ReminderService.list_for_user_in_local_date_range` does not exist.

- [x] **Step 3: Implement ReminderService method**

Add to `agent/reminder/service.py`:

```python
    def list_for_user_in_local_date_range(
        self,
        *,
        owner_user_id: str,
        from_date: date,
        to_date: date,
        lifecycle_states: list[str],
    ) -> list[Reminder]:
        if from_date > to_date:
            raise InvalidArgument(
                "Reminder date range is invalid",
                detail={"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
            )
        documents = self.reminder_dao.list_for_owner_in_local_date_range(
            owner_user_id,
            from_date=from_date,
            to_date=to_date,
            lifecycle_states=lifecycle_states,
        )
        return [self._map_document(document) for document in documents]
```

- [x] **Step 4: Add DAO range query tests**

In `tests/unit/dao/test_reminder_dao.py`, add coverage using the existing DAO test pattern. Insert documents directly into the test collection with `owner_user_id`, `schedule.local_date`, `lifecycle_state`, and `next_fire_at`. Assert that `list_for_owner_in_local_date_range("user-1", from_date=date(2026, 5, 13), to_date=date(2026, 5, 19), lifecycle_states=["active"])` returns only that owner and state.

- [x] **Step 5: Run DAO test and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/dao/test_reminder_dao.py -v
```

Expected: FAIL because the DAO method does not exist.

- [x] **Step 6: Implement DAO method**

Add to `dao/reminder_dao.py`:

```python
    def list_for_owner_in_local_date_range(
        self,
        owner_user_id: str,
        *,
        from_date: date,
        to_date: date,
        lifecycle_states: List[str],
    ) -> List[Dict]:
        selector: Dict = {
            "owner_user_id": owner_user_id,
            "lifecycle_state": {"$in": lifecycle_states},
            "schedule.local_date": {
                "$gte": from_date,
                "$lte": to_date,
            },
        }
        return list(self.collection.find(selector).sort([("schedule.local_date", 1), ("schedule.local_time", 1)]))
```

Also import `date` from `datetime`. This first implementation intentionally uses `schedule.local_date`; recurrence expansion beyond the current stored reminder is out of scope.

- [x] **Step 7: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py -v
```

Expected: PASS.

## Task 2: Bridge Reminder Management Routes

**Files:**
- Create: `connector/clawscale_bridge/reminder_management_service.py`
- Modify: `connector/clawscale_bridge/app.py`
- Test: `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`
- Test: `tests/unit/connector/clawscale_bridge/test_bridge_app.py`

- [x] **Step 1: Write failing service tests**

Create `tests/unit/connector/clawscale_bridge/test_reminder_management_service.py`.

Cover:

- `list_reminders` calls `ReminderService.list_for_user_in_local_date_range` with owner id, dates, and states.
- `create_reminder` resolves the latest conversation and passes an `AgentOutputTarget`.
- `create_reminder` raises `ValueError("conversation_required")` when no conversation is found.
- `update_reminder`, `complete_reminder`, and `cancel_reminder` pass `owner_user_id`.
- invalid timezone or past one-shot maps to `ValueError("invalid_schedule")`.

- [x] **Step 2: Run service tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_reminder_management_service.py -v
```

Expected: FAIL because the module does not exist.

- [x] **Step 3: Implement bridge reminder management service**

Create `connector/clawscale_bridge/reminder_management_service.py` with:

- `ReminderManagementService`
- `serialize_reminder(reminder)`
- date/time parsing helpers
- `build_schedule(local_date, local_time, timezone, rrule)`
- latest conversation resolution using `conversation_dao.find_latest_private_conversation_by_db_user_ids(customer_id, character_id)`
- methods: `list_reminders`, `create_reminder`, `update_reminder`, `complete_reminder`, `cancel_reminder`

Use `ReminderCreateCommand`, `ReminderPatch`, `ReminderSchedule`, and `AgentOutputTarget` from `agent.reminder.models`.

- [x] **Step 4: Write failing bridge route tests**

Append tests to `tests/unit/connector/clawscale_bridge/test_bridge_app.py`:

- missing bearer token on `/bridge/internal/reminders` returns 401.
- `GET /bridge/internal/reminders?...` returns serialized reminders from configured service.
- `POST /bridge/internal/reminders` forwards customer id and body to service.
- `PATCH /bridge/internal/reminders/rem-1` forwards update.
- `POST /bridge/internal/reminders/rem-1/complete` forwards complete.
- `POST /bridge/internal/reminders/rem-1/cancel` forwards cancel.
- service `ValueError("conversation_required")` maps to HTTP 400 `{ok:false,error:"conversation_required"}`.

- [x] **Step 5: Run route tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_bridge_app.py -k "reminders" -v
```

Expected: FAIL because routes are not wired.

- [x] **Step 6: Wire app routes**

Modify `connector/clawscale_bridge/app.py`:

- add `_build_reminder_management_service()`
- set `app.config["REMINDER_MANAGEMENT_SERVICE"]` in non-testing mode
- add route handlers under `/bridge/internal/reminders`
- normalize missing service to `bridge_service_not_wired`
- reuse `require_bridge_auth`

- [x] **Step 7: Run bridge tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_reminder_management_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -k "reminder or reminders" -v
```

Expected: PASS.

## Task 3: Gateway Customer Reminder API

**Files:**
- Create: `gateway/packages/api/src/lib/reminder-runtime-client.ts`
- Create: `gateway/packages/api/src/lib/reminder-runtime-client.test.ts`
- Create: `gateway/packages/api/src/routes/customer-reminder-routes.ts`
- Create: `gateway/packages/api/src/routes/customer-reminder-routes.test.ts`
- Modify: `gateway/packages/api/src/index.ts`

- [x] **Step 1: Write failing runtime client tests**

Create tests for:

- bridge transport failure maps to `reminder_bridge_transport_failed`.
- invalid bridge JSON maps to `reminder_bridge_invalid_response`.
- list sends `customer_id`, date range, and states to `/bridge/internal/reminders`.
- create/update/complete/cancel send the expected method/path/body.

- [x] **Step 2: Run runtime client tests and verify failure**

Run:

```bash
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts
```

Expected: FAIL because the client module does not exist.

- [x] **Step 3: Implement runtime client**

Create `gateway/packages/api/src/lib/reminder-runtime-client.ts` using the same bridge base/header helpers as `google-calendar-runtime-client.ts`. Export:

- `listRuntimeReminders`
- `createRuntimeReminder`
- `updateRuntimeReminder`
- `completeRuntimeReminder`
- `cancelRuntimeReminder`

- [x] **Step 4: Write failing customer route tests**

Create `gateway/packages/api/src/routes/customer-reminder-routes.test.ts`.

Mock:

- `verifyCustomerToken`
- `getCustomerSession`
- runtime client methods

Cover:

- unauthenticated request returns 401.
- inactive claim returns 403.
- list uses authenticated `session.customerId`.
- request body cannot override customer id.
- create maps `conversation_required` to 409 or 400 with same error code.
- update/complete/cancel forward reminder id and authenticated customer id.

- [x] **Step 5: Run route tests and verify failure**

Run:

```bash
cd gateway/packages/api && npm test -- src/routes/customer-reminder-routes.test.ts
```

Expected: FAIL because routes do not exist.

- [x] **Step 6: Implement customer reminder routes**

Create `gateway/packages/api/src/routes/customer-reminder-routes.ts`:

- auth middleware copied in style from customer channel/subscription routes.
- zod validators for list query, create body, update body.
- defaults: `states=active`, seven-day range if omitted can use current date from request runtime only if tests pin it; otherwise require `from` and `to`.
- max range: 31 days.
- route methods matching the spec.

Mount in `gateway/packages/api/src/index.ts`:

```ts
app.route('/api/customer/reminders', customerReminderRouter);
```

- [x] **Step 7: Run gateway tests**

Run:

```bash
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
```

Expected: PASS.

## Task 4: Web Reminder Client and Weekly Board

**Files:**
- Modify: `gateway/packages/web/lib/customer-api.ts`
- Create: `gateway/packages/web/lib/customer-reminders.ts`
- Create: `gateway/packages/web/lib/customer-reminders.test.ts`
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Create: `gateway/packages/web/app/(customer)/account/reminders/page.tsx`
- Create: `gateway/packages/web/app/(customer)/account/reminders/page.test.tsx`
- Modify: `gateway/packages/web/app/public-site.css`

- [x] **Step 1: Write failing web API wrapper tests**

Create `gateway/packages/web/lib/customer-reminders.test.ts` and mock `customerApi`.

Cover:

- `listCustomerReminders({ from, to, states })` calls `/api/customer/reminders?...`.
- `createCustomerReminder` posts title/localDate/localTime/timezone/rrule.
- `updateCustomerReminder` uses `customerApi.patch`.
- `completeCustomerReminder` and `cancelCustomerReminder` post to action routes.

- [x] **Step 2: Run wrapper tests and verify failure**

Run:

```bash
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts
```

Expected: FAIL because wrapper and `customerApi.patch` do not exist.

- [x] **Step 3: Implement web API wrapper**

Add `patch` to `gateway/packages/web/lib/customer-api.ts`.

Create `gateway/packages/web/lib/customer-reminders.ts` with exported types and functions used by the page.

- [x] **Step 4: Write failing page tests**

Create `gateway/packages/web/app/(customer)/account/reminders/page.test.tsx`.

Mock `next/navigation`, `customer-reminders`, and `next/link`.

Cover:

- renders seven day columns for the current week.
- groups returned reminders by `localDate`.
- clicking create opens a drawer/form.
- submitting create calls `createCustomerReminder`.
- `conversation_required` displays the chat-first blocked state.
- clicking an existing reminder opens edit drawer.
- save calls `updateCustomerReminder`.
- complete and cancel call their actions.

- [x] **Step 5: Run page test and verify failure**

Run:

```bash
cd gateway/packages/web && npm test -- app/'(customer)'/account/reminders/page.test.tsx
```

Expected: FAIL because page does not exist.

- [x] **Step 6: Implement weekly board page**

Create `gateway/packages/web/app/(customer)/account/reminders/page.tsx`:

- client component.
- compute Monday-Sunday for selected week.
- load reminders for the week with active state by default.
- render seven columns.
- drawer state for create/edit.
- default timezone from `Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'`.
- handle auth errors by `router.replace('/auth/login?next=/account/reminders')`.
- handle `conversation_required` as blocked inline message with link to `/channels/wechat-personal`.

Modify `gateway/packages/web/components/customer-shell.tsx` to add:

```ts
{ href: '/account/reminders', label: 'Reminders' }
{ href: '/account/reminders', label: '提醒' }
```

Add scoped CSS classes for the calendar board, day columns, reminder buttons, drawer, and form in `public-site.css`.

- [x] **Step 7: Run web tests**

Run:

```bash
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
```

Expected: PASS.

## Task 5: Docs and Integrated Verification

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Modify: `docs/fitness/coke-verification-matrix.md`

- [x] **Step 1: Update product surface docs**

Add `/account/reminders` under the customer/account web surfaces in `docs/product-specs/FEATURE_TREE.md`, and mention the gateway customer reminder API plus bridge internal reminder API under Reminder System surfaces.

Add focused customer reminder verification commands to `docs/fitness/coke-verification-matrix.md` near the existing reminder-system command set:

```bash
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
```

- [x] **Step 2: Run focused verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/reminder/test_service.py tests/unit/dao/test_reminder_dao.py tests/unit/connector/clawscale_bridge/test_reminder_management_service.py tests/unit/connector/clawscale_bridge/test_bridge_app.py -k "reminder or reminders" -v
cd gateway/packages/api && npm test -- src/lib/reminder-runtime-client.test.ts src/routes/customer-reminder-routes.test.ts
cd gateway/packages/web && npm test -- lib/customer-reminders.test.ts app/'(customer)'/account/reminders/page.test.tsx app/'(customer)'/account/layout.test.tsx
```

Expected: all focused tests pass.

- [x] **Step 3: Run diff-aware routing**

From repo root:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Run any additional commands they recommend for touched surfaces.

- [x] **Step 4: Run structure check if docs/routing changed**

Run:

```bash
zsh scripts/check
```

Expected: PASS or document unrelated failures with evidence.

- [x] **Step 5: Final git review**

Run:

```bash
git status --short
git diff --stat
git diff --check
```

Expected: only intended files changed and no whitespace errors.
