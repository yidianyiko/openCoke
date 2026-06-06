# Friend-Link Channel-Optional Joiner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated or claimed Coke user establish active friendship from a friend link even when the joining account has no usable channel.

**Architecture:** Keep SocialScheduling as the domain owner for friend-link establishment. Remove the joiner-channel precondition from the domain join path while keeping owner reachability, authentication, self-friendship, duplicate-active, and shared-reminder reachability rules intact.

**Tech Stack:** Python Flask backend, SocialScheduling domain service, pytest, Next.js/React web client, Vitest, repository docs.

---

## File Structure

- Modify `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`: replace the stale deferred self-completion test with the new channel-optional joiner contract.
- Modify `coke/domains/social_scheduling/models.py`: narrow `FriendshipResult.status` to current join results.
- Modify `coke/domains/social_scheduling/service.py`: remove joiner reachability gating from `_establish_from_link(...)`; leave `complete_deferred_friend_link(...)` as an obsolete old-artifact adapter only if current callers still need it.
- Modify `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`: assert `/api/friends/join` serializes `created` with a friendship id.
- Modify `web/lib/customer-friends.ts`: remove `deferred_channel_required` from the current web join result type.
- Modify `web/app/(customer)/account/friends/page.tsx`: remove the current-product branch that turns deferred join into a channel-required notice.
- Modify `web/app/(customer)/account/friends/page.test.tsx`: remove the stale deferred notice test; keep success, auth redirect, and self-friendship tests.
- Modify `web/lib/i18n.ts`: remove the now-unused `inviteNeedsChannel` message from friend-page copy.
- Modify `docs/product-requirements/current.md`: update the Friendship requirement so joiner channel is not required for friendship creation.

---

### Task 1: Backend Domain Contract

**Files:**
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/domains/social_scheduling/service.py`

- [x] **Step 1: Write the failing service test**

Replace `test_deferred_self_completion_when_joiner_has_no_usable_channel` in `tests/unit/coke/social_scheduling/test_social_scheduling_service.py` with:

```python
def test_friend_link_join_creates_active_friendship_without_joiner_channel():
    service, repo, _reachability, _availability = make_service({"owner"})
    link = service.get_or_create_friend_link("owner")

    result = service.establish_friendship_from_token("joiner", link.public_token)

    assert result.status == "created"
    assert result.friendship is not None
    assert result.friendship.lifecycle == "active"
    assert result.continuation == {}
    assert {friend.account_id for friend in service.list_friends("owner")} == {
        "joiner"
    }
    assert {friend.account_id for friend in service.list_friends("joiner")} == {
        "owner"
    }
    assert repo.list_active_friends("owner") == ["joiner"]
```

- [x] **Step 2: Run the service test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_join_creates_active_friendship_without_joiner_channel -v
```

Expected: FAIL because the current implementation returns `deferred_channel_required` and no friendship.

- [x] **Step 3: Implement minimal domain change**

In `coke/domains/social_scheduling/models.py`, change:

```python
status: Literal["created", "already_active", "deferred_channel_required"]
```

to:

```python
status: Literal["created", "already_active"]
```

In `coke/domains/social_scheduling/service.py`, change `complete_deferred_friend_link(...)` to call `_establish_from_link(...)` without `allow_defer`:

```python
        return self._establish_from_link(
            joiner_account_id,
            link,
            commit_guard=commit_guard,
        )
```

Then change `_establish_from_link(...)` from:

```python
    def _establish_from_link(
        self,
        joiner_account_id: str,
        link: FriendLink,
        allow_defer: bool = True,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
```

to:

```python
    def _establish_from_link(
        self,
        joiner_account_id: str,
        link: FriendLink,
        commit_guard: CommitGuard = None,
    ) -> FriendshipResult:
```

Remove this block from `_establish_from_link(...)`:

```python
        if not self.reachability.has_usable_channel(joiner_account_id):
            if allow_defer:
                return FriendshipResult(
                    status="deferred_channel_required",
                    friendship=None,
                    continuation={"friend_link_id": link.id},
                )
            raise SocialSchedulingError("joiner_channel_required")
```

- [x] **Step 4: Run service verification**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_join_creates_active_friendship_without_joiner_channel tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friendship_establishment_requires_owner_still_has_usable_channel tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_active_friendship_is_unique_and_removed_pair_can_reestablish -v
```

Expected: PASS.

---

### Task 2: Route And Channel-Reachability Tests

**Files:**
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`
- Modify: `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`

- [x] **Step 1: Add route serialization assertion**

In `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`, add this test after `test_friend_routes_are_thin_service_adapters`:

```python
def test_join_route_serializes_created_friendship_result():
    client, _service, _identity = make_client()

    response = client.post(
        "/api/friends/join", json={"public_token": "public_token"}
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "created",
        "friendship_id": "friendship_1",
        "continuation": {},
    }
```

- [x] **Step 2: Update channel-reachability old deferred test**

In `tests/unit/coke/channel_reachability/test_channel_reachability_service.py`, update `test_claimed_friend_link_self_completes_when_joiner_connects_channel` so it asserts the friendship already exists before channel connection:

```python
    created = social.establish_friendship_from_token(
        joiner_account_id=joiner.account.id,
        public_token=link.public_token,
    )
    claim = identity_service.issue_web_claim_code(
        browser_session="browser_1",
        continuation=created.continuation,
    )
```

and replace the final assertions with:

```python
    assert created.status == "created"
    assert social_repository.list_active_friends(owner.id) == [joiner.account.id]
    assert len(social_repository.friendships_by_id) == 1
    assert (
        identity_service.consume_deferred_friend_link_continuations(joiner.account.id)
        == []
    )
```

- [x] **Step 3: Run route/reachability tests and verify RED if code is not implemented yet, otherwise GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_join_route_serializes_created_friendship_result tests/unit/coke/channel_reachability/test_channel_reachability_service.py::test_claimed_friend_link_self_completes_when_joiner_connects_channel -v
```

Expected after Task 1 implementation: PASS.

---

### Task 3: Web Join Flow Cleanup

**Files:**
- Modify: `web/lib/customer-friends.ts`
- Modify: `web/app/(customer)/account/friends/page.tsx`
- Modify: `web/app/(customer)/account/friends/page.test.tsx`
- Modify: `web/lib/i18n.ts`

- [x] **Step 1: Write failing web expectation by removing stale deferred test**

Delete the test named `shows a channel-required notice when the clean join is deferred` from `web/app/(customer)/account/friends/page.test.tsx`.

- [x] **Step 2: Update TypeScript join result type**

In `web/lib/customer-friends.ts`, change:

```ts
  status: 'created' | 'already_active' | 'deferred_channel_required';
```

to:

```ts
  status: 'created' | 'already_active';
```

- [x] **Step 3: Remove the deferred branch from the friends page**

In `web/app/(customer)/account/friends/page.tsx`, delete:

```ts
        if (res.data.status === 'deferred_channel_required') {
          setNotice(copy.inviteNeedsChannel);
          return;
        }
```

Update the dependency list from:

```ts
    [copy.actionFailure, copy.inviteNeedsChannel, copy.inviteSelf, copy.inviteSent, loadData, replace],
```

to:

```ts
    [copy.actionFailure, copy.inviteSelf, copy.inviteSent, loadData, replace],
```

- [x] **Step 4: Remove unused copy**

In `web/lib/i18n.ts`, remove `inviteNeedsChannel: string;` from the friends page message type and remove both locale entries:

```ts
inviteNeedsChannel: 'Connect a messaging channel first, then open this friend link again.',
```

and:

```ts
inviteNeedsChannel: '请先连接消息通道，然后再打开这条好友链接。',
```

- [x] **Step 5: Run web friends test**

Run:

```bash
cd web && pnpm test -- app/\\(customer\\)/account/friends/page.test.tsx
```

Expected: PASS.

---

### Task 4: Product Requirement Update

**Files:**
- Modify: `docs/product-requirements/current.md`

- [x] **Step 1: Update the top feature matrix Friendship row**

In row `| 7 | Core journey: friendship |`, replace the sentence:

```text
Establishing active friendship also requires the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account, and to have a usable personal channel, so both friends always have a usable channel at establishment time.
```

with:

```text
Establishing active friendship requires the joining user to be authenticated as a Coke user or to have claimed an existing messaging-first account; the joining user does not need a usable personal channel at friendship establishment time.
```

- [x] **Step 2: Update the detailed Friendship row**

In the detailed row `| Friendship | Friendship; shared reminders |`, replace:

```text
A user who visits a friend link can establish active friendship after authenticating as a Coke user or claiming an existing messaging-first account, and after connecting a usable personal channel.
```

with:

```text
A user who visits a friend link can establish active friendship after authenticating as a Coke user or claiming an existing messaging-first account, even if that joining account has not connected a usable personal channel yet.
```

- [x] **Step 3: Keep shared reminder reachability unchanged**

Confirm the detailed `Shared reminders` row still says each receiver must resolve to a usable personal channel before shared reminder creation. Do not change that row.

---

### Task 5: Verification, Commit, Deploy, Production Smoke

**Files:**
- No additional source files expected.

- [x] **Step 1: Run backend target tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/channel_reachability/test_channel_reachability_service.py -v
```

Expected: PASS.

- [x] **Step 2: Run web target tests**

Run:

```bash
cd web && pnpm test -- app/\\(customer\\)/account/friends/page.test.tsx
```

Expected: PASS.

- [x] **Step 3: Run web build**

Run:

```bash
cd web && pnpm build
```

Expected: PASS.

- [x] **Step 4: Run diff-aware routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: Commands complete. Run any additional targeted command they suggest if it is more specific than the tests already run.

- [ ] **Step 5: Commit implementation**

Run:

```bash
git status --short
git add coke/domains/social_scheduling/models.py coke/domains/social_scheduling/service.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/channel_reachability/test_channel_reachability_service.py web/lib/customer-friends.ts web/app/\(customer\)/account/friends/page.tsx web/app/\(customer\)/account/friends/page.test.tsx web/lib/i18n.ts docs/product-requirements/current.md docs/superpowers/plans/2026-06-06-friend-link-channel-optional-joiner.md
git commit -m "feat: allow friend link joins before channel connection"
```

Expected: one commit containing plan, code, tests, and product docs. Do not add unrelated `.agents/skills/coke-agent-smoke/`.

- [ ] **Step 6: Deploy clean stack to GCP**

Run:

```bash
scripts/deploy-compose-to-gcp.sh
```

Expected: deploy script completes, service health checks pass, and `coke-api`, `coke-worker`, `coke-web`, `postgres`, and `redis` are running.

- [ ] **Step 7: Production smoke with a channel-less joiner**

Use production API to register a marked temporary web-first account, do not connect a channel, then call `POST /api/friends/join` against the active olivers friend link code. Verify:

```text
join response status is created or already_active
friendship_id is non-null
temporary joiner has zero channel rows
friendship row is active between olivers and temporary joiner
GET /api/friends with the temporary session includes olivers
```

Use a marker like `channel_optional_join_smoke_YYYYMMDDTHHMMSSZ` in the email/display name. Do not delete unmarked production data.
