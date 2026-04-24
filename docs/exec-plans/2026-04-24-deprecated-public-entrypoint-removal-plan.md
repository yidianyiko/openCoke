# Deprecated Public Entrypoint Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove deprecated public entrypoint references from active product verification and operational guidance while keeping explicit `404` regression checks for retired routes.

**Architecture:** Keep the supported Kap public surface anchored on `/`, `/auth/*`, `/channels/*`, `/account/*`, and `/global`. Tighten regression coverage so public web tests fail if retired entrypoints reappear, then narrow deploy verification and docs to talk about specific retired public routes instead of broad legacy namespaces.

**Tech Stack:** TypeScript, React, Next.js, Vitest, Bash, Markdown, pnpm

---

## File Structure

- `gateway/packages/web/components/coke-homepage.test.tsx`
  Public homepage regression coverage. Add explicit negative assertions for retired public routes.
- `gateway/packages/web/components/coke-public-shell.test.tsx`
  Shared public-shell regression coverage. Ensure active auth CTAs stay on supported routes and no retired route links render.
- `scripts/deploy-compose-to-gcp.sh`
  Production deploy verification. Replace stale homepage marker checks with current Kap markers and keep only explicit retired-route `404` probes.
- `scripts/test-deploy-compose-to-gcp.sh`
  Shell-script regression test fixture for the deploy script. Update fake homepage content and assertions to match the revised deploy verification contract.
- `docs/deploy.md`
  Canonical deployment guide. Describe retired public entrypoints explicitly instead of broad “all `/coke/*` / `/api/coke/*` are gone” wording.
- `docs/clawscale_bridge.md`
  Bridge/operator guide. Align route language with the active public contract and the specific retired routes that must stay unavailable.

### Task 1: Add Public-Surface Regression Coverage

**Files:**
- Modify: `gateway/packages/web/components/coke-homepage.test.tsx`
- Modify: `gateway/packages/web/components/coke-public-shell.test.tsx`

- [ ] **Step 1: Write the failing test assertions for retired public routes**

Add these assertions to the English homepage test in `gateway/packages/web/components/coke-homepage.test.tsx` after the existing supported-route checks:

```tsx
    expect(container.querySelector('a[href="/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/coke/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/api/coke/auth/login"]')).toBeFalsy();
```

Add these assertions to the English shell test in `gateway/packages/web/components/coke-public-shell.test.tsx` after the existing auth CTA checks:

```tsx
    expect(container.querySelector('a[href="/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/coke/login"]')).toBeFalsy();
    expect(container.querySelector('a[href="/api/coke/auth/login"]')).toBeFalsy();
```

- [ ] **Step 2: Run the targeted web tests to verify the new assertions fail only if retired routes are still rendered**

Run:

```bash
pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/coke-public-shell.test.tsx
```

Expected: PASS if the current public surface is already clean. If a retired route appears, the new assertions fail and identify the offending surface.

- [ ] **Step 3: Keep the tests and adjust code only if one of the new assertions reveals an unexpected route**

If the tests from Step 2 fail, inspect the rendered component and replace the retired link with the supported route. The only allowed destinations for public auth CTAs are:

```tsx
<Link href="/auth/login">...</Link>
<Link href="/auth/register">...</Link>
```

If Step 2 already passes, do not make extra product-code changes.

- [ ] **Step 4: Re-run the targeted web tests**

Run:

```bash
pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/coke-public-shell.test.tsx
```

Expected: PASS with the new negative assertions in place.

- [ ] **Step 5: Commit Task 1**

```bash
git -C gateway add packages/web/components/coke-homepage.test.tsx packages/web/components/coke-public-shell.test.tsx
git -C gateway commit -m "test(web): guard retired public entrypoints"
git add gateway
git commit -m "test: record retired public entrypoint guards"
```

### Task 2: Narrow Deploy Verification To Current Kap Markers And Explicit Retired Routes

**Files:**
- Modify: `scripts/deploy-compose-to-gcp.sh`
- Modify: `scripts/test-deploy-compose-to-gcp.sh`

- [ ] **Step 1: Update the deploy script test fixture first**

In `scripts/test-deploy-compose-to-gcp.sh`, change the fake homepage body returned by the curl stub from the old Coke marker to current Kap markers:

```bash
cat <<'OUT'
Kap AI
Plan meetings, reminders, and the next move in one thread.
__COKE_LOCALE__
<img src="/kap-koala-hero.png" alt="Kap koala mascot" />
<a href="/channels/wechat-personal">WeChat channel</a>
<a href="/account/subscription">Subscription</a>
OUT
```

Keep the stubbed `404` responses for:

```bash
/login
/coke/login
/api/coke/auth/login
```

- [ ] **Step 2: Adjust the deploy script assertions to the new contract**

In `scripts/deploy-compose-to-gcp.sh`, replace the stale homepage copy check:

```bash
printf '%s' "$homepage" | grep -q 'coke | An AI Partner That Grows With You'
```

with current Kap markers:

```bash
printf '%s' "$homepage" | grep -q 'Kap AI'
printf '%s' "$homepage" | grep -q 'Plan meetings, reminders, and the next move in one thread.'
printf '%s' "$homepage" | grep -q '/kap-koala-hero.png'
```

Keep the explicit retired-route probes:

```bash
old_login_status=$(curl -k -s -o /dev/null -w '%{http_code}' "$public_url/login")
old_web_namespace_status=$(curl -k -s -o /dev/null -w '%{http_code}' "$public_url/coke/login")
old_api_namespace_status=$(curl -k -s -o /dev/null -w '%{http_code}' "$public_url/api/coke/auth/login")
```

Replace the broad homepage grep guards:

```bash
printf '%s' "$homepage" | grep -q '/coke/' && exit 1 || true
printf '%s' "$homepage" | grep -q '/api/coke/' && exit 1 || true
```

with explicit checks only for the retired public entrypoint strings:

```bash
printf '%s' "$homepage" | grep -q 'href="/login"' && exit 1 || true
printf '%s' "$homepage" | grep -q 'href="/coke/login"' && exit 1 || true
printf '%s' "$homepage" | grep -q '/api/coke/auth/login' && exit 1 || true
```

- [ ] **Step 3: Update the deploy-script test expectations**

In `scripts/test-deploy-compose-to-gcp.sh`, keep the call-log assertions for the supported pages and the explicit retired-route probes:

```bash
  assert_contains "$call_log" "/auth/login"
  assert_contains "$call_log" "/auth/register"
  assert_contains "$call_log" "/login"
  assert_contains "$call_log" "/coke/login"
  assert_contains "$call_log" "/api/coke/auth/login"
```

Do not assert broad `/coke/` namespace scanning in the test.

- [ ] **Step 4: Run the deploy-script regression test**

Run:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
```

Expected: PASS, proving the deploy verifier now checks the current Kap homepage and only explicit retired public entrypoints.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/deploy-compose-to-gcp.sh scripts/test-deploy-compose-to-gcp.sh
git commit -m "fix: narrow retired public entrypoint deploy checks"
```

### Task 3: Align Operator Docs With The Supported Public Contract

**Files:**
- Modify: `docs/deploy.md`
- Modify: `docs/clawscale_bridge.md`

- [ ] **Step 1: Update the route-contract wording in `docs/deploy.md`**

Rewrite the route-contract bullets so they describe:

```md
- Web: `/auth/*`、`/channels/wechat-personal`、`/account/subscription`
- Public API: `/api/auth/*`、`/api/customer/channels/wechat-personal/*`、`/api/customer/subscription`、`/api/customer/subscription/checkout`、`/api/public/subscription-checkout`、`/api/webhooks/stripe`
- Internal API: `/api/internal/*`
- Retired public entrypoints: `/login`、`/coke/login`、`/api/coke/auth/login` 应返回 404
```

Update later deployment-check bullets to say the script verifies those specific retired public entrypoints return `404`.

- [ ] **Step 2: Update `docs/clawscale_bridge.md` to match the same boundary**

Replace broad wording like:

```md
legacy `/coke/*` and `/api/coke/*` paths are removed and return 404
```

with explicit retired-entrypoint wording:

```md
retired public entrypoints `/login`, `/coke/login`, and `/api/coke/auth/login` return 404
```

Keep the active customer-facing paths and API routes unchanged.

- [ ] **Step 3: Run a targeted search to confirm active docs and scripts now describe only specific retired public entrypoints**

Run:

```bash
rg -n "legacy `/coke/\\*`|/login|/coke/login|/api/coke/auth/login" docs/deploy.md docs/clawscale_bridge.md scripts/deploy-compose-to-gcp.sh scripts/test-deploy-compose-to-gcp.sh
```

Expected:
- `docs/deploy.md` and `docs/clawscale_bridge.md` mention only the explicit retired public entrypoints
- deploy scripts retain explicit `404` checks for those same routes

- [ ] **Step 4: Re-run the web regression tests plus deploy-script test**

Run:

```bash
pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/coke-public-shell.test.tsx
bash scripts/test-deploy-compose-to-gcp.sh
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add docs/deploy.md docs/clawscale_bridge.md
git commit -m "docs: clarify retired public entrypoints"
```

### Task 4: Final Verification And Integration

**Files:**
- Verify only

- [ ] **Step 1: Run the complete web verification suite**

Run:

```bash
pnpm --dir gateway/packages/web test
pnpm --dir gateway/packages/web build
```

Expected:
- `36` test files pass
- build exits `0`

- [ ] **Step 2: Run the deploy-script regression test again**

Run:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
```

Expected: PASS.

- [ ] **Step 3: Inspect the final diff**

Run:

```bash
git status --short
git diff -- docs/deploy.md docs/clawscale_bridge.md scripts/deploy-compose-to-gcp.sh scripts/test-deploy-compose-to-gcp.sh
git -C gateway status --short
git -C gateway diff -- packages/web/components/coke-homepage.test.tsx packages/web/components/coke-public-shell.test.tsx
```

Expected: only the planned files are changed.

- [ ] **Step 4: Commit the final integration state**

If Task 1 used nested gateway commits, update the root repo pointer and create the final root commit:

```bash
git add gateway docs/deploy.md docs/clawscale_bridge.md scripts/deploy-compose-to-gcp.sh scripts/test-deploy-compose-to-gcp.sh
git commit -m "feat: remove retired public entrypoint remnants"
```

- [ ] **Step 5: Record verification evidence in the task file**

Append the final command results to:

```md
tasks/2026-04-24-deprecated-public-entrypoint-removal.md
```

using bullets like:

```md
- Verified `pnpm --dir gateway/packages/web test` on 2026-04-24
- Verified `pnpm --dir gateway/packages/web build` on 2026-04-24
- Verified `bash scripts/test-deploy-compose-to-gcp.sh` on 2026-04-24
```
