# Neutral Auth Login Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove active repository reliance on `/api/coke/login` by cutting web and smoke callers over to `/api/auth/login`.

**Architecture:** Authenticate through neutral customer auth, then reuse the returned customer token against existing Coke compatibility reads such as `/api/coke/me`, `/api/coke/subscription`, and `/api/coke/checkout`. Pause `/api/coke/login` so legacy API compatibility no longer sits on the login path.

**Tech Stack:** Next.js 16, React 19, TypeScript, Hono, Vitest

---

### Task 1: Lock in the new caller contract as failing tests

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Modify: `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- Modify: `gateway/packages/api/src/scripts/stripe-e2e-smoke.test.ts`

- [ ] **Step 1: Update the login page tests to expect `/api/auth/login` plus `/api/coke/me` hydration**
- [ ] **Step 2: Update Coke auth route tests to expect `/api/coke/login` to return a paused response**
- [ ] **Step 3: Add or update smoke helper tests to lock in neutral login request behavior**
- [ ] **Step 4: Run the focused web and API tests and confirm the new expectations fail before implementation**

### Task 2: Cut callers over to neutral login and pause the legacy endpoint

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.tsx`
- Modify: `gateway/packages/api/src/routes/coke-auth-routes.ts`
- Modify: `gateway/packages/api/src/scripts/stripe-e2e-smoke.ts`

- [ ] **Step 1: Switch the login page submit path to `/api/auth/login`**
- [ ] **Step 2: Hydrate the compatibility profile from `/api/coke/me` using the customer token**
- [ ] **Step 3: Switch the Stripe smoke helper to `/api/auth/login`**
- [ ] **Step 4: Replace `/api/coke/login` with the standard paused compatibility response**

### Task 3: Re-run focused verification

**Files:**
- Test: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Test: `gateway/packages/api/src/routes/coke-auth-routes.test.ts`
- Test: `gateway/packages/api/src/scripts/stripe-e2e-smoke.test.ts`

- [ ] **Step 1: Run the targeted login page test**
- [ ] **Step 2: Run the focused API tests for paused login and smoke helpers**
- [ ] **Step 3: Review the diff to ensure no touched repo caller still posts to `/api/coke/login`**
