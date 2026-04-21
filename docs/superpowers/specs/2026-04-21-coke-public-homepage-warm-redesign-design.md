# Coke Public Homepage — Warm Editorial Redesign (Design)

**Status:** approved for implementation
**Date:** 2026-04-21
**Surfaces:** `gateway/packages/web` (public homepage only)
**Reference bundle:** `/tmp/design_bundle/coke-ai-design-system/project/ui_kits/public_site/`

## Goal

Replace the current dark-navy + teal "AI slop" visuals of the public Coke homepage and its shared public shell with the warm cream / espresso-ink editorial design system shipped in the reference bundle. The redesign is visual-only: all existing routes, auth flows, admin/customer shells, bilingual copy, and locale bootstrap behavior stay intact.

## Non-Goals

- No change to admin dashboard (`app/(admin)`) or customer shell (`app/(customer)`) styling; Tailwind tokens in `globals.css` stay untouched.
- No change to auth/Coke-user pages styling (`app/(coke-user)/**`).
- No new i18n framework, no new routing, no new backend calls.
- No ship of the reference-bundle "tweaks" dev panel.
- No new CMS or content pipeline — copy continues to come from `lib/i18n.ts`.

## Scope

Redesigns visible to a user hitting `/`:

1. `components/coke-public-shell.tsx` — header with warm glass blur, serif brand mark + claw-orange dot, editorial nav, pill CTAs, warm footer.
2. `components/coke-homepage.tsx` — split into the five reference sections (Hero + ChatPeek, Platforms, Features, Architecture, Contact/Footer) using warm-palette class names from the scoped stylesheet.
3. `app/layout.tsx` — swap the dark radial-gradient `locale-splash` for a warm cream splash that matches the new palette; wire `next/font` for Fraunces + Inter + JetBrains Mono so the scoped CSS variables `--font-fraunces`, `--font-inter`, `--font-mono` get real values.
4. `app/public-site.css` — already authored; imported once by `layout.tsx`. All selectors stay scoped under `.coke-site` so admin/customer styling is not disturbed.
5. `components/coke-public-shell.test.tsx` — rewrite visual assertions to match new text/class surface while still guarding bilingual labels and auth links.

No other files are modified.

## Design System Summary

Pulled from `/tmp/design_bundle/coke-ai-design-system/project/colors_and_type.css` and `styles.css`. All tokens live inside `.coke-site` scope in `app/public-site.css`.

- **Palette:** warm cream background (`--cream-100 #F6F1E8`), espresso ink text (`--ink-900 #1B1410`), brand claw orange (`--claw-500 #E8693C`, unchanged from current brand token), quieter teal + olive accents.
- **Typography:**
  - `--font-display` → Fraunces (variable serif, used for hero/h1..h4 with `font-variation-settings: 'SOFT' 30..80, 'opsz' 120..144`).
  - `--font-body` → Inter with `font-feature-settings: 'ss01','cv11'`.
  - `--font-mono` → JetBrains Mono (used for section numbers, meta text).
- **Layout rhythm:** 8px spacing scale, `--max-content: 1180px`, `--gutter: 32px`.
- **Signature moves:** warm radial glow at top of page, italic serif brand word + orange dot, inverted espresso-ink Architecture section carved out as a rounded card, large ghosted "coke" watermark behind the Contact form.

## Page Structure

All sections are rendered inside `<div className="coke-site">` provided by the shell. Sections use the reference class names verbatim so the pre-written scoped CSS applies as-is.

### 1. `CokePublicShell`

```
<div class="coke-site">
  <header class="site-header">
    <div class="site-header__inner">
      <a class="brand">
        <span class="brand__mark">coke</span>
        <span class="brand__dot" aria-hidden="true" />
      </a>
      <nav class="site-nav">…links from messages.publicShell.nav…</nav>
      <div class="site-header__actions">
        <LocaleSwitch />            // re-styled: uses .locale-switch + .locale-switch__opt
        <Link class="header-signin" href="/auth/login">…</Link>
        <Link class="header-cta" href="/auth/register">… <ArrowRight /></Link>
      </div>
    </div>
  </header>
  <main>{children}</main>
  <Footer />                        // new subcomponent in coke-homepage.tsx
</div>
```

Notes:
- The locale bootstrap / splash path does not change; only the splash's markup/styling in `layout.tsx` is swapped for a cream surface.
- The shell no longer wraps `<main>` in the dark-navy gradient class list. Background glow comes from the scoped `.coke-site` radial gradient.
- `LocaleSwitch` is rebuilt as a two-button pill (EN / 中) that mirrors the reference `.locale-switch__opt[aria-pressed="true"]` pattern. It continues to call `setLocale` from `useLocale()`.

### 2. Hero (`section.hero`)

- `.hero__eyebrow` pill with `.hero__eyebrow-dot`.
- `.hero__title` uses reference three-line composition: plain, italic `.hero__title-em` (claw-orange), plain. Bilingual mapping:
  - EN: `An AI partner` / *that grows* / `with you.`
  - ZH: `会随着使用` / *不断进化的* / `AI 助手。`
- `.hero__lede` (single paragraph under title).
- Buttons: `.btn .btn--primary` → `/auth/register` (primary CTA), `.btn .btn--link` → `/auth/login` (secondary).
- `.hero__foot`: small meta strip ("Six platforms · 99.9% uptime · <100ms latency" / "六个平台 · 99.9% 可用性 · <100ms 响应").
- Right column: static `ChatPeek` (no JS state needed, purely decorative). The thread text stays in the component file (short, bilingual, hard-coded per reference) because it is a visual illustration, not product content. This intentionally does not go through `lib/i18n.ts`.

### 3. Platforms (`section#platforms`)

- `.section__head` with numbered eyebrow `01 · PLATFORMS`.
- `.platforms` grid (3 columns desktop → 2 → 1).
- Each `.platform` card renders platform name + muted note + arrow icon. Six platforms hardcoded in component (they are a fixture, not copy that changes: WeChat / Telegram / DingTalk / Lark / Slack / Discord). Localized subtitle note uses a small local bilingual table.

### 4. Features (`section#features`)

- `.section__head` numbered `02 · FEATURES`.
- `.features` 2-col grid. Each `.feature` card: number badge, kicker, icon, display-serif title, body.
- Icons are React components from `lucide-react` (`CalendarCheck`, `Route`, `Activity`, `Workflow`). No `data-lucide` attribute usage — we drop the runtime icon-font pattern of the reference HTML.

### 5. Architecture (`section#architecture.section--invert`)

- Inverted espresso card with rounded corners, brand radial glow.
- Left column: eyebrow `03 · ARCHITECTURE`, serif title, lede, static diagram with three stacked `.arch__layer` rows and two `.arch__line` separators. Diagram chips are decorative only.
- Right column: 4 `.arch__point` list items each numbered `01..04`.

### 6. Contact + Footer (`section#contact`)

- `.contact` block with bilingual eyebrow `04 · BETA`, serif title, body, email input inside `.contact__form`.
- Form behavior: the reference shows a submitted state swap. We implement this with `useState`; no network call. This is acceptable because the goal is visual parity and the form already matches the existing homepage's register funnel (we swap the submitted view back for a toast in a follow-up; not in scope).
- Behind the form, the giant `.contact__mark` watermark ("coke" + `.contact__mark-dot`).
- Footer (`<Footer />`) reproduces `.site-footer` with brand mark, 3 columns of links, bottom bar. Links are static hrefs to existing routes where they exist (`/auth/login`, `/auth/register`, `/`) and `#` placeholders where no destination exists yet.

## Typography + Font Loading

In `app/layout.tsx`:

```ts
import { Fraunces, Inter, JetBrains_Mono } from 'next/font/google';

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  axes: ['SOFT', 'opsz'],
});
const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });
const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' });
```

The three `variable` CSS custom properties are applied to `<body className={`${fraunces.variable} ${inter.variable} ${jetbrains.variable}`}>` so the scoped `.coke-site` rules in `public-site.css` can resolve `var(--font-fraunces, …)` etc. This does not affect admin/customer shells because they don't use those variables.

`globals.css` line `--font-sans: Inter, system-ui, sans-serif;` is kept untouched; admin pages continue to resolve Inter through the system stack.

## Styling Boundary (Isolation Guarantee)

- `app/public-site.css` is imported in `layout.tsx` (once). Every non-root selector is prefixed `.coke-site …`.
- The public shell is the only component that sets `className="coke-site"`. Admin and customer shells never opt in, so warm tokens never leak.
- Tailwind layers (`@import "tailwindcss"` in `globals.css`) still compile normally. Tailwind utilities are not used on the public homepage — we use the scoped CSS classes — but Tailwind is still available for auth pages, admin, and customer shells.

## Locale Splash

`layout.tsx` currently renders a dark-navy gradient splash. Replace with:

```tsx
<div id="locale-splash" className="coke-site-splash">
  <div className="coke-site-splash__card">
    <span className="coke-site-splash__mark">coke</span>
    <span className="coke-site-splash__dot" aria-hidden="true" />
    <p className="coke-site-splash__body">Preparing your workspace…</p>
  </div>
</div>
```

Splash-only styles go at the bottom of `public-site.css` (still under the `.coke-site-splash` scope, not under `.coke-site`, so it is visible before the shell mounts). The `LocaleProvider` effect that calls `document.getElementById('locale-splash')?.remove()` continues to work unchanged.

## Component Diff Summary

| File | Action | Reason |
|---|---|---|
| `components/coke-public-shell.tsx` | Rewrite markup + classes | Warm header + footer-less shell. |
| `components/coke-homepage.tsx` | Rewrite into 5 sections + local `ChatPeek`, `Footer` | Editorial layout per reference. |
| `components/locale-switch.tsx` | Restyle to `.locale-switch` + `.locale-switch__opt` pill | Matches new header treatment. |
| `components/coke-public-shell.test.tsx` | Rewrite assertions | Text-level bilingual guard stays; class-name checks replaced. |
| `app/layout.tsx` | Wire next/font, replace splash | Font vars + warm splash. |
| `app/public-site.css` | Append splash styles | Already authored; add splash-only block. |
| `app/globals.css` | Untouched | Admin/customer Tailwind unaffected. |
| `lib/i18n.ts` | Minor additive keys only | `hero.titleItalicMiddle` + `hero.foot` + `contact.note` + `contact.thanks` + `footerColumns` (see below). |

### i18n additions

Add the following keys to both `en` and `zh` (hero three-part title, hero footline, contact form supporting copy, footer column labels). Existing `homepage.*` keys are preserved; unused ones (`stats`, `spotlight`) stay in the file untouched since future variants may want them — not removed to avoid pulling more than necessary.

```
homepage.hero.titleLine1          // "An AI partner" / "会随着使用"
homepage.hero.titleItalicMiddle   // "that grows" / "不断进化的"
homepage.hero.titleLine3          // "with you." / "AI 助手。"
homepage.hero.foot                // "Six platforms · 99.9% uptime · <100ms latency"
homepage.contact.placeholder
homepage.contact.note
homepage.contact.thanks
homepage.footer.productHeading
homepage.footer.accountHeading
homepage.footer.companyHeading
homepage.footer.copyright         // "© 2026 Coke AI"
homepage.footer.tagline           // "Built to grow with you." / "与你一起慢慢变好。"
```

Corresponding TypeScript shape additions in `LocaleMessages['homepage']`. All new keys must exist in both locales. No behavior gets keyed on string content; tests assert on the rendered value.

## Testing Strategy

- Rewrite `coke-public-shell.test.tsx` to assert:
  - `<div class="coke-site">` root wrapper rendered.
  - English and Chinese nav labels appear (Platforms/平台, Features/功能, Architecture/架构, Contact/联系).
  - `href="/auth/login"` and `href="/auth/register"` links both render.
  - Brand mark `coke` renders.
  - EN locale shows `An AI Partner That Grows With You` tagline **only** if the shell surfaces it (if we drop the tagline in favor of `.brand` mark, update the test to not assert it; see Open Questions → resolved: we drop brand tagline because the italic serif mark is the tagline now).
  - Locale switch renders both `EN` and `中` toggles.
- Add a light `coke-homepage.test.tsx` that renders the page with `LocaleProvider initialLocale="en"` and asserts each section id is present (`#platforms`, `#features`, `#architecture`, `#contact`) and the italic middle hero word renders in an `<em>`.
- Existing `page.test.tsx`, `layout.metadata.test.ts`, and `dashboard-removal.test.ts` are unaffected by visual changes; they should continue to pass.

## Verification Gate

Per `docs/fitness/coke-verification-matrix.md` (web frontend surface):

```bash
cd gateway/packages/web
pnpm test -- --run components/coke-public-shell.test.tsx components/coke-homepage.test.tsx app/layout.metadata.test.ts app/page.test.tsx app/dashboard-removal.test.ts
pnpm lint
pnpm build
```

(Use `npm` if workspace resolves that way; command name is the concern of the plan, not the spec.) No Python test suite is affected.

## Rollout

Single-PR change. The design is a visual-only swap of three TSX files + one layout + one stylesheet + one i18n additive patch. There is no feature flag because the admin and customer shells are isolated by Tailwind-only usage vs. `.coke-site`-scoped CSS. If revert is needed, it's one commit.

## Risks

- **Font variation axes:** `Fraunces` needs `axes: ['SOFT', 'opsz']`. If `next/font` fails to include `SOFT`, italic hero word still renders — it just won't have the extra soft weight. Not a blocker.
- **Tailwind vs scoped CSS drift:** two styling systems coexist. Mitigation: scoped selectors under `.coke-site` prevent leaks; admin pages never set that class.
- **Locale switch footprint change:** The button now has two pressed states instead of a single toggle. Existing `LocaleProvider` tests (`locale-provider.test.tsx`) only exercise `setLocale`, not the switch's markup, so they stay green.

## Out of Scope (Follow-ups)

- Replacing the decorative `ChatPeek` thread with a lightweight motion/marquee.
- Wiring the Contact form to Resend (feature flag).
- Animating the hero "that grows" italic word on scroll.
- Migrating the reference "tweaks" dev panel (intentionally not shipped).
