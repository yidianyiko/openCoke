# Neutral Auth Register/Verify Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the customer registration and email verification flow by cutting the web auth pages over to the neutral `/api/auth/*` endpoints.

**Architecture:** Keep the neutral customer-auth API as the source of truth for register and verify flows while leaving `/api/coke/login` temporarily in place for compatibility profile hydration. Limit changes to auth page callers and their tests so the blast radius stays inside `gateway-web`.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest

---

### Task 1: Lock in the broken endpoint expectations as failing tests

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`

- [ ] **Step 1: Update the page tests to expect `/api/auth/*` instead of paused Coke compatibility endpoints**
- [ ] **Step 2: Run the targeted auth page tests and confirm they fail on old endpoint assertions**
- [ ] **Step 3: Keep redirect/storage assertions unchanged so only the API contract changes**

### Task 2: Cut the register and verify pages to neutral customer-auth endpoints

**Files:**
- Modify: `gateway/packages/web/app/(customer)/auth/register/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/verify-email/page.tsx`
- Modify: `gateway/packages/web/app/(customer)/auth/login/page.tsx`

- [ ] **Step 1: Switch register submit to `/api/auth/register`**
- [ ] **Step 2: Switch verify-email submit to `/api/auth/verify-email`**
- [ ] **Step 3: Switch resend-verification calls to `/api/auth/resend-verification`**
- [ ] **Step 4: Preserve existing auth storage and redirect behavior**

### Task 3: Re-run focused verification

**Files:**
- Test: `gateway/packages/web/app/(customer)/auth/register/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/login/page.test.tsx`
- Test: `gateway/packages/web/app/(customer)/auth/verify-email/page.test.tsx`

- [ ] **Step 1: Run the targeted auth page suite**
- [ ] **Step 2: Confirm all endpoint assertions now pass**
- [ ] **Step 3: Review the diff to ensure no paused Coke register/verify API callers remain in the touched pages**
