# Task: Kap Demo Library

- Status: Implemented
- Owner: Codex
- Date: 2026-04-30

## Goal

Add a public demo library so prospects can see concrete Kap supervision conversations before signing up.

## Scope

- In scope:
  - Add a public `/demos` page with real conversation examples for currently live Kap surfaces.
  - Add a compact homepage section that links to the demo library.
  - Add public navigation/footer labels for demos.
  - Keep demos tied to reminders, follow-up, WhatsApp, personal WeChat, account access, and Google Calendar import.
- Out of scope:
  - User-generated demo content.
  - Analytics or social tracking.
  - Runtime, bridge, reminder, channel, or payment behavior changes.

## Touched Surfaces

- gateway-web
- repo-os

## Acceptance Criteria

- `/demos` renders a public Kap demo library with at least six concrete conversation examples.
- Homepage includes a demo preview section and links to `/demos`.
- Public nav and footer expose `/demos`.
- Tests cover the new route, homepage entry, and shell nav label.

## Verification

- Command: `pnpm --dir gateway/packages/web test -- app/demos/page.test.tsx components/coke-homepage.test.tsx app/page.test.tsx components/coke-public-shell.test.tsx lib/i18n.test.ts`
- Expected evidence: gateway web tests pass. Current Vitest invocation ran the full suite: 39 files, 147 tests.
- Command: `pnpm --dir gateway/packages/web exec eslint components/coke-homepage.tsx components/coke-public-shell.test.tsx app/demos/page.tsx app/demos/page.test.tsx lib/i18n.ts`
- Expected evidence: eslint passes for touched files.
- Command: `pnpm --dir gateway/packages/web build`
- Expected evidence: Next build succeeds and statically prerenders `/demos`.
- Command: `zsh scripts/check`
- Expected evidence: repo-OS checks pass after the new task file.

## Notes

- Implemented in an isolated worktree from pushed `origin/main` to avoid unrelated reminder work in the primary checkout.
