# Kap User Surface Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/auth/*`, `/channels/*`, and `/account/*` feel like the true Kap product stage, and bring `/global` into the same warm homepage visual family.

**Architecture:** Keep the same route graph and page logic, but strengthen the shared auth and customer shells with mascot-backed spotlight structures and more deliberate content-stage framing. Rework `/global` to use the same warm sticker-card language as `/` while preserving its WhatsApp-only CTA behavior.

**Tech Stack:** Next.js app router, React client components, TypeScript, Vitest, CSS in `gateway/packages/web/app/public-site.css`

---

## Inputs

- Related task: `tasks/2026-04-24-kap-user-surface-priority.md`
- Related spec: `docs/superpowers/specs/2026-04-24-kap-user-surface-priority-design.md`

## Touched Surfaces

- gateway-web

### Task 1: Lock The New User-Surface Contract In Tests

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/layout.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/channels/layout.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/account/layout.test.tsx`
- Modify: `gateway/packages/web/components/global-homepage.test.tsx`

- [ ] **Step 1: Add failing auth-shell assertions**

```tsx
expect(container.querySelector('.auth-hero__spotlight')).toBeTruthy();
expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
expect(container.querySelector('.auth-shell__stage')).toBeTruthy();
```

- [ ] **Step 2: Add failing customer-shell assertions**

```tsx
expect(container.querySelector('.customer-shell__spotlight')).toBeTruthy();
expect(container.querySelector('.customer-shell__workspace')).toBeTruthy();
expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
```

- [ ] **Step 3: Add failing `/global` assertions**

```tsx
expect(container.querySelector('.global-site.global-site--kap')).toBeTruthy();
expect(container.querySelector('.global-ticker')).toBeTruthy();
expect(container.querySelector('img[alt="Kap koala mascot"]')).toBeTruthy();
```

- [ ] **Step 4: Run targeted tests and verify they fail**

Run:

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/auth/layout.test.tsx' 'app/(customer)/channels/layout.test.tsx' 'app/(customer)/account/layout.test.tsx' components/global-homepage.test.tsx
```

Expected: FAIL because the stronger spotlight/workspace structures and warm global markers do not exist yet.

### Task 2: Upgrade Auth And Customer Shells Into The Main Product Stage

**Files:**
- Modify: `gateway/packages/web/components/customer-auth-shell.tsx`
- Modify: `gateway/packages/web/components/customer-shell.tsx`
- Modify: `gateway/packages/web/app/public-site.css`

- [ ] **Step 1: Add spotlight structure and mascot to the auth shell**
- [ ] **Step 2: Add spotlight structure, mascot, and workspace wrapper to the customer shell**
- [ ] **Step 3: Add matching warm-stage CSS for auth and customer shells**
- [ ] **Step 4: Run the shell tests and verify they pass**

### Task 3: Rework `/global` Onto The Homepage Family

**Files:**
- Modify: `gateway/packages/web/components/global-homepage.tsx`
- Modify: `gateway/packages/web/app/public-site.css`

- [ ] **Step 1: Add warm-page marker class, mascot, and ticker structure to `/global`**
- [ ] **Step 2: Replace the independent dark look with homepage-family warm card and sticker styling**
- [ ] **Step 3: Keep all primary CTAs pointed at WhatsApp**
- [ ] **Step 4: Run the `/global` test and verify it passes**

### Task 4: Verify The Full Follow-Up

**Files:**
- Test: `gateway/packages/web/app/(customer)/auth/layout.test.tsx`
- Test: `gateway/packages/web/app/(customer)/channels/layout.test.tsx`
- Test: `gateway/packages/web/app/(customer)/account/layout.test.tsx`
- Test: `gateway/packages/web/components/global-homepage.test.tsx`

- [ ] **Step 1: Run the targeted test set**

```bash
pnpm --dir gateway/packages/web test -- 'app/(customer)/auth/layout.test.tsx' 'app/(customer)/channels/layout.test.tsx' 'app/(customer)/account/layout.test.tsx' components/global-homepage.test.tsx
```

- [ ] **Step 2: Run the full web test suite**

```bash
pnpm --dir gateway/packages/web test
```

- [ ] **Step 3: Run the production build**

```bash
pnpm --dir gateway/packages/web build
```
