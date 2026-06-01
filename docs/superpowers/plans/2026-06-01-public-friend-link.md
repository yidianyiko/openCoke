# Public Friend Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make copied friend links resolve to the real public `/u/{link_code}` route, expose the missing clean-backend public resolver, and let authenticated channel-connected users join by link code.

**Architecture:** The backend keeps SocialScheduling as the owner of friend-link and friendship rules. Flask routes stay thin: unauthenticated public route resolves active reachable links, authenticated friend routes keep direct join semantics. The Next.js app becomes a thin client over the clean Python API and removes retired gateway link-session behavior.

**Tech Stack:** Python 3.12, Flask, pytest, Next.js 16, React 19, TypeScript, Vitest.

---

## Reference Spec

- `docs/superpowers/specs/2026-06-01-public-friend-link-design.md`
- `docs/product-requirements/current.md` friendship journey
- `docs/ARCHITECTURE.md` SocialScheduling bounded context
- `docs/design-docs/coke-working-contract.md` direct friendship rule

## File Structure

- Modify `coke/config.py`: add `Settings.public_base_url` and production validation.
- Modify `coke/composition.py`: thread `public_base_url` into every `SocialSchedulingService` constructor.
- Modify `coke/domains/social_scheduling/models.py`: add `PublicFriendLinkView`.
- Modify `coke/domains/social_scheduling/service.py`: store the public base URL, build `/u/{link_code}` payloads, and resolve public friend links.
- Create `coke/api/public_friend_routes.py`: unauthenticated public resolver blueprint.
- Modify `coke/app.py`: register public resolver outside the customer-auth route block.
- Modify backend tests under `tests/unit/coke/`.
- Modify `web/lib/user-link-api.ts`, `web/lib/api-types.ts`, and tests: public link fetch only, raw body handling.
- Modify `web/app/u/[code]/page.tsx` and test: remove link sessions, link auth CTAs to `?join=`.
- Modify `web/lib/customer-friends.ts`, `web/lib/i18n.ts`, `web/app/(customer)/account/friends/page.tsx`, and tests: clean error normalization, join-by-code, channel-less link resilience.
- Modify `scripts/deploy-compose-to-gcp.sh`, `docs/deploy.md`, `docs/product-specs/FEATURE_TREE.md`.
- Create `docs/issues/2026-06-01-friend-link-prefix.md`.

---

### Task 1: Backend Public Base URL And Link Payload

**Files:**
- Modify: `coke/config.py`
- Modify: `coke/composition.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Modify: `tests/unit/coke/test_backend_foundation.py`
- Modify: `tests/unit/coke/settings/test_settings_composition.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `tests/unit/coke/test_social_scheduling_tool_adapter.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`

- [ ] **Step 1: Add failing config tests**

Append these tests near the other `Settings.from_env` tests in `tests/unit/coke/test_backend_foundation.py`:

```python
def test_settings_from_env_reads_public_base_url_and_strips_trailing_slash(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("COKE_PUBLIC_BASE_URL", "https://coke.example.com///")

    settings = Settings.from_env()

    assert settings.public_base_url == "https://coke.example.com"


def test_settings_from_env_defaults_public_base_url_for_non_production(monkeypatch):
    from coke.config import Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("COKE_PUBLIC_BASE_URL", raising=False)

    settings = Settings.from_env()

    assert settings.public_base_url == "http://localhost:4040"


def test_settings_from_env_requires_public_base_url_for_production(monkeypatch):
    from coke.config import ConfigurationError, Settings

    monkeypatch.setenv("DATABASE_URL", POSTGRES_URL)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COKE_LLM_FAKE", "1")
    monkeypatch.delenv("COKE_PUBLIC_BASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="COKE_PUBLIC_BASE_URL"):
        Settings.from_env()
```

- [ ] **Step 2: Run config tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py::test_settings_from_env_reads_public_base_url_and_strips_trailing_slash tests/unit/coke/test_backend_foundation.py::test_settings_from_env_defaults_public_base_url_for_non_production tests/unit/coke/test_backend_foundation.py::test_settings_from_env_requires_public_base_url_for_production -v
```

Expected: FAIL because `Settings` has no `public_base_url`.

- [ ] **Step 3: Implement config**

In `coke/config.py`, add the field near the runtime URL settings:

```python
    public_base_url: str = "http://localhost:4040"
```

In `Settings.from_env`, after `app_env` is computed:

```python
        public_base_url = _optional(source, "COKE_PUBLIC_BASE_URL")
        if app_env == "production" and public_base_url is None:
            raise ConfigurationError(
                "COKE_PUBLIC_BASE_URL is required for production public links"
            )
```

In the returned `cls(...)`, include:

```python
            public_base_url=(public_base_url or "http://localhost:4040").rstrip("/"),
```

- [ ] **Step 4: Add failing composition and link payload tests**

Append this test to `tests/unit/coke/settings/test_settings_composition.py`:

```python
def test_composition_threads_public_base_url_to_social_scheduling():
    runtime = compose_coke_runtime(
        semantic_interpreter=FakeSemanticInterpreter(),
        interaction_agent=FakeInteractionAgent(),
        redis_client=object(),
        outbound_delivery=FakeOutboundDelivery(),
        now=lambda: NOW,
        id_factory=_id_factory(),
        public_base_url="https://web.example.com/",
    )

    assert runtime.social_scheduling_service._public_base_url == "https://web.example.com"
```

Append this test near the friend-link tests in `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`:

```python
def test_friend_link_payload_uses_public_base_url_and_link_code():
    service, _repo, _reachability, _availability = make_service({"owner"})
    service._public_base_url = "https://web.example.com"

    link = service.get_or_create_friend_link("owner")

    assert link.public_token == "friend_link_token_1"
    assert link.link_code == "friend_code_token_2"
    assert link.qr_payload == "https://web.example.com/u/friend_code_token_2"
```

- [ ] **Step 5: Run composition and service tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/settings/test_settings_composition.py::test_composition_threads_public_base_url_to_social_scheduling tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_friend_link_payload_uses_public_base_url_and_link_code -v
```

Expected: FAIL because `compose_coke_runtime` has no `public_base_url` parameter and `_link_view` still returns `https://coke.example/friends/{token}`.

- [ ] **Step 6: Implement composition and link payload**

In `coke/composition.py`, add the parameter to `compose_coke_runtime(...)`:

```python
    public_base_url: str = "http://localhost:4040",
```

Pass it into `SocialSchedulingService(...)`:

```python
        public_base_url=public_base_url,
```

In `build_runtime_from_settings`, pass `settings.public_base_url` into both `compose_coke_runtime(...)` calls: the child runtime inside `interactive_runtime_factory()` and the main runtime.

In `coke/domains/social_scheduling/service.py`, add `public_base_url` to `__init__`:

```python
        public_base_url: str = "http://localhost:4040",
```

Store it after the factories:

```python
        self._public_base_url = public_base_url.rstrip("/") or "http://localhost:4040"
```

Change `_link_view` to build from `code`:

```python
            qr_payload=f"{self._public_base_url}/u/{code}" if code else None,
```

- [ ] **Step 7: Update old friend-link fixtures**

In `tests/unit/coke/test_social_scheduling_tool_adapter.py`, update expected URLs from `https://coke.example/friends/<token>` to `http://localhost:4040/u/<link_code>`. Update `_friend_link_view(...)` so its default `qr_payload` uses the code:

```python
    if qr_payload is None and code is not None:
        qr_payload = f"http://localhost:4040/u/{code}"
```

In `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`, update the fake link payload:

```python
            qr_payload="http://localhost:4040/u/link_code",
```

- [ ] **Step 8: Run Task 1 tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

Run:

```bash
git add coke/config.py coke/composition.py coke/domains/social_scheduling/service.py tests/unit/coke/test_backend_foundation.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/test_social_scheduling_tool_adapter.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py
git commit -m "fix: build public friend links from configured web host"
```

---

### Task 2: Public Friend-Link Resolver Route

**Files:**
- Modify: `coke/domains/social_scheduling/models.py`
- Modify: `coke/domains/social_scheduling/service.py`
- Create: `coke/api/public_friend_routes.py`
- Modify: `coke/app.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`
- Modify: `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`

- [ ] **Step 1: Add failing service resolver tests**

Append these tests near the friend-link tests in `tests/unit/coke/social_scheduling/test_social_scheduling_service.py`:

```python
def test_resolve_public_friend_link_returns_active_reachable_owner_display_name():
    service, _repo, _reachability, _availability = make_service({"owner"})
    service.display_name_resolver = lambda account_id: {"owner": "Mina Owner"}[account_id]
    link = service.get_or_create_friend_link("owner")

    resolved = service.resolve_public_friend_link(link.link_code)

    assert resolved is not None
    assert resolved.link_code == link.link_code
    assert resolved.status == "active"
    assert resolved.owner_display_name == "Mina Owner"


def test_resolve_public_friend_link_returns_none_for_missing_disabled_or_unreachable():
    service, _repo, reachability, _availability = make_service({"owner"})
    link = service.get_or_create_friend_link("owner")

    assert service.resolve_public_friend_link("missing-code") is None

    service.disable_friend_link("owner")
    assert service.resolve_public_friend_link(link.link_code) is None

    reset = service.reset_friend_link("owner")
    reachability.reachable.clear()
    assert service.resolve_public_friend_link(reset.link_code) is None
```

- [ ] **Step 2: Run resolver tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_resolve_public_friend_link_returns_active_reachable_owner_display_name tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_resolve_public_friend_link_returns_none_for_missing_disabled_or_unreachable -v
```

Expected: FAIL because `resolve_public_friend_link` and `PublicFriendLinkView` do not exist.

- [ ] **Step 3: Implement resolver model and service**

In `coke/domains/social_scheduling/models.py`, add:

```python
@dataclass(frozen=True, slots=True)
class PublicFriendLinkView:
    link_code: str
    status: Literal["active"]
    owner_display_name: str
```

Import `PublicFriendLinkView` in `coke/domains/social_scheduling/service.py` and add:

```python
    def resolve_public_friend_link(
        self, link_code: str
    ) -> PublicFriendLinkView | None:
        link = self.repository.get_friend_link_by_code_hash(_hash_token(link_code))
        if link is None or link.lifecycle != "active":
            return None
        if not self.reachability.has_usable_channel(link.owner_account_id):
            return None
        return PublicFriendLinkView(
            link_code=link_code,
            status="active",
            owner_display_name=self.display_name_resolver(link.owner_account_id),
        )
```

- [ ] **Step 4: Add failing public route tests**

In `tests/unit/coke/social_scheduling/test_social_scheduling_routes.py`, import `FriendLinkLifecycle` is not needed; use `SimpleNamespace`. Add this method to `FakeSocialSchedulingService`:

```python
    def resolve_public_friend_link(self, link_code):
        self.calls.append(("resolve_public_friend_link", {"link_code": link_code}))
        if link_code == "missing":
            return None
        return SimpleNamespace(
            link_code=link_code,
            status="active",
            owner_display_name="Alice Push",
        )
```

Append these route tests:

```python
def test_public_friend_link_route_is_registered_without_identity_service():
    service = FakeSocialSchedulingService()
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        social_scheduling_service=service,
    )

    response = app.test_client().get("/api/public/user-links/code_1")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": "code_1",
        "status": "active",
        "profile": {
            "displayName": "Alice Push",
            "tagline": None,
            "avatarUrl": None,
        },
    }
    assert service.calls == [("resolve_public_friend_link", {"link_code": "code_1"})]


def test_public_friend_link_route_returns_404_for_missing_or_inactive_link():
    service = FakeSocialSchedulingService()
    app = create_app(
        Settings(database_url=DATABASE_URL, redis_url=REDIS_URL),
        social_scheduling_service=service,
    )

    response = app.test_client().get("/api/public/user-links/missing")

    assert response.status_code == 404
    assert response.get_json() == {"error": {"code": "friend_link_not_active"}}
```

- [ ] **Step 5: Run route tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_public_friend_link_route_is_registered_without_identity_service tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_public_friend_link_route_returns_404_for_missing_or_inactive_link -v
```

Expected: FAIL with 404 because the route is not registered.

- [ ] **Step 6: Implement public route and registration**

Create `coke/api/public_friend_routes.py`:

```python
from __future__ import annotations

from flask import Blueprint, jsonify


def create_public_friend_blueprint(social_scheduling_service) -> Blueprint:
    blueprint = Blueprint(
        "public_friend_links",
        __name__,
        url_prefix="/api/public/user-links",
    )

    @blueprint.get("/<code>")
    def get_public_friend_link(code: str):
        view = social_scheduling_service.resolve_public_friend_link(code)
        if view is None:
            return jsonify({"error": {"code": "friend_link_not_active"}}), 404
        return jsonify(
            {
                "code": view.link_code,
                "status": view.status,
                "profile": {
                    "displayName": view.owner_display_name,
                    "tagline": None,
                    "avatarUrl": None,
                },
            }
        )

    return blueprint
```

In `coke/app.py`, register this before the authenticated social block:

```python
    if social_scheduling_service is not None:
        from coke.api.public_friend_routes import create_public_friend_blueprint

        app.register_blueprint(
            create_public_friend_blueprint(social_scheduling_service)
        )
```

Keep the existing authenticated friend/shared route block gated by both `social_scheduling_service` and `identity_access_service`.

- [ ] **Step 7: Run Task 2 tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_resolve_public_friend_link_returns_active_reachable_owner_display_name tests/unit/coke/social_scheduling/test_social_scheduling_service.py::test_resolve_public_friend_link_returns_none_for_missing_disabled_or_unreachable tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_public_friend_link_route_is_registered_without_identity_service tests/unit/coke/social_scheduling/test_social_scheduling_routes.py::test_public_friend_link_route_returns_404_for_missing_or_inactive_link -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add coke/domains/social_scheduling/models.py coke/domains/social_scheduling/service.py coke/api/public_friend_routes.py coke/app.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py
git commit -m "feat: resolve public friend links in clean backend"
```

---

### Task 3: Public Web Link Landing Without Link Sessions

**Files:**
- Modify: `web/lib/user-link-api.ts`
- Modify: `web/lib/api-types.ts`
- Modify: `web/lib/user-link-api.test.ts`
- Modify: `web/app/u/[code]/page.tsx`
- Modify: `web/app/u/[code]/page.test.tsx`

- [ ] **Step 1: Rewrite failing `fetchUserLink` tests for raw bodies**

Replace `web/lib/user-link-api.test.ts` with focused tests for `fetchUserLink` only:

```typescript
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchUserLink } from './user-link-api';

const originalApiBaseUrl = process.env['NEXT_PUBLIC_API_BASE_URL'];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();

  if (originalApiBaseUrl == null) {
    delete process.env['NEXT_PUBLIC_API_BASE_URL'];
  } else {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = originalApiBaseUrl;
  }
});

describe('user-link api helpers', () => {
  it('fetches a public user link from the clean raw response body', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com/';
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      }),
    }));
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

    await expect(fetchUserLink('a/b')).resolves.toEqual({
      ok: true,
      data: {
        code: 'abc',
        status: 'active',
        profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
      },
    });
    expect(fetchMock).toHaveBeenCalledWith('https://api.example.com/api/public/user-links/a%2Fb', {
      cache: 'no-store',
    });
  });

  it('maps non-200 public link responses to link_not_active', async () => {
    process.env['NEXT_PUBLIC_API_BASE_URL'] = 'https://api.example.com';
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })) as unknown as typeof fetch);

    await expect(fetchUserLink('missing')).resolves.toEqual({
      ok: false,
      error: 'link_not_active',
    });
  });
});
```

- [ ] **Step 2: Run user-link tests and verify RED**

Run:

```bash
cd web && pnpm test lib/user-link-api.test.ts
```

Expected: FAIL because `fetchUserLink` still expects `{ok,data}` and exports retired functions referenced by old tests.

- [ ] **Step 3: Implement public user-link API cleanup**

In `web/lib/api-types.ts`, keep only:

```typescript
export type PublicUserLinkResponse = {
  code: string;
  status: 'active';
  profile: {
    displayName: string;
    tagline: string | null;
    avatarUrl: string | null;
  };
};
```

Delete `PublicLinkSessionResponse`, `PublicLinkSessionStatusResponse`, and `DirectFriendshipResponse`.

Replace `web/lib/user-link-api.ts` with:

```typescript
import type { ApiResponse, PublicUserLinkResponse } from './api-types';
import { getCustomerApiBase } from './customer-api';

export async function fetchUserLink(code: string): Promise<ApiResponse<PublicUserLinkResponse>> {
  const base = getCustomerApiBase();
  const encodedCode = encodeURIComponent(code);
  const metaRes = await fetch(`${base}/api/public/user-links/${encodedCode}`, { cache: 'no-store' });
  if (!metaRes.ok) {
    return { ok: false, error: 'link_not_active' };
  }

  return {
    ok: true,
    data: (await metaRes.json()) as PublicUserLinkResponse,
  };
}
```

- [ ] **Step 4: Rewrite failing landing-page tests**

In `web/app/u/[code]/page.test.tsx`, remove `openLinkSession` mocks and replace expectations with join-code links:

```typescript
vi.mock('../../../lib/user-link-api', () => ({
  fetchUserLink: mockFetchUserLink,
}));
```

Update the first test to assert:

```typescript
expect(loginLink?.getAttribute('href')).toBe('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dabc');
expect(registerLink?.getAttribute('href')).toBe('/auth/register?next=%2Faccount%2Ffriends%3Fjoin%3Dabc');
```

Delete the retry-state and preserved `link_session` redirect tests. Add this test:

```typescript
it('renders auth actions carrying the encoded join code', async () => {
  mockFetchUserLink.mockResolvedValue({
    ok: true,
    data: {
      code: 'abc/123',
      status: 'active',
      profile: { displayName: 'Coach A', tagline: null, avatarUrl: null },
    },
  });

  const html = renderToString(
    await UserLinkPage({ params: Promise.resolve({ code: 'abc/123' }), searchParams: Promise.resolve({}) }),
  );
  const container = renderHtml(html);
  const links = Array.from(container.querySelectorAll('a')).map((link) => link.getAttribute('href'));

  expect(links).toContain('/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dabc%252F123');
  expect(links).toContain('/auth/register?next=%2Faccount%2Ffriends%3Fjoin%3Dabc%252F123');
}
```

- [ ] **Step 5: Run landing tests and verify RED**

Run:

```bash
cd web && pnpm test 'app/u/[code]/page.test.tsx'
```

Expected: FAIL because the page imports and calls `openLinkSession`.

- [ ] **Step 6: Implement landing page**

In `web/app/u/[code]/page.tsx`:

- Delete `redirect`, `firstSearchParam`, `openLinkSession`, `dashboardAuthHref(path, token)`, and all `link_session` handling.
- Add:

```typescript
function dashboardAuthHref(path: '/auth/login' | '/auth/register', code: string): string {
  const next = `/account/friends?join=${encodeURIComponent(code)}`;
  return `${path}?next=${encodeURIComponent(next)}`;
}
```

- Render auth links unconditionally after the QR when the public link is active:

```tsx
<div className="public-user-link__actions">
  <Link href={dashboardAuthHref('/auth/login', code)}>Log in to add friend</Link>
  <Link href={dashboardAuthHref('/auth/register', code)}>Create account to add friend</Link>
</div>
```

- [ ] **Step 7: Run Task 3 tests and verify GREEN**

Run:

```bash
cd web && pnpm test lib/user-link-api.test.ts 'app/u/[code]/page.test.tsx'
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add web/lib/user-link-api.ts web/lib/api-types.ts web/lib/user-link-api.test.ts 'web/app/u/[code]/page.tsx' 'web/app/u/[code]/page.test.tsx'
git commit -m "fix: open public friend links without link sessions"
```

---

### Task 4: Customer Friends Join-By-Code And Channel-Less Resilience

**Files:**
- Modify: `web/lib/customer-friends.ts`
- Modify: `web/lib/customer-friends.test.ts`
- Modify: `web/lib/i18n.ts`
- Modify: `web/app/(customer)/account/friends/page.tsx`
- Modify: `web/app/(customer)/account/friends/page.test.tsx`

- [ ] **Step 1: Add failing customer-friends wrapper tests**

In `web/lib/customer-friends.test.ts`, import `joinFriendByCode`. Add these tests:

```typescript
it('maps clean route error bodies instead of treating them as successful friend-link data', async () => {
  apiMock.get.mockResolvedValueOnce({ error: { code: 'owner_channel_required' } });

  await expect(getCustomerFriendLink()).resolves.toEqual({
    ok: false,
    error: 'owner_channel_required',
  });
});

it('joins a friend by clean link code and preserves deferred status', async () => {
  apiMock.post.mockResolvedValueOnce({
    status: 'deferred_channel_required',
    friendship_id: null,
    continuation: { friend_link_id: 'fl_1' },
  });

  await expect(joinFriendByCode('code/1')).resolves.toEqual({
    ok: true,
    data: {
      status: 'deferred_channel_required',
      friendship_id: null,
      continuation: { friend_link_id: 'fl_1' },
    },
  });
  expect(apiMock.post).toHaveBeenCalledWith('/api/friends/join', { link_code: 'code/1' });
});

it('maps clean join error bodies to ApiResponse errors', async () => {
  apiMock.post.mockResolvedValueOnce({ error: { code: 'self_friendship_forbidden' } });

  await expect(joinFriendByCode('code_1')).resolves.toEqual({
    ok: false,
    error: 'self_friendship_forbidden',
  });
});
```

Also update the existing current-link test to assert the corrected URL:

```typescript
const result = await getCustomerFriendLink();
expect(result).toEqual({
  ok: true,
  data: {
    code: 'code_1',
    status: 'active',
    url: 'https://example.test/u/code_1',
    qrUrl: 'https://example.test/u/code_1',
    profile: { displayName: 'acct_1', tagline: null, avatarUrl: null },
  },
});
```

- [ ] **Step 2: Run customer-friends wrapper tests and verify RED**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts
```

Expected: FAIL because `joinFriendByCode` and error normalization do not exist.

- [ ] **Step 3: Implement customer-friends wrappers**

In `web/lib/customer-friends.ts`, add types:

```typescript
type CleanRouteError = {
  error: {
    code: string;
  };
};

type CleanFriendshipJoin = {
  status: 'created' | 'already_active' | 'deferred_channel_required';
  friendship_id: string | null;
  continuation?: Record<string, unknown>;
};
```

Add helpers:

```typescript
function isCleanRouteError(value: unknown): value is CleanRouteError {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as CleanRouteError).error?.code === 'string'
  );
}

function okOrError<T, U>(value: T | CleanRouteError, map: (value: T) => U): ApiResponse<U> {
  if (isCleanRouteError(value)) {
    return { ok: false, error: value.error.code };
  }
  return { ok: true, data: map(value) };
}
```

Update wrappers to use `okOrError`, for example:

```typescript
export function getCustomerFriendLink(): Promise<ApiResponse<CustomerFriendLink>> {
  return customerApi
    .get<CleanFriendLink | CleanRouteError>('/api/friends/link')
    .then((link) => okOrError(link, cleanFriendLink));
}
```

Add:

```typescript
export function joinFriendByCode(code: string): Promise<ApiResponse<CleanFriendshipJoin>> {
  return customerApi
    .post<CleanFriendshipJoin | CleanRouteError>('/api/friends/join', { link_code: code })
    .then((result) => okOrError(result, (join) => join));
}
```

Update `CleanFriendList` to include the backend display name and map it:

```typescript
type CleanFriendList = {
  friends: {
    account_id: string;
    friendship_id: string;
    display_name?: string;
  }[];
};
```

In `listCustomerFriends`, set:

```typescript
counterpartProfile: {
  displayName: friend.display_name || friend.account_id,
  avatarUrl: null,
},
```

- [ ] **Step 4: Add i18n copy fields**

In the `friends` type in `web/lib/i18n.ts`, add:

```typescript
    linkRequiresChannel: string;
    inviteNeedsChannel: string;
    inviteSelf: string;
```

In English copy:

```typescript
        linkRequiresChannel: 'Connect a messaging channel to get your shareable friend link.',
        inviteNeedsChannel: 'Connect a messaging channel first, then open this friend link again.',
        inviteSelf: 'You cannot add yourself as a friend.',
```

In Chinese copy:

```typescript
        linkRequiresChannel: '先连接一个消息通道，之后才能获得可分享的好友链接。',
        inviteNeedsChannel: '请先连接消息通道，然后再打开这条好友链接。',
        inviteSelf: '不能把自己添加为好友。',
```

- [ ] **Step 5: Rewrite failing friends page tests**

In `web/app/(customer)/account/friends/page.test.tsx`:

- Remove `getLinkSessionStatusMock`, `createFriendshipMock`, `PublicLinkSessionStatusResponse`, and the `../../../../lib/user-link-api` mock.
- Add `joinFriendByCodeMock` to the customer-friends mock.
- Replace `link_session=session-token` cases with `join=code_1`.
- Assert `joinFriendByCodeMock` is called with `code_1`.
- Assert redirect auth failures use `/auth/login?next=%2Faccount%2Ffriends%3Fjoin%3Dcode_1`.

Add these tests:

```typescript
it('joins by public friend link code once and scrubs the URL', async () => {
  searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
  listFriendsMock.mockResolvedValueOnce({ ok: true, data: [] }).mockResolvedValue({
    ok: true,
    data: [friend({ id: 'friendship-new', counterpartAccountId: 'acct_target' })],
  });
  joinFriendByCodeMock.mockResolvedValueOnce({
    ok: true,
    data: { status: 'created', friendship_id: 'friendship-new', continuation: {} },
  });

  renderPage();
  await flushTicks();

  expect(joinFriendByCodeMock).toHaveBeenCalledWith('code_1');
  expect(replaceMock).toHaveBeenCalledWith('/account/friends');
  expect(container.textContent).toContain('Friend added.');
  expect(listFriendsMock).toHaveBeenCalledTimes(2);
});

it('shows a channel-required notice when the clean join is deferred', async () => {
  searchParamsMock.mockReturnValue(new URLSearchParams('join=code_1'));
  joinFriendByCodeMock.mockResolvedValueOnce({
    ok: true,
    data: {
      status: 'deferred_channel_required',
      friendship_id: null,
      continuation: { friend_link_id: 'fl_1' },
    },
  });

  renderPage();
  await flushTicks();

  expect(container.textContent).toContain('Connect a messaging channel first');
  expect(replaceMock).toHaveBeenCalledWith('/account/friends');
});

it('keeps friends visible when the current account has no shareable link yet', async () => {
  getLinkMock.mockResolvedValueOnce({ ok: false, error: 'owner_channel_required' });

  renderPage();
  await flushTicks();

  expect(container.textContent).toContain('Connect a messaging channel to get your shareable friend link.');
  expect(container.textContent).toContain('Rin');
  expect(container.textContent).not.toContain('Unable to load friend data right now.');
});
```

- [ ] **Step 6: Run friends page tests and verify RED**

Run:

```bash
cd web && pnpm test 'app/(customer)/account/friends/page.test.tsx'
```

Expected: FAIL because the page still uses link sessions.

- [ ] **Step 7: Implement friends page join-by-code**

In `web/app/(customer)/account/friends/page.tsx`:

- Import `joinFriendByCode` from `customer-friends`.
- Delete imports from `user-link-api` and `PublicLinkSessionStatusResponse`.
- Rename `inviteToken` to `joinCode`:

```typescript
const joinCode = searchParams.get('join')?.trim() ?? '';
```

- Update `loginNextPath`:

```typescript
function loginNextPath(joinCode: string): string {
  if (!joinCode) {
    return LOGIN_NEXT_PATH;
  }
  const next = `/account/friends?join=${encodeURIComponent(joinCode)}`;
  return `/auth/login?next=${encodeURIComponent(next)}`;
}
```

- Add state:

```typescript
const [linkRequiresChannel, setLinkRequiresChannel] = useState(false);
const joinAttemptedRef = useRef<string | null>(null);
```

- In `loadData`, fetch only `getCustomerFriendLink()` and `listCustomerFriends()`. If `linkRes.error === 'owner_channel_required'`, set `friendLink` to `null`, set `linkRequiresChannel` to `true`, and keep going. For other non-auth link errors, set `copy.loadFailure`.
- Add an effect that runs after load:

```typescript
useEffect(() => {
  if (loading || !joinCode || joinAttemptedRef.current === joinCode) {
    return;
  }
  joinAttemptedRef.current = joinCode;
  void runJoinByCode(joinCode);
}, [joinCode, loading, runJoinByCode]);
```

- Implement `runJoinByCode` with `useCallback`:

```typescript
const runJoinByCode = useCallback(
  async (code: string) => {
    setActionPending(true);
    setError('');
    setNotice('');
    try {
      const res = await joinFriendByCode(code);
      if (!res.ok) {
        if (AUTH_ERRORS.has(res.error)) {
          replace(loginNextPath(code));
          return;
        }
        setError(res.error === 'self_friendship_forbidden' ? copy.inviteSelf : copy.actionFailure);
        return;
      }
      if (res.data.status === 'deferred_channel_required') {
        setNotice(copy.inviteNeedsChannel);
      } else {
        setNotice(copy.inviteSent);
        await loadData();
      }
    } catch {
      setError(copy.actionFailure);
    } finally {
      setActionPending(false);
      replace('/account/friends');
    }
  },
  [copy.actionFailure, copy.inviteNeedsChannel, copy.inviteSelf, copy.inviteSent, loadData, replace],
);
```

- Delete the invite confirmation panel that depended on `linkSession`; the join runs automatically after auth.
- In the friend link section, render `copy.linkRequiresChannel` when `linkRequiresChannel` is true and no `friendLink` exists.

- [ ] **Step 8: Run Task 4 tests and verify GREEN**

Run:

```bash
cd web && pnpm test lib/customer-friends.test.ts 'app/(customer)/account/friends/page.test.tsx' lib/i18n.test.ts
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

Run:

```bash
git add web/lib/customer-friends.ts web/lib/customer-friends.test.ts web/lib/i18n.ts 'web/app/(customer)/account/friends/page.tsx' 'web/app/(customer)/account/friends/page.test.tsx'
git commit -m "fix: join public friend links by clean code"
```

---

### Task 5: Deployment And Repository Docs

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `docs/deploy.md`
- Modify: `docs/product-specs/FEATURE_TREE.md`
- Create: `docs/issues/2026-06-01-friend-link-prefix.md`

- [ ] **Step 1: Add deploy env**

In `scripts/deploy-compose-to-gcp.sh`, add this line to the generated clean `.env` next to the Next public URLs:

```bash
COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com
```

- [ ] **Step 2: Document deployment env**

In `docs/deploy.md`, add `COKE_PUBLIC_BASE_URL=https://coke.keep4oforever.com` to the clean production environment section. State that production backend startup fails without this variable because friend links must not fall back to localhost.

- [ ] **Step 3: Update feature tree**

In `docs/product-specs/FEATURE_TREE.md`, under `## Python Public API`, add:

```markdown
- `/api/public/user-links/:code`
```

Under the SocialScheduling product module bullet or nearby route notes, state that the public user-link route resolves active reachable friend links and that authenticated friendship creation remains under `/api/friends/join`.

- [ ] **Step 4: Create issue record**

Create `docs/issues/2026-06-01-friend-link-prefix.md`:

```markdown
---
title: Public friend links copied with placeholder host and retired route
date: 2026-06-01
status: active
kind: incident
surface: social-scheduling
---

# Public friend links copied with placeholder host and retired route

## What Happened

Copied friend links used `https://coke.example/friends/{public_token}`. That host was a test placeholder, the path did not exist in the web app, and the identifier was the private `public_token` instead of the public landing `link_code`.

## Why It Mattered

The current product requirement says friend links must be openable. The broken string prevented strangers from opening the public profile landing page and starting the authenticated friendship flow.

## Affected Surfaces

- `SocialSchedulingService._link_view`
- `/api/friends/link`
- `/u/[code]`
- `/api/public/user-links/{code}`
- `/account/friends?join={code}`
- production deploy env

## Resolution

Planned resolution: build backend friend links from `COKE_PUBLIC_BASE_URL` and `/u/{link_code}`, expose an unauthenticated public resolver for active reachable friend links, and move the web flow from retired gateway link sessions to `/account/friends?join={code}` direct clean-backend joining.

## Verification

Verification is pending implementation. Task 6 will update this record to `status: resolved` with exact command evidence.
```

- [ ] **Step 5: Run docs/check verification**

Run:

```bash
zsh scripts/check
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add scripts/deploy-compose-to-gcp.sh docs/deploy.md docs/product-specs/FEATURE_TREE.md docs/issues/2026-06-01-friend-link-prefix.md
git commit -m "docs: record public friend link runtime contract"
```

---

### Task 6: Final Verification And Evidence Update

**Files:**
- Modify: `docs/issues/2026-06-01-friend-link-prefix.md`

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_backend_foundation.py tests/unit/coke/settings/test_settings_composition.py tests/unit/coke/social_scheduling/test_social_scheduling_service.py tests/unit/coke/social_scheduling/test_social_scheduling_routes.py tests/unit/coke/test_social_scheduling_tool_adapter.py -v
```

Expected: PASS.

- [ ] **Step 2: Run web targeted tests**

Run:

```bash
cd web && pnpm test lib/user-link-api.test.ts lib/customer-friends.test.ts 'app/u/[code]/page.test.tsx' 'app/(customer)/account/friends/page.test.tsx' lib/i18n.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run diff-aware verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: both commands complete and produce a non-blocking risk report.

- [ ] **Step 4: Run touched surface verification**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-backend
zsh scripts/verify-surface clean-rebuild-web
zsh scripts/verify-surface deploy
zsh scripts/verify-surface repo-os-docs
```

Expected: commands complete successfully. If a surface has no configured commands, `verify-surface` reports that without failing.

- [ ] **Step 5: Run baseline hygiene**

Run:

```bash
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Update issue verification**

In `docs/issues/2026-06-01-friend-link-prefix.md`, set `status: resolved` and replace the pending verification sentence with the exact commands run and pass/fail results.

- [ ] **Step 7: Commit final evidence if the issue record changed**

Run:

```bash
git add docs/issues/2026-06-01-friend-link-prefix.md
git commit -m "docs: add public friend link verification evidence"
```

If the issue record already contains final evidence from Task 5 and this commit has nothing to add, skip this commit.
