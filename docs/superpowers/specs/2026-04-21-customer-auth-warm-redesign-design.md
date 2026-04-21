# Coke Customer Auth — Warm Editorial Redesign (Design)

**Status:** approved for implementation
**Date:** 2026-04-21
**Surfaces:** `gateway/packages/web` customer auth pages only
**References:** `docs/superpowers/specs/2026-04-21-coke-public-homepage-warm-redesign-design.md`, `gateway/packages/web/app/public-site.css`

## Goal

Redesign the six customer auth routes so they feel like a direct continuation
of the warm public homepage instead of a separate dark product surface:

- `/auth/login`
- `/auth/register`
- `/auth/forgot-password`
- `/auth/reset-password`
- `/auth/verify-email`
- `/auth/claim`

The redesign is visual-only. Existing auth logic, route behavior, redirects,
API callers, storage, and locale bootstrap behavior stay intact.

## Non-Goals

- No change to `(customer)/channels`, `(coke-user)/*`, or `(admin)/admin/login`.
- No change to auth endpoints, error handling logic, router destinations, or
  token persistence.
- No change to `components/customer-shell.tsx`; that shell remains the darker
  workspace shell for channels and other logged-in customer surfaces.
- No change to `app/globals.css` or the Tailwind token system used outside the
  public-site scope.
- No copy rewrite project. Existing auth copy stays unless a tiny additive key
  is required to support the new shell.

## Scope

The implementation should touch only the files needed to move auth onto a new
warm shell:

1. a dedicated auth shell layered on top of the public-site header
2. the six auth page components, rewritten to emit shared `auth-*` classes
   instead of page-local Tailwind layout wrappers
3. additive `.coke-site .auth-*` rules in `app/public-site.css`
4. minimal `lib/i18n.ts` additions for shared auth-shell support copy
5. the auth/layout and auth/page tests plus the shared public-shell test

If a change is not required for that list, it is out of scope.

## Logic Freeze

This redesign is strictly a frontend presentation change. It must not change
product behavior.

### Allowed changes

- auth shell composition
- JSX structure reshaping needed to apply shared `auth-*` classes
- `className` changes
- additive CSS in `gateway/packages/web/app/public-site.css`
- small additive i18n support keys for shell-only copy
- test assertion updates required by markup changes

### Forbidden changes

- any file under `gateway/packages/api`, `gateway/packages/shared`,
  `connector/`, `agent/`, `dao/`, `entity/`, `framework/`, or `util/`
- endpoint path, HTTP method, request payload, or response-shape changes
- auth storage behavior changes
- redirect destination changes
- `next` sanitization or query-param parsing changes
- success/error/recovery branching changes
- validation rule changes

### Review rule

If an implementation PR changes any of the following, it is out of spec and
should be sent back:

- API call strings such as `/api/auth/login`, `/api/auth/register`,
  `/api/auth/resend-verification`, `/api/coke/forgot-password`,
  `/api/coke/reset-password`, `/api/auth/claim`, or `/api/coke/me`
- router destinations such as `/auth/login`, `/auth/verify-email`, or
  `/channels/wechat-personal`
- handler control flow beyond the minimal extraction needed to reuse shared
  presentational wrappers

## Core Decisions

### 1. Auth opts into `.coke-site`, but only auth

Auth pages should stop using `CustomerShell` and instead render inside a new
dedicated auth shell that composes `CokePublicShell`.

This preserves the isolation rule already established by the homepage redesign:

- warm tokens and component styles live only under `.coke-site`
- admin and logged-in customer workspace pages stay on their existing styling
- `app/public-site.css` remains the single source of truth for the warm system

### 2. Reuse the full public header

Auth should use the same sticky header as `/`:

- brand mark linking to `/`
- nav links back to `/#platforms`, `/#features`, `/#architecture`, `/#contact`
- `LocaleSwitch`
- `Sign in` and `Register` CTAs

`CokePublicShell` should gain an optional `activeAuthCta` prop:

- `'signIn'` on `/auth/login`
- `'register'` on `/auth/register`
- `null` on `/auth/forgot-password`, `/auth/reset-password`,
  `/auth/verify-email`, and `/auth/claim`

Active state should be exposed through `aria-current="page"` plus a visual
state in `public-site.css`. Do not special-case the click target beyond that;
same-route navigation is harmless and the active state is enough to remove the
"why am I clicking myself?" feeling.

### 3. Use one shared editorial left panel

The left column should be shared across all six auth routes instead of
re-inventing a page-specific shell for every screen. This is the main
engineering simplification in the spec.

Reasoning:

- the current layout already centralizes auth shell behavior in
  `app/(customer)/auth/layout.tsx`
- keeping the left panel shared avoids route-to-copy plumbing and keeps the
  layout reusable
- page-level specificity already exists in each card title, description,
  recovery state, and footer links

The shared panel still needs to feel on-brand and intentional. It should use
`messages.customerLayout` plus one small additive `trustLines` array.

### 4. Inputs become rounded rectangles; buttons stay pill-shaped

Use the warm system for controls:

- inputs: rounded rectangle, label above, white background, warm ink border,
  claw-orange focus ring
- submit buttons: reuse the homepage button language, full-width pill primary
  button
- inline text links: ink text with underline offset, same family as homepage

This keeps data-entry dense and readable without forcing the homepage's pill
input style onto forms that have three or four stacked fields.

## Shell Structure

Create a dedicated component:

- `gateway/packages/web/components/customer-auth-shell.tsx`

This component should compose `CokePublicShell` and own the two-column auth
layout. `app/(customer)/auth/layout.tsx` should become a thin wrapper around
it.

Recommended markup shape:

```tsx
<CokePublicShell activeAuthCta={activeAuthCta} contentClassName="auth-shell">
  <section className="auth-shell__grid">
    <aside className="auth-hero">
      <p className="auth-hero__eyebrow">{copy.eyebrow}</p>
      <p className="auth-hero__kicker">{copy.brandTagline}</p>
      <h1 className="auth-hero__title">{copy.title}</h1>
      <p className="auth-hero__lede">{copy.body}</p>
      <p className="auth-hero__lede auth-hero__lede--secondary">{copy.secondaryBody}</p>
      <p className="auth-hero__meta">{copy.navLabel}</p>
      <ul className="auth-hero__trust">…</ul>
    </aside>
    <div className="auth-shell__content">{children}</div>
  </section>
</CokePublicShell>
```

Notes:

- Keep this as a client component so it can inspect `usePathname()` for the
  active auth CTA.
- Do not import or reuse `CustomerShell`.
- Do not add a footer; auth should reuse the public header, not the homepage's
  page-specific footer section.

## Visual System

All new selectors live in `gateway/packages/web/app/public-site.css` and stay
scoped under `.coke-site`.

### Page layout

- `.auth-shell`
  - `padding: 56px 0 80px`
- `.auth-shell__grid`
  - `max-width: var(--max-content)`
  - `margin: 0 auto`
  - `padding: 0 var(--gutter)`
  - `display: grid`
  - `grid-template-columns: minmax(0, 0.95fr) minmax(0, 0.9fr)`
  - `gap: 32px`
  - `align-items: start`
- `< 1024px`
  - stack to one column
  - hero above the card
  - reduce horizontal padding to the same mobile gutter pattern used by the
    homepage

### Shared editorial panel

- `.auth-hero`
  - soft warm card, not a dark panel
  - `background: linear-gradient(145deg, rgba(255,255,255,0.78), rgba(246,241,232,0.92))`
  - `border: 1px solid var(--ink-08)`
  - `border-radius: var(--radius-lg)`
  - `box-shadow: var(--shadow-sm)`
  - `padding: 40px 36px`
- `.auth-hero__eyebrow`
  - pill treatment matching the homepage eyebrow language
- `.auth-hero__kicker`
  - small uppercase support line in warm muted ink
- `.auth-hero__title`
  - Fraunces display
  - `font-size: clamp(34px, 4vw, 52px)`
  - `line-height: 1.04`
  - `font-variation-settings: 'SOFT' 40, 'opsz' 120`
- `.auth-hero__lede`
  - 17px, `line-height: 1.55`, `color: var(--ink-700)`
- `.auth-hero__meta`
  - small mono or uppercased support line
  - this is where the existing `navLabel` stays visible so the old layout
    contract remains represented
- `.auth-hero__trust`
  - three short rows or chips
  - mono or semi-mono treatment is fine, but keep it quiet

### Auth card

- `.auth-card`
  - `max-width: 560px`
  - `width: 100%`
  - `background: #fff`
  - `border: 1px solid var(--ink-08)`
  - `border-radius: var(--radius-lg)`
  - `box-shadow: var(--shadow-md)`
  - `padding: 40px 36px`
- `.auth-card__eyebrow`
  - optional, only render where the route already has a natural eyebrow label
- `.auth-card__title`
  - Fraunces display, 32px to 36px
- `.auth-card__desc`
  - 14px to 15px body copy in `var(--ink-700)`

### Form system

- `.auth-form`
  - vertical stack with `gap: 20px`
- `.auth-field`
  - vertical stack with `gap: 8px`
- `.auth-label`
  - 14px, semibold, normal case
  - do not use uppercase labels because the Chinese locale reads poorly with
    that treatment
- `.auth-input`
  - `border-radius: var(--radius-md)`
  - `border: 1px solid var(--ink-20)`
  - `background: #fff`
  - `padding: 14px 16px`
  - `font-size: 15px`
  - `color: var(--ink-900)`
  - focus: `border-color: var(--claw-500)` plus `box-shadow: 0 0 0 4px var(--claw-50)`
- `.auth-submit`
  - full-width primary button
  - reuse the homepage button treatment where practical
- keep the current field ids intact:
  - `displayName`
  - `email`
  - `password`
  - `confirmPassword`
  - `token`

### Alerts and recovery blocks

Add three variants so the existing status logic can drop into the warm system
without branching by route:

- `.auth-alert--error`
  - pale clay background, warm red text, subtle error border
- `.auth-alert--warning`
  - pale amber background for verification recovery states
- `.auth-alert--success`
  - pale olive/teal background for resend or completion confirmation

Do not invent new alert logic. This is only a visual mapping for the existing
state branches already present in the pages.

### Inline links and helper rows

- `.auth-linkrow`
  - `margin-top: 20px`
  - 14px text in `var(--ink-700)`
- `.auth-linkrow a`
  - `font-weight: 600`
  - `color: var(--ink-900)`
  - underline with visible offset

## Route-by-Route Behavior

### `/auth/login`

- Remove the page-local left hero block and let the shared auth shell own the
  editorial column.
- Keep:
  - form logic
  - `/api/auth/login`
  - `/api/auth/resend-verification`
  - `/api/coke/me` profile hydration
  - safe `next` handling
  - recovery warning block and resend button
- Card content should use the existing `title`, `description`, field labels,
  status text, and bottom links.

### `/auth/register`

- Same shell behavior as login.
- Keep:
  - `/api/auth/register`
  - customer auth storage
  - redirect to `/auth/verify-email?email=...`
- Keep the existing card title/description and bottom sign-in link.

### `/auth/forgot-password`

- Move from the current centered slate card into the shared auth shell's right
  column.
- Keep the current single-card behavior and legacy endpoint:
  - `/api/coke/forgot-password`
- Do not opportunistically cut this route over to `/api/auth/forgot-password`
  in the same visual change.

### `/auth/reset-password`

- Same shell move as forgot-password.
- Keep:
  - token prefill from the query string
  - password mismatch client validation
  - `/api/coke/reset-password`
  - success redirect to `/auth/login`

### `/auth/verify-email`

- Keep the auto-verify-on-mount behavior when `token` and `email` are present.
- Keep the manual resend recovery flow when the token is missing, expired, or
  verification fails.
- In visual terms:
  - auto-verify state is an auth card with title + verifying description only
  - recovery state is the same card plus warning alert, email input, resend
    button, and resend status copy

### `/auth/claim`

- Move into the shared auth shell.
- Keep:
  - token prefill from query string
  - URL cleanup after prefill
  - password mismatch validation
  - `/api/auth/claim`
  - success redirect to `/channels/wechat-personal`

## Copy and i18n

Reuse the existing public and auth copy wherever possible.

### Required additive key

Add one shared shell field to `CustomerLayoutMessages`:

```ts
trustLines: string[];
```

Suggested values:

- `en`
  - `Encrypted in transit`
  - `We do not sell your data`
  - `Leave or reset access anytime`
- `zh`
  - `全程加密传输`
  - `不会售卖你的数据`
  - `可随时退出或重置访问`

### Existing copy to preserve

- `messages.publicShell.*` continues to drive the header
- `messages.customerLayout.*` drives the shared left panel
- each page keeps using its existing title, description, labels, errors,
  submit labels, and helper links

### Cleanup rule

`customerPages.login.hero*`, `customerPages.register.hero*`, and
`backToHomepage` may become unused after the redesign. Do not widen this PR
into a copy cleanup unless removing those keys is trivial and fully covered by
the touched tests. The visual redesign is the priority.

## File-Level Change Map

| File | Action | Reason |
|---|---|---|
| `gateway/packages/web/components/customer-auth-shell.tsx` | Create | Dedicated warm shell for auth only |
| `gateway/packages/web/app/(customer)/auth/layout.tsx` | Rewrite | Swap `CustomerShell` out for the new auth shell |
| `gateway/packages/web/components/coke-public-shell.tsx` | Modify | Support active auth CTA state |
| `gateway/packages/web/app/public-site.css` | Append | Add `.auth-*` styles and active header states |
| `gateway/packages/web/lib/i18n.ts` | Modify | Add `customerLayout.trustLines` and, only if necessary, matching type updates |
| `gateway/packages/web/app/(customer)/auth/login/page.tsx` | Rewrite markup only | Drop local hero block, emit shared auth-card classes |
| `gateway/packages/web/app/(customer)/auth/register/page.tsx` | Rewrite markup only | Same as login |
| `gateway/packages/web/app/(customer)/auth/forgot-password/page.tsx` | Rewrite markup only | Move into shared auth card system |
| `gateway/packages/web/app/(customer)/auth/reset-password/page.tsx` | Rewrite markup only | Move into shared auth card system |
| `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx` | Rewrite markup only | Warm recovery/auto-verify card states |
| `gateway/packages/web/app/(customer)/auth/claim/page.tsx` | Rewrite markup only | Warm claim card without logic change |
| `gateway/packages/web/components/customer-shell.tsx` | No change | Channels pages must keep current workspace shell |
| `gateway/packages/web/app/(customer)/channels/**` | No change | Explicitly out of scope |
| `gateway/packages/web/app/(coke-user)/**` | No change | Redirect wrappers and Coke-user flows remain untouched |

## Testing Strategy

### Shared shell tests

Update:

- `gateway/packages/web/components/coke-public-shell.test.tsx`
- `gateway/packages/web/app/(customer)/auth/layout.test.tsx`

Assertions to keep or add:

- `.coke-site` root exists
- public nav links still render in both locales
- `/auth/login` and `/auth/register` CTAs still render
- `EN` and `中文` locale toggles render
- the Chinese auth layout still exposes:
  - `统一管理客户登录与通道接入`
  - `处理登录、验证与个人微信接入`
  - `进入你的客户工作区`
- the auth layout still does not render Coke billing shell copy
- active CTA state is exposed on login/register routes

### Page tests

Update the page tests only where the old assertions depended on the page-local
left hero block:

- `app/(customer)/auth/login/page.test.tsx`
- `app/(customer)/auth/register/page.test.tsx`

The behavior assertions should stay the same:

- endpoints called
- redirects happen
- recovery states appear
- stored auth payloads are unchanged

The remaining auth page tests should only need light DOM assertion updates, if
any, because their logic does not change.

## Verification Gate

Future implementation should use the gateway-web verification set, starting
with the touched auth tests:

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

If the implementation modifies more shared web surfaces than listed above,
expand the test scope accordingly.

## Risks

- **Wrong shell touched:** editing `CustomerShell` would restyle `(customer)/channels`
  unintentionally. The redesign must use a new auth-only shell.
- **Logic drift during markup rewrite:** login/register/verify/claim have active
  auth-state logic. Keep handler bodies and API calls unchanged while swapping
  class names.
- **Scoped-style leakage:** every new selector must stay under `.coke-site`.
- **Copy cleanup creep:** removing old i18n keys is lower priority than
  landing the visual redesign cleanly.

## Rollout

Single PR. No feature flag required.

Revert path is simple because the redesign is constrained to:

- one new auth shell component
- auth layout/page markup
- additive `.coke-site` auth styles
- small shared-shell support changes

No migration, no backend dependency, and no data backfill is involved.
