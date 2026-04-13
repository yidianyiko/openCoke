# Coke Public Homepage and Auth Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the web root with a public Coke homepage, restyle Coke user auth pages to match that public surface, and move the admin console under `/dashboard/*`.

**Architecture:** Keep the public Coke experience and the admin console as separate route namespaces inside the Next.js app. Build a small shared Coke public/auth visual shell for `/` and `/coke/*`, then remap the existing admin route tree under `/dashboard/*` and update auth redirects and nav links to use the new namespace.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Tailwind CSS 4, Vitest, pnpm

---

## Scope Check

This plan stays inside the `gateway/packages/web` frontend surface. It does not require backend contract changes, which keeps the work to one coherent frontend routing and UX slice.

## File Structure

### New files

- `gateway/packages/web/app/page.tsx`
  Public Coke homepage at `/`.
- `gateway/packages/web/app/page.test.tsx`
  Verifies the homepage exposes Coke auth entry points and product copy.
- `gateway/packages/web/components/coke-public-shell.tsx`
  Shared public/auth page shell.
- `gateway/packages/web/components/coke-homepage.tsx`
  Homepage sections and public CTA layout.
- `gateway/packages/web/app/dashboard/layout.tsx`
  Admin layout under `/dashboard`.
- `gateway/packages/web/app/dashboard/page.tsx`
  Admin dashboard home route.
- `gateway/packages/web/app/dashboard/login/page.tsx`
  Admin login route.
- `gateway/packages/web/app/dashboard/register/page.tsx`
  Admin register route if still needed.
- `gateway/packages/web/app/dashboard/onboard/page.tsx`
  Admin onboard route if still needed.

### Modified files

- `gateway/packages/web/app/layout.tsx`
  Update metadata to Coke-focused public defaults.
- `gateway/packages/web/app/(coke-user)/coke/layout.tsx`
  Replace the thin header-only layout with the shared Coke public/auth shell.
- `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
  Restyle login and keep existing auth behavior.
- `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`
  Expand assertions for the branded page.
- `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`
  Restyle registration and keep the same post-register flow.
- `gateway/packages/web/app/(dashboard)/layout.tsx`
  This file will either be removed or replaced by the new `/dashboard` layout approach.
- `gateway/packages/web/app/(dashboard)/page.tsx`
  This file will either move or be replaced by the new `/dashboard` route.
- `gateway/packages/web/app/(dashboard)/conversations/page.tsx`
- `gateway/packages/web/app/(dashboard)/channels/page.tsx`
- `gateway/packages/web/app/(dashboard)/ai-backends/page.tsx`
- `gateway/packages/web/app/(dashboard)/workflows/page.tsx`
- `gateway/packages/web/app/(dashboard)/end-users/page.tsx`
- `gateway/packages/web/app/(dashboard)/users/page.tsx`
- `gateway/packages/web/app/(dashboard)/settings/page.tsx`
  These routes will move under `/dashboard/*`.
- `gateway/packages/web/app/login/page.tsx`
- `gateway/packages/web/app/register/page.tsx`
- `gateway/packages/web/app/onboard/page.tsx`
  These root-level admin entry points will move to `/dashboard/*`.

---

### Task 1: Write failing tests for the new public and admin routing expectations

**Files:**
- Create: `gateway/packages/web/app/page.test.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.test.tsx`

- [ ] **Step 1: Write the failing homepage test**

```tsx
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import HomePage from './page';

describe('HomePage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
  });

  it('links public visitors to Coke registration and sign-in', () => {
    flushSync(() => {
      root.render(<HomePage />);
    });

    expect(container.querySelector('a[href=\"/coke/register\"]')).toBeTruthy();
    expect(container.querySelector('a[href=\"/coke/login\"]')).toBeTruthy();
    expect(container.textContent).toContain('An AI Partner That Grows With You');
  });
});
```

- [ ] **Step 2: Expand the failing Coke login page test**

```tsx
it('shows public navigation and both auth recovery links', () => {
  flushSync(() => {
    root.render(<CokeLoginPage />);
  });

  expect(container.querySelector('a[href=\"/\"]')).toBeTruthy();
  expect(container.querySelector('a[href=\"/coke/forgot-password\"]')).toBeTruthy();
  expect(container.querySelector('a[href=\"/coke/register\"]')).toBeTruthy();
  expect(container.textContent).toContain('Sign in to Coke');
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pnpm --dir gateway --filter @clawscale/web test -- app/page.test.tsx app/'(coke-user)'/coke/login/page.test.tsx`

Expected: FAIL because `app/page.tsx` does not exist yet and the current login page does not render the new public shell expectations.

### Task 2: Implement the shared public Coke shell and the new homepage

**Files:**
- Create: `gateway/packages/web/components/coke-public-shell.tsx`
- Create: `gateway/packages/web/components/coke-homepage.tsx`
- Create: `gateway/packages/web/app/page.tsx`
- Modify: `gateway/packages/web/app/layout.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/layout.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/login/page.tsx`
- Modify: `gateway/packages/web/app/(coke-user)/coke/register/page.tsx`

- [ ] **Step 1: Implement the shared shell**

```tsx
export function CokePublicShell({
  children,
  eyebrow,
  title,
  subtitle,
}: {
  children: React.ReactNode;
  eyebrow?: string;
  title?: string;
  subtitle?: string;
}) {
  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_#12304d,_#09111f_55%,_#060b14)] text-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Link href="/" className="text-xl font-semibold tracking-tight">
          Coke AI
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          <Link href="/coke/register" className="rounded-full bg-white px-4 py-2 text-slate-950">
            Register
          </Link>
          <Link href="/coke/login" className="rounded-full border border-white/20 px-4 py-2">
            Sign in
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 pb-16">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Implement the homepage sections**

```tsx
export function CokeHomepage() {
  return (
    <CokePublicShell>
      <section className="grid gap-10 py-14 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-teal-300">Evolves With You</p>
          <h1 className="mt-5 text-5xl font-semibold leading-tight">
            与您共同成长的 AI 助手
          </h1>
          <p className="mt-4 text-xl text-slate-200">An AI Partner That Grows With You</p>
          <div className="mt-8 flex gap-3">
            <Link href="/coke/register">Register</Link>
            <Link href="/coke/login">Sign in</Link>
          </div>
        </div>
      </section>
    </CokePublicShell>
  );
}
```

- [ ] **Step 3: Apply the shell to Coke auth pages**

```tsx
export default function CokeUserLayout({ children }: { children: React.ReactNode }) {
  return (
    <CokePublicShell
      eyebrow="Coke account"
      title="Access your personal AI workspace"
      subtitle="Sign in, verify your account, and continue to your WeChat binding flow."
    >
      {children}
    </CokePublicShell>
  );
}
```

- [ ] **Step 4: Restyle the login and registration cards with the shared visual language**

```tsx
<section className="grid gap-8 lg:grid-cols-[0.95fr_1.05fr]">
  <div className="rounded-[2rem] border border-white/10 bg-white/5 p-8 text-slate-100">
    <h2 className="text-3xl font-semibold">Manage your Coke account</h2>
  </div>
  <div className="rounded-[2rem] bg-white p-8 text-slate-950 shadow-2xl">
    {/* existing form fields and submit behavior */}
  </div>
</section>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pnpm --dir gateway --filter @clawscale/web test -- app/page.test.tsx app/'(coke-user)'/coke/login/page.test.tsx`

Expected: PASS

### Task 3: Move the admin surface under `/dashboard`

**Files:**
- Create: `gateway/packages/web/app/dashboard/layout.tsx`
- Create: `gateway/packages/web/app/dashboard/page.tsx`
- Create: `gateway/packages/web/app/dashboard/login/page.tsx`
- Create: `gateway/packages/web/app/dashboard/register/page.tsx`
- Create: `gateway/packages/web/app/dashboard/onboard/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/conversations/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/channels/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/ai-backends/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/workflows/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/end-users/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/users/page.tsx`
- Create or move: `gateway/packages/web/app/dashboard/settings/page.tsx`

- [ ] **Step 1: Update the admin layout navigation and redirect target**

```tsx
const navItems = [
  { href: '/dashboard', label: 'Dashboard', exact: true },
  { href: '/dashboard/conversations', label: 'Conversations' },
  { href: '/dashboard/channels', label: 'Channels' },
];

useEffect(() => {
  if (!isAuthenticated()) {
    router.replace('/dashboard/login');
    return;
  }
  setReady(true);
}, [router]);
```

- [ ] **Step 2: Move or recreate the existing admin pages under the `/dashboard` segment**

```tsx
export { default } from '../../(dashboard)/conversations/page';
```

Use re-export stubs only if they reduce churn cleanly. If route-group coupling becomes awkward, copy the files into `app/dashboard/*` and remove the old root-level versions in the same change.

- [ ] **Step 3: Move the admin login/register/onboard routes**

```tsx
// app/dashboard/login/page.tsx
export { default } from '../../login/page';
```

After the new routes exist, remove or replace the old root-level admin entry points so `/login`, `/register`, and `/onboard` are no longer the operator surface.

- [ ] **Step 4: Run the focused web test suite**

Run: `pnpm --dir gateway --filter @clawscale/web test`

Expected: PASS with no new route or auth regressions.

### Task 4: Run production verification for the web package

**Files:**
- No code changes required unless verification exposes issues.

- [ ] **Step 1: Run the production build**

Run: `pnpm --dir gateway --filter @clawscale/web build`

Expected: successful Next.js build with the new `/`, `/coke/*`, and `/dashboard/*` routes.

- [ ] **Step 2: Review route and auth requirements against the spec**

Checklist:
- `/` is public and product-focused
- `/coke/login` and `/coke/register` use the branded shell
- Coke sign-in still lands on `/coke/bind-wechat`
- admin layout redirects to `/dashboard/login`
- admin navigation points only to `/dashboard/*`

- [ ] **Step 3: Commit**

```bash
git -C gateway add packages/web
git -C gateway commit -m "feat(web): separate coke homepage and dashboard routes"
git add docs/superpowers/specs/2026-04-14-coke-public-homepage-auth-design.md docs/superpowers/plans/2026-04-14-coke-public-homepage-auth-plan.md
git commit -m "docs(coke): add homepage and auth separation spec"
```

## Self-Review

### Spec coverage

- Public homepage replacement is covered by Task 2.
- Coke auth visual integration is covered by Task 2.
- Admin route isolation is covered by Task 3.
- Verification is covered by Task 4.

### Placeholder scan

No `TODO`, `TBD`, or delegated placeholders remain. The only implementation flexibility is whether admin page migration uses re-exports or copied files, and that choice is constrained to the same target route structure.

### Type consistency

The plan keeps existing auth helpers and Coke user API contracts unchanged. New shared UI is additive and does not rename the existing Coke auth result types or request functions.
