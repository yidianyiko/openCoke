# Kap Koala Mascot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Kap's current letter-based mascot and outward-facing brand icons with a hand-drawn sticker-style koala across the homepage and brand entrypoints.

**Architecture:** Keep the current route and shell structure, but swap letter-only mascot treatments for two shared bitmap assets: a large homepage koala illustration and a small koala badge for brand/icon surfaces. Wire both assets through the existing Next.js public asset pipeline and update the shared shells so every outward-facing brand entrypoint uses the badge consistently.

**Tech Stack:** Next.js app router, React client components, TypeScript, Vitest, CSS in `gateway/packages/web/app/public-site.css`, raster mascot assets in `gateway/packages/web/public`

---

## Inputs

- Related task: `tasks/2026-04-24-kap-koala-mascot.md`
- Related spec: `docs/superpowers/specs/2026-04-24-kap-koala-mascot-design.md`

## Touched Surfaces

- gateway-web

## Execution Notes

- Work in the existing workspace because the user requested direct execution.
- Use TDD for component behavior changes before editing production code.
- Save generated final mascot assets into `gateway/packages/web/public/` rather than leaving them under the default image generation output path.

### Task 1: Capture The Koala Brand Contract In Tests

**Files:**
- Modify: `gateway/packages/web/components/coke-homepage.test.tsx`
- Modify: `gateway/packages/web/components/coke-public-shell.test.tsx`
- Modify: `gateway/packages/web/components/global-homepage.test.tsx`
- Modify: `gateway/packages/web/app/layout.metadata.test.ts`

- [ ] **Step 1: Write the failing homepage mascot test**

```tsx
expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
expect(container.querySelector('.hero-mascot-figure')).toBeTruthy();
```

- [ ] **Step 2: Write the failing shared-brand badge tests**

```tsx
expect(container.querySelector('img[alt="Kap koala badge"]')).toBeTruthy();
```

- [ ] **Step 3: Run the targeted tests and verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/coke-public-shell.test.tsx components/global-homepage.test.tsx app/layout.metadata.test.ts
```

Expected: FAIL because the current UI still renders wordmark-only branding and the old `K` / `AI` homepage mascot blocks.

### Task 2: Generate And Install The Koala Assets

**Files:**
- Create: `gateway/packages/web/public/kap-koala-hero.png`
- Create: `gateway/packages/web/public/kap-koala-badge.png`
- Modify: `gateway/packages/web/public/logo.png`
- Modify: `gateway/packages/web/app/favicon.ico`

- [ ] **Step 1: Generate the hero koala asset**

Prompt requirements:

```text
Use case: illustration-story
Asset type: landing page hero mascot
Primary request: hand-drawn sticker-style koala mascot for the Kap homepage
Style/medium: warm editorial illustration with a paper sticker feel
Composition/framing: single koala character, transparent background, readable at homepage hero scale
Color palette: warm grey fur, cream muzzle and belly, charcoal nose, subtle olive and burnt-orange accents
Constraints: no text, no letters, no clothing logo, friendly calm expression, transparent background
```

- [ ] **Step 2: Generate the badge koala asset**

Prompt requirements:

```text
Use case: logo-brand
Asset type: site badge and favicon source
Primary request: simplified hand-drawn sticker-style koala head matching the homepage mascot
Composition/framing: close head badge, centered, transparent background, readable at very small sizes
Constraints: no text, no letters, strong silhouette, soft but clear outline
```

- [ ] **Step 3: Copy the selected outputs into the workspace**

Run:

```bash
cp <generated-hero> gateway/packages/web/public/kap-koala-hero.png
cp <generated-badge> gateway/packages/web/public/kap-koala-badge.png
cp gateway/packages/web/public/kap-koala-badge.png gateway/packages/web/public/logo.png
```

- [ ] **Step 4: Regenerate the favicon from the badge asset**

Run:

```bash
magick gateway/packages/web/public/kap-koala-badge.png -background none -define icon:auto-resize=16,32,48,64 gateway/packages/web/app/favicon.ico
```

Expected: `favicon.ico` exists and is refreshed from the koala badge.

### Task 3: Wire Koala Assets Into Homepage And Brand Entrypoints

**Files:**
- Modify: `gateway/packages/web/components/coke-homepage.tsx`
- Modify: `gateway/packages/web/components/coke-public-shell.tsx`
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Modify: `gateway/packages/web/components/global-homepage.tsx`
- Modify: `gateway/packages/web/app/layout.tsx`
- Modify: `gateway/packages/web/app/public-site.css`

- [ ] **Step 1: Replace the homepage mascot blocks with the hero image**

```tsx
<div className="hero-mascot-figure">
  <img src="/kap-koala-hero.png" alt="Kap koala mascot" />
</div>
```

- [ ] **Step 2: Update shared brand anchors to use the badge image plus wordmark**

```tsx
<Link href="/" className="brand" aria-label="Kap AI">
  <img src="/kap-koala-badge.png" alt="Kap koala badge" className="brand__icon" />
  <span className="brand__mark">kap</span>
</Link>
```

```tsx
<a href="/global" className="global-brand" aria-label="Kap global">
  <img src="/kap-koala-badge.png" alt="Kap koala badge" className="global-brand__icon" />
  <span className="global-brand__wordmark">kap</span>
</a>
```

- [ ] **Step 3: Update the splash card to use the badge asset**

```tsx
<img src="/kap-koala-badge.png" alt="Kap koala badge" className="coke-site-splash__icon" />
```

- [ ] **Step 4: Add CSS for the badge and hero mascot layouts**

```css
.coke-site .brand,
.global-site .global-brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.coke-site .brand__icon,
.global-site .global-brand__icon,
.coke-site-splash__icon {
  width: 40px;
  height: 40px;
  object-fit: contain;
}

.coke-site .hero-mascot-figure img {
  width: min(100%, 280px);
  height: auto;
  object-fit: contain;
}
```

### Task 4: Verify The Koala Rollout

**Files:**
- Test: `gateway/packages/web/components/coke-homepage.test.tsx`
- Test: `gateway/packages/web/components/coke-public-shell.test.tsx`
- Test: `gateway/packages/web/components/global-homepage.test.tsx`
- Test: `gateway/packages/web/app/layout.metadata.test.ts`

- [ ] **Step 1: Run targeted koala tests**

Run:

```bash
pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx components/coke-public-shell.test.tsx components/global-homepage.test.tsx app/layout.metadata.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run the full gateway web test suite**

Run:

```bash
pnpm --dir gateway/packages/web test
```

Expected: PASS.

- [ ] **Step 3: Run the production build**

Run:

```bash
pnpm --dir gateway/packages/web build
```

Expected: PASS with static route generation for the outward-facing pages.
