# Friend Add Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show personalized friend-add feedback by carrying counterpart identity through the join result and rendering status-specific i18n copy.

**Architecture:** SocialScheduling owns the join outcome and enriches `FriendshipResult` with the link owner's account id and display name. API routes, the social scheduling tool adapter, the web API wrapper, and the Friends page pass those fields through without reintroducing pending friend-request behavior.

**Tech Stack:** Python dataclasses and Flask routes; pytest backend tests; Next.js React client; TypeScript API wrappers; Vitest web tests; existing Coke repo verification scripts.

---

## File Structure

- Modify `coke/domains/social_scheduling/models.py`: add counterpart fields to `FriendshipResult`.
- Modify `coke/domains/social_scheduling/service.py`: set counterpart fields for `created` and `already_active` link joins.
- Modify `coke/api/friend_routes.py`: serialize counterpart fields in join responses.
- Modify `coke/composition.py`: expose counterpart fields in social scheduling tool facts.
- Modify `web/lib/customer-friends.ts`: type and preserve join-result counterpart fields.
- Modify `web/lib/i18n.ts`: replace generic friend-join copy with parameterized status-specific copy and distinct invalid/disabled link errors.
- Modify `web/app/(customer)/account/friends/page.tsx`: render personalized join notices and map clean join errors explicitly.
- Modify `docs/product-specs/FEATURE_TREE.md`: document that authenticated friend joins return counterpart identity.
- Test `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`: domain join result identity.
- Test `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`: HTTP join serialization.
- Test `tests/unit/coke/test_social_scheduling_tool_adapter.py`: tool-adapter facts.
- Test `web/lib/customer-friends.test.ts`: web wrapper join identity.
- Test `web/app/(customer)/account/friends/page.test.tsx`: logged-out handoff plus personalized created/already-active notices.

---

### Task 1: Backend Join Result Contract

**Files:**
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `coke/api/friend_routes.py`
- Modify: `coke/composition.py`

- [x] **Step 1: Add failing service tests for counterpart identity**

In `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`, update `test_friend_link_join_creates_active_friendship_without_joiner_channel`:

```python
    service.display_name_resolver = lambda account_id: {
        "owner": "Oliver",
        "joiner": "Eva",
    }[account_id]
```

Then add these assertions after the existing `result.continuation == {}` assertion:

```python
    assert result.counterpart_account_id == "owner"
    assert result.counterpart_display_name == "Oliver"
```

In `test_active_friendship_is_unique_and_removed_pair_can_reestablish`, set the resolver before creating the link:

```python
    service.display_name_resolver = lambda account_id: {
        "owner": "Oliver",
        "joiner": "Eva",
    }[account_id]
```

Then add these assertions after `assert second.friendship.id == first.friendship.id`:

```python
    assert second.counterpart_account_id == "owner"
    assert second.counterpart_display_name == "Oliver"
```

- [x] **Step 2: Run service tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_join_creates_active_friendship_without_joiner_channel \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_active_friendship_is_unique_and_removed_pair_can_reestablish \
  -v
```

Expected: FAIL with `AttributeError: 'FriendshipResult' object has no attribute 'counterpart_account_id'`.

- [x] **Step 3: Add failing route and adapter expectations**

In `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`, update each fake friendship result returned by `FakeSocialSchedulingService.establish_friendship_from_token`, `establish_friendship_from_code`, and `complete_deferred_friend_link`:

```python
            counterpart_account_id="friend",
            counterpart_display_name="Alice Push",
```

Update `test_join_route_serializes_created_friendship_result` expected JSON:

```python
    assert response.get_json() == {
        "status": "created",
        "friendship_id": "friendship_1",
        "counterpart_account_id": "friend",
        "counterpart_display_name": "Alice Push",
        "continuation": {},
    }
```

In `tests/unit/coke/test_social_scheduling_tool_adapter.py`, update `test_establish_friendship_operation_accepts_visible_invite_code` expected facts:

```python
    assert result.facts == {
        "status": "created",
        "friendship_id": "friendship_1",
        "counterpart_account_id": "friend",
        "counterpart_display_name": "Alice Push",
        "continuation": {},
    }
```

Update `FakeFriendshipResult`:

```python
class FakeFriendshipResult:
    status = "created"
    friendship = FakeFriendship()
    counterpart_account_id = "friend"
    counterpart_display_name = "Alice Push"
    continuation: dict[str, Any] = {}
```

- [x] **Step 4: Run route and adapter tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_join_route_serializes_created_friendship_result \
  tests/unit/coke/test_social_scheduling_tool_adapter.py::test_establish_friendship_operation_accepts_visible_invite_code \
  -v
```

Expected: FAIL because the route and adapter do not serialize counterpart fields yet.

- [x] **Step 5: Implement the backend contract**

In `coke/domains/social_scheduling/models.py`, replace `FriendshipResult` with:

```python
@dataclass(frozen=True, slots=True)
class FriendshipResult:
    status: Literal["created", "already_active"]
    friendship: Friendship | None
    counterpart_account_id: str
    counterpart_display_name: str
    continuation: dict[str, Any] = field(default_factory=dict)
```

In `coke/domains/social_scheduling/service.py`, add this helper inside `SocialSchedulingService` before `_create_friendship_notification`:

```python
    def _friendship_result(
        self,
        status: Literal["created", "already_active"],
        friendship: Friendship,
        counterpart_account_id: str,
    ) -> FriendshipResult:
        return FriendshipResult(
            status=status,
            friendship=friendship,
            counterpart_account_id=counterpart_account_id,
            counterpart_display_name=self.display_name_resolver(counterpart_account_id),
        )
```

Add `Literal` to the typing import if it is not already imported:

```python
from typing import Any, Callable, Literal, Protocol
```

In `_establish_from_link`, replace the already-active return:

```python
            return self._friendship_result(
                "already_active", active, link.owner_account_id
            )
```

Replace the created return:

```python
        return self._friendship_result("created", friendship, link.owner_account_id)
```

In `coke/api/friend_routes.py`, update `_friendship_result_body`:

```python
def _friendship_result_body(result) -> dict:
    return {
        "status": result.status,
        "friendship_id": (
            result.friendship.id if result.friendship is not None else None
        ),
        "counterpart_account_id": result.counterpart_account_id,
        "counterpart_display_name": result.counterpart_display_name,
        "continuation": result.continuation,
    }
```

In `coke/composition.py`, update the `establish_friendship_from_token` facts:

```python
                    facts={
                        "status": result.status,
                        "friendship_id": (
                            result.friendship.id if result.friendship else None
                        ),
                        "counterpart_account_id": result.counterpart_account_id,
                        "counterpart_display_name": result.counterpart_display_name,
                        "continuation": result.continuation,
                    },
```

- [x] **Step 6: Run backend contract tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_join_creates_active_friendship_without_joiner_channel \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_active_friendship_is_unique_and_removed_pair_can_reestablish \
  tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_join_route_serializes_created_friendship_result \
  tests/unit/coke/test_social_scheduling_tool_adapter.py::test_establish_friendship_operation_accepts_visible_invite_code \
  -v
```

Expected: PASS for all four tests.

---

### Task 2: Web Join Wrapper And Friends Page Copy

**Files:**
- Modify: `web/lib/customer-friends.test.ts`
- Modify: `web/app/(customer)/account/friends/page.test.tsx`
- Modify: `web/lib/customer-friends.ts`
- Modify: `web/lib/i18n.ts`
- Modify: `web/app/(customer)/account/friends/page.tsx`

- [x] **Step 1: Add failing web wrapper expectation**

In `web/lib/customer-friends.test.ts`, update the join mock in `joins a friend by clean link code and preserves created status`:

```typescript
    apiMock.post.mockResolvedValueOnce({
      status: 'created',
      friendship_id: 'friendship_1',
      counterpart_account_id: 'acct_oliver',
      counterpart_display_name: 'Oliver',
      continuation: {},
    });
```

Update the expected result:

```typescript
      data: {
        status: 'created',
        friendship_id: 'friendship_1',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
```

- [x] **Step 2: Add failing Friends page tests**

In `web/app/(customer)/account/friends/page.test.tsx`, change `renderPage` to accept a locale:

```typescript
  function renderPage(initialLocale: 'en' | 'zh' = 'en') {
    flushSync(() => {
      root.render(
        <LocaleProvider initialLocale={initialLocale}>
          <FriendsPage />
        </LocaleProvider>,
      );
    });
  }
```

Update the default `joinFriendByCodeMock` result in `beforeEach`:

```typescript
    joinFriendByCodeMock.mockResolvedValue({
      ok: true,
      data: {
        status: 'already_active',
        friendship_id: 'friendship-existing',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });
```

Rename the load-auth test to `preserves logged-out join handoff before attempting auto-join` and keep these expectations:

```typescript
    expect(replaceMock).toHaveBeenCalledWith('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dcode_1');
    expect(joinFriendByCodeMock).not.toHaveBeenCalled();
```

In `joins by public friend link code once and scrubs the URL`, update the join result:

```typescript
    joinFriendByCodeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'created',
        friendship_id: 'friendship-new',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });
```

Render Chinese locale and assert personalized Chinese copy:

```typescript
    renderPage('zh');
    await flushTicks();

    expect(container.textContent).toContain('已成功添加 Oliver');
```

Add a new test:

```typescript
  it('shows personalized already-active copy after logged-in auto-join', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
    listFriendsMock.mockResolvedValueOnce({ ok: true, data: [friend()] }).mockResolvedValue({
      ok: true,
      data: [friend({ counterpartAccountId: 'acct_oliver', counterpartProfile: { displayName: 'Oliver', avatarUrl: null } })],
    });
    joinFriendByCodeMock.mockResolvedValueOnce({
      ok: true,
      data: {
        status: 'already_active',
        friendship_id: 'friendship-existing',
        counterpart_account_id: 'acct_oliver',
        counterpart_display_name: 'Oliver',
        continuation: {},
      },
    });

    renderPage('zh');
    await flushTicks();

    expect(joinFriendByCodeMock).toHaveBeenCalledWith('code_1');
    expect(container.textContent).toContain('Oliver 已经在你的好友列表中。');
    expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  });
```

Add disabled-link and invalid-link coverage:

```typescript
  it('shows distinct disabled and invalid friend link join errors', async () => {
    searchParamsMock.mockReturnValue(new URLSearchParams('join=disabled_code'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'friend_link_disabled' });

    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('This friend link has been disabled.');

    searchParamsMock.mockReturnValue(new URLSearchParams('join=missing_code'));
    joinFriendByCodeMock.mockResolvedValueOnce({ ok: false, error: 'friend_link_not_found' });
    renderPage();
    await flushTicks();

    expect(container.textContent).toContain('This friend link is invalid or expired.');
  });
```

- [x] **Step 3: Run web tests to verify they fail**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts app/\(customer\)/account/friends/page.test.tsx
```

Expected: FAIL because the page still renders generic copy and the i18n keys do not exist.

- [x] **Step 4: Implement web wrapper, i18n, and page behavior**

In `web/lib/customer-friends.ts`, keep `CustomerFriendshipJoin` in snake case to match the clean API:

```typescript
export type CustomerFriendshipJoin = {
  status: 'created' | 'already_active';
  friendship_id: string | null;
  counterpart_account_id: string;
  counterpart_display_name: string;
  continuation?: Record<string, unknown>;
};
```

In `web/lib/i18n.ts`, replace the friends copy type fields:

```typescript
    inviteCreated: string;
    inviteAlreadyActive: string;
    inviteSelf: string;
    inviteDisabled: string;
    inviteInvalid: string;
```

Remove `inviteSent`, `inviteAlreadyFriend`, `inviteLoadFailure`, and
`inviteUnavailable` if no code uses them after the page update.

Use these English strings:

```typescript
        inviteCreated: 'Added {name}.',
        inviteAlreadyActive: '{name} is already in your friends list.',
        inviteSelf: 'You cannot add yourself as a friend.',
        inviteDisabled: 'This friend link has been disabled.',
        inviteInvalid: 'This friend link is invalid or expired.',
```

Use these Chinese strings:

```typescript
        inviteCreated: '已成功添加 {name}',
        inviteAlreadyActive: '{name} 已经在你的好友列表中。',
        inviteSelf: '不能把自己添加为好友。',
        inviteDisabled: '这条好友链接已被停用。',
        inviteInvalid: '这条好友链接无效或已过期。',
```

In `web/app/(customer)/account/friends/page.tsx`, add helpers near `loginNextPath`:

```typescript
function formatFriendName(template: string, name: string): string {
  return template.replace('{name}', name);
}

function joinErrorMessage(error: string, copy: ReturnType<typeof useLocale>['messages']['customerPages']['friends']): string {
  if (error === 'self_friendship_forbidden') {
    return copy.inviteSelf;
  }
  if (error === 'friend_link_disabled') {
    return copy.inviteDisabled;
  }
  if (error === 'friend_link_not_found') {
    return copy.inviteInvalid;
  }
  return copy.actionFailure;
}
```

If the `useLocale` return type is awkward outside the component, define:

```typescript
type FriendsCopy = ReturnType<typeof useLocale>['messages']['customerPages']['friends'];
```

Update successful join notice:

```typescript
        const template = res.data.status === 'created' ? copy.inviteCreated : copy.inviteAlreadyActive;
        setNotice(formatFriendName(template, res.data.counterpart_display_name));
```

Update failed join error handling:

```typescript
          preserveActionErrorRef.current = true;
          setError(joinErrorMessage(res.error, copy));
          return;
```

Update the `runJoinByCode` dependency list:

```typescript
    [copy, loadData, replace],
```

- [x] **Step 5: Run web tests to verify they pass**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts app/\(customer\)/account/friends/page.test.tsx
```

Expected: PASS for customer-friends wrapper and Friends page tests.

---

### Task 3: Canonical Docs And Focused Verification

**Files:**
- Modify: `docs/product-specs/FEATURE_TREE.md`

- [x] **Step 1: Update product/API surface doc**

In `docs/product-specs/FEATURE_TREE.md`, replace:

```markdown
The public user-link route resolves active reachable friend links for the
public `/u/:code` web landing. Authenticated friendship creation remains
`/api/friends/join`.
```

with:

```markdown
The public user-link route resolves active reachable friend links for the
public `/u/:code` web landing. Authenticated friendship creation remains
`/api/friends/join`; successful join responses include the friendship status,
friendship id, and counterpart account/display identity needed for immediate
user feedback.
```

- [x] **Step 2: Run focused backend verification**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_join_creates_active_friendship_without_joiner_channel \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_active_friendship_is_unique_and_removed_pair_can_reestablish \
  tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_join_route_serializes_created_friendship_result \
  tests/unit/coke/test_social_scheduling_tool_adapter.py::test_establish_friendship_operation_accepts_visible_invite_code \
  -v
```

Expected: PASS.

- [x] **Step 3: Run focused web verification**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts app/\(customer\)/account/friends/page.test.tsx
```

Expected: PASS.

- [x] **Step 4: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: the script prints one or more suggested verification surfaces.

Follow the exact command printed by the routing script. When the output names a
surface verification command, copy that command exactly into the terminal and
run it.

Expected: PASS or a classified environment/test failure recorded in the final report.

- [x] **Step 5: Run web build if feasible**

Run:

```bash
cd web && pnpm build
```

Expected: PASS. If build dependencies or environment constraints fail before compiling this change, capture the exact output and classify the failure.

- [x] **Step 6: Commit implementation and docs**

Run:

```bash
git status --short
git add \
  coke/domains/social_scheduling/models.py \
  coke/domains/social_scheduling/service.py \
  coke/api/friend_routes.py \
  coke/composition.py \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py \
  tests/unit/coke/social_scheduling/test_social_scheduling_routes.py \
  tests/unit/coke/test_social_scheduling_tool_adapter.py \
  web/lib/customer-friends.ts \
  web/lib/customer-friends.test.ts \
  web/lib/i18n.ts \
  'web/app/(customer)/account/friends/page.tsx' \
  'web/app/(customer)/account/friends/page.test.tsx' \
  docs/product-specs/FEATURE_TREE.md
git commit -m $'feat: personalize friend add feedback\n\nCo-Authored-By: Codex <noreply@openai.com>'
```

Expected: one implementation commit.

---

### Task 4: Final Verification And Handoff Evidence

**Files:**
- No source edits unless verification identifies a real product or test bug.

- [x] **Step 1: Run supervisor-requested backend scope**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/coke/social_scheduling/test_social_scheduling_service.py \
  tests/unit/coke/social_scheduling/test_social_scheduling_routes.py \
  tests/unit/coke/test_social_scheduling_tool_adapter.py \
  -v
```

Expected: PASS.

- [x] **Step 2: Run supervisor-requested web scope**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts app/\(customer\)/account/friends/page.test.tsx
```

Expected: PASS.

- [x] **Step 3: Re-run `suggest-verification` after the implementation commit**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Expected: suggested verification surfaces for the implementation commit.

- [x] **Step 4: Run suggested surface command**

Run the exact command from Step 3. If it repeats a command already run, re-run it after the implementation commit so the evidence is fresh.

Expected: PASS or a classified failure with exact output.

- [x] **Step 5: Run web build**

Run:

```bash
cd web && pnpm build
```

Expected: PASS or a classified environment failure with exact output.

- [x] **Step 6: Collect commit list**

Run:

```bash
git log --oneline --decorate -5
```

Expected: includes the spec commit and implementation commit on `fix/eva-rca-web`.

- [x] **Step 7: Final report**

Report the spec path, plan path, commit list from `git log --oneline`, exact
verification commands with the real output observed in this run, deviations from
this plan, and blockers. If there are no deviations or blockers, state `none`
for those sections.
