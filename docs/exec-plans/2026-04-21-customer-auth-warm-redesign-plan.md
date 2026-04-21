# Customer Auth Warm Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the six customer auth pages onto the warm public-site design system without changing any auth logic, API behavior, routing, storage, or validation behavior.

**Architecture:** Keep all behavior exactly where it is today, but swap the auth layout from `CustomerShell` to a new auth-only shell that composes `CokePublicShell`. Reuse `.coke-site` and `public-site.css` for all new styling, add only the minimum i18n support copy for the shared left panel, and rewrite each auth page to emit shared `auth-*` presentational classes while preserving handlers and endpoints.

**Tech Stack:** Next.js app router, React client components, TypeScript, scoped CSS in `gateway/packages/web/app/public-site.css`, Vitest + jsdom for web tests, pnpm workspace tooling

---

## File Map

### New files

- `gateway/packages/web/components/customer-auth-shell.tsx`
  Owns the warm auth shell. Composes `CokePublicShell`, resolves the active auth CTA from the pathname, renders the shared left editorial panel, and wraps auth page children.

### Modified files

- `gateway/packages/web/components/coke-public-shell.tsx`
  Adds optional active-CTA support for auth routes without changing homepage behavior.
- `gateway/packages/web/app/(customer)/auth/layout.tsx`
  Swaps `CustomerShell` out for `CustomerAuthShell`.
- `gateway/packages/web/app/public-site.css`
  Adds `.coke-site .auth-*` selectors and active header CTA styling.
- `gateway/packages/web/lib/i18n.ts`
  Adds `customerLayout.trustLines` to both locales and to the `CustomerLayoutMessages` type.
- `gateway/packages/web/app/(customer)/auth/login/page.tsx`
  Removes the page-local hero column and rewrites markup to shared auth card/form classes.
- `gateway/packages/web/app/(customer)/auth/register/page.tsx`
  Same as login.
- `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx`
  Moves the page into the shared auth card language.
- `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx`
  Same as forgot-password with token/password fields.
- `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
  Keeps auto-verify logic and recovery flow, but rewrites the recovery and loading UI to the shared auth card language.
- `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
  Rewrites to the shared auth card language.

### Test files

- `gateway/packages/web/components/coke-public-shell.test.tsx`
- `gateway/packages/web/app/(customer)/auth/layout.test.tsx`
- `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
- `gateway/packages/web/app/(customer)/auth/forgot-password/page.test.tsx`
- `gateway/packages/web/app/(customer)/auth/reset-password/page.test.tsx`
- `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- `gateway/packages/web/app/(customer)/auth/claim/page.test.tsx`

### Files that must not change

- `gateway/packages/web/components/customer-shell.tsx`
- `gateway/packages/web/app/(customer)/channels/**`
- `gateway/packages/web/app/(coke-user)/**`
- any file outside `gateway/packages/web`
- any auth endpoint path string, redirect destination, storage helper usage, or handler control flow beyond presentational extraction

## Implementation Rules

- Keep the logic freeze from `docs/superpowers/specs/2026-04-21-customer-auth-warm-redesign-design.md` intact.
- Do not touch API callers except to move them with surrounding JSX; endpoint strings must remain byte-for-byte unchanged.
- Do not change route destinations.
- Do not change `CustomerShell`; auth gets a new shell instead.
- Keep all new CSS scoped under `.coke-site`.
- Prefer small helper extraction only when it reduces presentational duplication; do not refactor unrelated logic.

## Task 1: Build the Warm Auth Shell and Shared Styling Boundary

**Files:**
- Create: `gateway/packages/web/components/customer-auth-shell.tsx`
- Modify: `gateway/packages/web/components/coke-public-shell.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/layout.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Modify: `gateway/packages/web/lib/i18n.ts`
- Test: `gateway/packages/web/components/coke-public-shell.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/layout.test.tsx`

- [ ] **Step 1: Write failing shared-shell tests**

Add assertions that prove the new shell contract exists before any implementation code changes:

```tsx
expect(container.querySelector('.coke-site')).toBeTruthy();
expect(container.querySelector('.auth-shell')).toBeTruthy();
expect(container.querySelector('.auth-hero')).toBeTruthy();
expect(container.textContent).toContain('统一管理客户登录与通道接入');
expect(container.textContent).toContain('全程加密传输');
expect(container.querySelector('a[href="/auth/login"][aria-current="page"]')).toBeTruthy();
```

Also keep the existing bilingual nav and CTA assertions in `components/coke-public-shell.test.tsx`.

- [ ] **Step 2: Run the shared-shell tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  components/coke-public-shell.test.tsx \
  app/'(customer)'/auth/layout.test.tsx
```

Expected:

- `auth-shell` / `auth-hero` selectors missing
- `aria-current="page"` assertion failing
- `trustLines` copy assertion failing

- [ ] **Step 3: Implement the new auth shell, active CTA support, shared copy, and base auth CSS**

Implementation details:

- `customer-auth-shell.tsx`
  - use `useLocale()` and `usePathname()`
  - map pathname to `activeAuthCta`
  - render `CokePublicShell activeAuthCta={...} contentClassName="auth-shell"`
  - render the shared editorial panel using `messages.customerLayout.*`
  - render `trustLines` as a simple list
- `coke-public-shell.tsx`
  - add `activeAuthCta?: 'signIn' | 'register' | null`
  - set `aria-current="page"` on the matching auth CTA only
- `layout.tsx`
  - replace `CustomerShell` with `CustomerAuthShell`
- `public-site.css`
  - add `.header-signin[aria-current="page"]`
  - add `.header-cta[aria-current="page"]`
  - add `.auth-shell`, `.auth-shell__grid`, `.auth-hero`, `.auth-hero__*`
- `i18n.ts`
  - extend `CustomerLayoutMessages` with `trustLines: string[]`
  - add `trustLines` in both locales

- [ ] **Step 4: Run the shared-shell tests to verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  components/coke-public-shell.test.tsx \
  app/'(customer)'/auth/layout.test.tsx
```

Expected: PASS

## Task 2: Move Login and Register to the Shared Auth Card System

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Test: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`

- [ ] **Step 1: Write failing login/register presentation tests without changing behavior assertions**

Add or update assertions so the tests require the shared card/form structure while keeping all existing endpoint and redirect checks:

```tsx
expect(container.querySelector('.auth-card')).toBeTruthy();
expect(container.querySelector('.auth-form')).toBeTruthy();
expect(container.querySelector('.auth-input#email')).toBeTruthy();
expect(container.querySelector('.auth-submit')).toBeTruthy();
expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
```

For register:

```tsx
expect(container.querySelector('.auth-card')).toBeTruthy();
expect(container.querySelector('.auth-input#displayName')).toBeTruthy();
expect(container.querySelector('.auth-input#password')).toBeTruthy();
expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
```

- [ ] **Step 2: Run the login/register tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/'(customer)'/auth/login/page.test.tsx \
  app/'(customer)'/auth/register/page.test.tsx
```

Expected:

- selector assertions fail because the pages still render the old Tailwind-only layout

- [ ] **Step 3: Rewrite login and register markup to shared auth classes**

Implementation details:

- remove the page-local left hero panels entirely
- wrap each page body in a single `.auth-card`
- convert field wrappers to `.auth-field`
- convert labels to `.auth-label`
- convert inputs to `.auth-input`
- convert the form to `.auth-form`
- convert the submit button to `.auth-submit`
- map the current error/warning/status blocks to `.auth-alert` variants
- keep every handler, endpoint string, stored-auth call, redirect target, and state branch untouched

Add CSS only if the base auth selectors from Task 1 are insufficient:

- `.auth-card__title`
- `.auth-card__desc`
- `.auth-alert`
- `.auth-alert--error`
- `.auth-alert--warning`
- `.auth-linkrow`

- [ ] **Step 4: Run the login/register tests to verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/'(customer)'/auth/login/page.test.tsx \
  app/'(customer)'/auth/register/page.test.tsx
```

Expected: PASS, including all existing endpoint/redirect assertions

## Task 3: Move Forgot Password, Reset Password, and Claim to the Shared Card System

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Test: `gateway/packages/web/app/(customer)/auth/forgot-password/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/reset-password/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/claim/page.test.tsx`

- [ ] **Step 1: Write failing tests for the shared auth-card structure on the three secondary pages**

Representative assertions:

```tsx
expect(container.querySelector('.auth-card')).toBeTruthy();
expect(container.querySelector('.auth-form')).toBeTruthy();
expect(container.querySelector('.auth-input#email')).toBeTruthy();
```

```tsx
expect(container.querySelector('.auth-input#token')).toBeTruthy();
expect(container.querySelector('.auth-input#confirmPassword')).toBeTruthy();
```

```tsx
expect(container.querySelector('.auth-card')).toBeTruthy();
expect(container.querySelector('a[href="/auth/login"]')).toBeTruthy();
```

Keep all existing endpoint and redirect assertions unchanged.

- [ ] **Step 2: Run the secondary-page tests to verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/'(customer)'/auth/forgot-password/page.test.tsx \
  app/'(customer)'/auth/reset-password/page.test.tsx \
  app/'(customer)'/auth/claim/page.test.tsx
```

Expected: FAIL on the new auth-card/auth-input selectors

- [ ] **Step 3: Rewrite the three pages to shared card/form classes**

Implementation details:

- preserve:
  - `/api/coke/forgot-password`
  - `/api/coke/reset-password`
  - `/api/auth/claim`
  - token prefill in reset
  - token prefill plus URL cleanup in claim
  - redirect behavior
  - mismatch validation
- rewrite only the rendered markup and class names
- use `.auth-linkrow` for the bottom helper links
- use `.auth-alert--error` for existing error panels

- [ ] **Step 4: Run the secondary-page tests to verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  app/'(customer)'/auth/forgot-password/page.test.tsx \
  app/'(customer)'/auth/reset-password/page.test.tsx \
  app/'(customer)'/auth/claim/page.test.tsx
```

Expected: PASS

## Task 4: Move Verify Email to the Shared Card System and Run Full Gateway-Web Verification

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Test: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- Verify: the full auth/web test set and build commands below

- [ ] **Step 1: Write failing verify-email tests for the shared card and warning/recovery styles**

Add assertions such as:

```tsx
expect(container.querySelector('.auth-card')).toBeTruthy();
expect(container.querySelector('.auth-alert--warning')).toBeTruthy();
expect(container.querySelector('.auth-input#email')).toBeTruthy();
```

Keep the existing behavior assertions:

- auto-verify still posts to `/api/auth/verify-email`
- recovery resend still posts to `/api/auth/resend-verification`
- redirects still go to the same destinations

- [ ] **Step 2: Run the verify-email test to verify it fails**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/'(customer)'/auth/verify-email/page.test.tsx
```

Expected: FAIL on the new auth-card/auth-alert selector assertions

- [ ] **Step 3: Rewrite verify-email UI to the shared auth-card system**

Implementation details:

- keep the auto-verify side effect untouched
- keep the recovery-mode branching untouched
- use:
  - `.auth-card`
  - `.auth-card__title`
  - `.auth-card__desc`
  - `.auth-alert--warning`
  - `.auth-input`
  - `.auth-submit`
  - `.auth-alert--success` / `.auth-alert--error` for resend status if needed

- [ ] **Step 4: Run the verify-email test to verify it passes**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/'(customer)'/auth/verify-email/page.test.tsx
```

Expected: PASS

- [ ] **Step 5: Run the full auth/web verification set**

Run:

```bash
pnpm --dir gateway/packages/web test -- \
  components/coke-public-shell.test.tsx \
  app/'(customer)'/auth/layout.test.tsx \
  app/'(customer)'/auth/login/page.test.tsx \
  app/'(customer)'/auth/register/page.test.tsx \
  app/'(customer)'/auth/forgot-password/page.test.tsx \
  app/'(customer)'/auth/reset-password/page.test.tsx \
  app/'(customer)'/auth/verify-email/page.test.tsx \
  app/'(customer)'/auth/claim/page.test.tsx

pnpm --dir gateway/packages/web lint
pnpm --dir gateway/packages/web build
```

Expected:

- all targeted auth/web tests pass
- lint exits 0
- build exits 0

## Self-Review Checklist

- Spec coverage:
  - auth-only warm shell: Task 1
  - active public header CTAs: Task 1
  - `.coke-site`-scoped shared auth styling: Tasks 1-4
  - login/register shell and shared card move: Task 2
  - forgot/reset/claim move: Task 3
  - verify-email move while preserving recovery behavior: Task 4
  - frontend-only logic freeze: all tasks explicitly ban behavior edits
- Placeholder scan:
  - no TODO/TBD placeholders
  - all files and commands are named explicitly
- Type consistency:
  - `activeAuthCta` uses `'signIn' | 'register' | null`
  - `CustomerLayoutMessages` gains `trustLines: string[]`

## Execution Handoff

The user already chose the recommended path: execute this plan with
subagent-driven development in the current session.
