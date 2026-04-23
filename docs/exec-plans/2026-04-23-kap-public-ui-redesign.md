# Kap Public UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand outward-facing gateway web pages from Coke to Kap and migrate them onto the `index (1)(1).html` visual system without changing routes or runtime behavior.

**Architecture:** Keep the existing route and behavior graph, but centralize the redesign in the shared public shell, outward-facing i18n copy, and `public-site.css`. Rebuild the homepage as a reference-style marketing page, then pull `/global`, `/auth/*`, `/account/*`, and `/channels/*` onto the same Kap design language with targeted component updates instead of route rewrites.

**Tech Stack:** Next.js app router, React client components, TypeScript, Vitest, CSS in `app/public-site.css`, locale copy in `lib/i18n.ts`

---

## Inputs

- Related task: `tasks/2026-04-23-kap-public-ui-redesign.md`
- Related references:
  - `docs/superpowers/specs/2026-04-23-kap-public-ui-redesign-design.md`
  - `tasks/index (1)(1).html`

## Touched Surfaces

- gateway-web

## Execution Notes

- Use `.worktrees/kap-public-ui-redesign` as the isolated worktree before starting implementation.
- Baseline verification before edits:

```bash
pnpm --dir gateway/packages/web test -- app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx app/layout.metadata.test.ts
```

- If baseline fails in the clean worktree, stop and inspect before continuing.

### Task 1: Kap Brand Foundation And Shared Shell

**Files:**
- Modify: `gateway/packages/web/app/layout.tsx`
- Modify: `gateway/packages/web/app/layout.metadata.test.ts`
- Modify: `gateway/packages/web/components/coke-public-shell.tsx`
- Modify: `gateway/packages/web/components/customer-auth-shell.tsx`
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Modify: `gateway/packages/web/lib/i18n.ts`
- Modify: `gateway/packages/web/app/public-site.css`
- Test: `gateway/packages/web/app/layout.metadata.test.ts`

- [ ] **Step 1: Write the failing brand assertions**

```ts
// app/layout.metadata.test.ts
it('brands the public site title as kap', () => {
  expect(metadata.title).toBe('kap | An AI Partner That Grows With You');
});
```

```ts
// components/coke-homepage.test.tsx
expect(container.textContent).toContain('kap');
expect(container.textContent).not.toContain('coke');
```

- [ ] **Step 2: Run the targeted brand tests and verify they fail for the old brand**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/layout.metadata.test.ts app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx
```

Expected: FAIL on `coke` / `Coke AI` assertions.

- [ ] **Step 3: Replace outward-facing brand metadata and shell copy with Kap**

```tsx
// app/layout.tsx
export const metadata: Metadata = {
  title: 'kap | An AI Partner That Grows With You',
  description: 'Kap AI public homepage, user sign-in, registration, and personal channel setup.',
  icons: { icon: '/logo.png' },
};
```

```tsx
// components/coke-public-shell.tsx
<Link href="/" className="brand" aria-label="Kap AI">
  <span className="brand__mark">kap</span>
  <span className="brand__dot" aria-hidden="true" />
</Link>
```

```ts
// lib/i18n.ts
brandName: 'Kap AI',
copyright: '© 2026 Kap AI',
```

- [ ] **Step 4: Introduce Kap-wide shared tokens and header/button primitives in `public-site.css`**

```css
.coke-site {
  --kap-cream: #f6efe3;
  --kap-olive: #5e6a3a;
  --kap-orange: #d96a2c;
  --kap-ink: #2b241e;
  --kap-shadow-stamp: 0 4px 0 rgba(43, 36, 30, 0.9);
  --font-display: var(--font-fraunces, 'Fraunces', Georgia, serif);
}

.coke-site .site-header {
  background: rgba(251, 247, 238, 0.88);
  border-bottom: 2px solid var(--kap-ink);
}

.coke-site .header-cta {
  background: var(--kap-orange);
  color: #fff9ee;
  box-shadow: var(--kap-shadow-stamp);
}
```

- [ ] **Step 5: Run the same brand tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/layout.metadata.test.ts app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx
```

Expected: PASS.

### Task 2: Rebuild The Homepage And Global Marketing Pages

**Files:**
- Modify: `gateway/packages/web/components/coke-homepage.tsx`
- Modify: `gateway/packages/web/components/global-homepage.tsx`
- Modify: `gateway/packages/web/app/global/page.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Modify: `gateway/packages/web/app/page.test.tsx`
- Modify: `gateway/packages/web/components/coke-homepage.test.tsx`
- Modify: `gateway/packages/web/components/global-homepage.test.tsx`
- Test: `gateway/packages/web/app/page.test.tsx`
- Test: `gateway/packages/web/components/coke-homepage.test.tsx`
- Test: `gateway/packages/web/components/global-homepage.test.tsx`

- [ ] **Step 1: Write failing tests for the new marketing structure**

```ts
// components/coke-homepage.test.tsx
expect(container.querySelector('#capabilities')).toBeTruthy();
expect(container.querySelector('#scenarios')).toBeTruthy();
expect(container.querySelector('#download')).toBeTruthy();
expect(container.textContent).toContain('Kap AI');
expect(container.querySelector('a[href="/auth/register"]')).toBeTruthy();
```

```ts
// components/global-homepage.test.tsx
expect(container.textContent).toContain('Kap on WhatsApp');
expect(container.querySelector('.global-site')).toBeTruthy();
expect(container.textContent).not.toContain('Coke');
```

- [ ] **Step 2: Run homepage/global tests and verify they fail on missing sections and old copy**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx
```

Expected: FAIL because the current homepage still renders `#platforms`, `#features`, `#architecture`, and old Coke copy.

- [ ] **Step 3: Replace the homepage composition with a reference-style landing page**

```tsx
// components/coke-homepage.tsx
export function CokeHomepage() {
  return (
    <CokePublicShell>
      <Hero />
      <Ticker />
      <Capabilities />
      <Scenarios />
      <QuoteBand />
      <CloseCta />
      <Footer />
    </CokePublicShell>
  );
}
```

```tsx
// hero CTA preservation
<Link href="/auth/register" className="btn-sticker">
  {hero.primaryCta}
</Link>
<Link href="/auth/login" className="btn-ghost">
  {hero.secondaryCta}
</Link>
```

- [ ] **Step 4: Move the homepage and global page styling onto the reference visual language**

```css
.coke-site .hero,
.coke-site .ticker,
.coke-site .caps,
.coke-site .scen-grid,
.coke-site .quoteband,
.coke-site .dl-card {
  border-color: var(--kap-ink);
  box-shadow: var(--kap-shadow-stamp);
  background: var(--kap-cream);
}

.global-site .global-header,
.global-site .global-hero,
.global-site .global-section,
.global-site .global-close {
  background: var(--kap-cream);
  color: var(--kap-ink);
}
```

- [ ] **Step 5: Update global metadata to Kap branding**

```ts
// app/global/page.tsx
export const metadata: Metadata = {
  title: 'kap global | AI partner on WhatsApp',
  description: 'Start a WhatsApp conversation with Kap and use one thread for planning, coordination, and follow-through.',
};
```

- [ ] **Step 6: Run the homepage/global tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx
```

Expected: PASS with the new section IDs, Kap branding, and live CTA routes.

### Task 3: Migrate Auth Surfaces Onto The Kap Theme

**Files:**
- Modify: `gateway/packages/web/components/customer-auth-shell.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Modify: `gateway/packages/web/lib/i18n.ts`
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/forgot-password/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/reset-password/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/claim/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/claim-entry/page.test.tsx`

- [ ] **Step 1: Write failing auth tests for Kap copy and homepage links**

```ts
// app/(customer)/auth/login/page.test.tsx
expect(container.textContent).toContain('Sign in to Kap');
expect(container.textContent).not.toContain('Sign in to Coke');
```

```ts
// app/(customer)/auth/register/page.test.tsx
expect(container.textContent).toContain('创建你的 Kap 账号');
expect(container.textContent).not.toContain('创建你的 Coke 账号');
```

- [ ] **Step 2: Run auth tests and verify they fail on the old Coke branding**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/auth/login/page.test.tsx' 'app/(customer)/auth/register/page.test.tsx' 'app/(customer)/auth/forgot-password/page.test.tsx' 'app/(customer)/auth/reset-password/page.test.tsx' 'app/(customer)/auth/verify-email/page.test.tsx' 'app/(customer)/auth/claim/page.test.tsx' 'app/(customer)/auth/claim-entry/page.test.tsx'
```

Expected: FAIL on Kap copy assertions.

- [ ] **Step 3: Update auth-shell copy and styling to the Kap marketing system**

```tsx
// components/customer-auth-shell.tsx
<section className="auth-hero kap-auth-hero" aria-label={copy.title}>
  <p className="auth-hero__brand">{copy.brandName}</p>
  <p className="auth-hero__tagline">{copy.brandTagline}</p>
  <p className="auth-hero__eyebrow">{copy.eyebrow}</p>
  <h1 className="auth-hero__title">{copy.title}</h1>
  <p className="auth-hero__body">{copy.body}</p>
</section>
```

```ts
// lib/i18n.ts
title: 'Sign in to Kap',
submit: 'Sign in to Kap',
heroTitle: 'Return to your Kap account',
```

- [ ] **Step 4: Extend auth card and alert styling without changing form behavior**

```css
.coke-site .auth-card,
.coke-site .auth-alert,
.coke-site .auth-submit,
.coke-site .auth-input,
.coke-site .auth-linkrow {
  border-color: var(--kap-ink);
  color: var(--kap-ink);
  background: #fbf7ee;
}
```

- [ ] **Step 5: Run the auth suite and verify it passes**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/auth/login/page.test.tsx' 'app/(customer)/auth/register/page.test.tsx' 'app/(customer)/auth/forgot-password/page.test.tsx' 'app/(customer)/auth/reset-password/page.test.tsx' 'app/(customer)/auth/verify-email/page.test.tsx' 'app/(customer)/auth/claim/page.test.tsx' 'app/(customer)/auth/claim-entry/page.test.tsx'
```

Expected: PASS with Kap copy and unchanged form flows.

### Task 4: Restyle Customer Account And Channel Surfaces

**Files:**
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Modify: `gateway/packages/web/app/public-site.css`
- Modify: `gateway/packages/web/app/(customer)/channels/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/subscription/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/calendar-import/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx`
- Modify: `gateway/packages/web/lib/i18n.ts`
- Modify: `gateway/packages/web/app/(customer)/channels/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/channels/wechat-personal/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/layout.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/subscription/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/calendar-import/page.test.tsx`

- [ ] **Step 1: Write failing customer-surface tests for Kap branding and shared shell usage**

```ts
// app/(customer)/account/subscription/page.test.tsx
expect(container.textContent).toContain('Renew your Kap access');
```

```ts
// app/(customer)/channels/wechat-personal/page.test.tsx
expect(container.textContent).toContain('Kap');
expect(container.textContent).not.toContain('Coke');
```

- [ ] **Step 2: Run the customer-facing tests and verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/channels/page.test.tsx' 'app/(customer)/channels/wechat-personal/page.test.tsx' 'app/(customer)/account/layout.test.tsx' 'app/(customer)/account/subscription/page.test.tsx' 'app/(customer)/account/calendar-import/page.test.tsx'
```

Expected: FAIL on Kap branding and updated shell expectations.

- [ ] **Step 3: Replace the dark customer shell and ad-hoc Tailwind cards with Kap surface classes**

```tsx
// components/customer-shell.tsx
return (
  <div className="coke-site kap-customer-shell">
    <header className="site-header">
      <div className="site-header__inner">
        <Link href="/" className="brand" aria-label="Kap AI">
          <span className="brand__mark">kap</span>
          <span className="brand__dot" aria-hidden="true" />
        </Link>
        <div className="site-header__actions">
          <LocaleSwitch />
        </div>
      </div>
    </header>
    <main className="kap-customer-shell__main">{children}</main>
  </div>
);
```

```tsx
// app/(customer)/account/subscription/page.tsx
<section className="kap-surface-card kap-surface-card--narrow">
  <h1 className="kap-surface-card__title">{renewCopy.title}</h1>
  <p className="kap-surface-card__body">{renewCopy.description}</p>
  <div className="kap-surface-card__actions">
    <button type="button" className="btn-sticker">
      {copy.renewSubscription}
    </button>
    <Link href="/channels/wechat-personal" className="btn-ghost">
      {renewCopy.backToSetup}
    </Link>
  </div>
</section>
```

- [ ] **Step 4: Keep `wechat-personal` behavior intact while aligning its states with Kap surfaces**

```css
.coke-site .customer-channel-page__card,
.coke-site .customer-channel-page__surface,
.coke-site .customer-channel-page__button,
.coke-site .kap-surface-card {
  border: 2px solid var(--kap-ink);
  background: #fbf7ee;
  box-shadow: var(--kap-shadow-stamp);
}
```

- [ ] **Step 5: Run the customer-facing tests and verify they pass**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/channels/page.test.tsx' 'app/(customer)/channels/wechat-personal/page.test.tsx' 'app/(customer)/account/layout.test.tsx' 'app/(customer)/account/subscription/page.test.tsx' 'app/(customer)/account/calendar-import/page.test.tsx'
```

Expected: PASS with unchanged redirects/state logic and new Kap styling/copy.

## Final Verification

- [ ] Run the focused gateway web suite after all tasks complete

```bash
pnpm --dir gateway/packages/web test -- app/page.test.tsx components/coke-homepage.test.tsx components/global-homepage.test.tsx app/layout.metadata.test.ts 'app/(customer)/auth/login/page.test.tsx' 'app/(customer)/auth/register/page.test.tsx' 'app/(customer)/channels/page.test.tsx' 'app/(customer)/channels/wechat-personal/page.test.tsx' 'app/(customer)/account/subscription/page.test.tsx' 'app/(customer)/account/calendar-import/page.test.tsx'
```

Expected: PASS.

- [ ] Run the broader gateway web suite if the shared-shell/CSS changes caused collateral updates

```bash
pnpm --dir gateway/packages/web test
```

Expected: PASS, or documented unrelated failures if the baseline was already broken.

## Risks

- `lib/i18n.ts` is large and shared; copy changes must stay scoped to outward-facing text.
- `public-site.css` is the common styling entrypoint for homepage, auth, and customer pages; selector collisions are the main regression risk.
- `subscription/page.tsx` and `channels/page.tsx` currently rely on inline Tailwind class composition and will need careful visual convergence without changing control flow.
