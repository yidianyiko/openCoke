# Task: Kap Public Acquisition Basics

- Status: Implemented
- Owner: Codex
- Date: 2026-04-30

## Goal

Close the first public-site gaps from the Karpo comparison by adding trust pages and a clearer start path.

## Scope

- In scope:
  - Add public FAQ, Terms, and Privacy pages.
  - Replace placeholder footer legal links with real routes.
  - Add a concise domestic/global "how to start" section on the homepage.
  - Keep copy tied to currently live Kap surfaces: personal WeChat, WhatsApp, reminders, follow-up, account access, and Google Calendar import.
- Out of scope:
  - Conversation demo library.
  - SEO content library.
  - Analytics, pixels, and social-channel setup.
  - Runtime, bridge, gateway API, payment, or reminder behavior changes.

## Touched Surfaces

- gateway-web
- repo-os

## Acceptance Criteria

- `/faqs`, `/terms`, and `/privacy` render public Kap pages with real user-facing copy.
- Homepage footer links point to the real legal/FAQ routes instead of `#`.
- Homepage includes a clear path for domestic users and global WhatsApp users to start.
- Public-page tests cover the new routes and footer links.

## Verification

- Command: `pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx app/page.test.tsx app/faqs/page.test.tsx app/terms/page.test.tsx app/privacy/page.test.tsx`
- Expected evidence: gateway web tests pass. Current Vitest invocation ran the full suite: 38 files, 146 tests.
- Command: `zsh scripts/check`
- Expected evidence: repo-OS checks pass after the new task file.
- Command: `pnpm --dir gateway/packages/web exec eslint components/coke-homepage.tsx components/public-info-page.tsx app/faqs/page.tsx app/terms/page.tsx app/privacy/page.tsx app/faqs/page.test.tsx app/terms/page.test.tsx app/privacy/page.test.tsx app/page.test.tsx components/coke-homepage.test.tsx`
- Expected evidence: eslint passes for the files touched by this task.
- Command: `pnpm --dir gateway/packages/web build`
- Expected evidence: Next build succeeds and statically prerenders `/faqs`, `/terms`, and `/privacy`.

## Notes

- Existing unrelated reminder eval/evidence changes were present before this task and should not be modified here.
- Full `pnpm --dir gateway/packages/web lint` is currently blocked by pre-existing errors in `app/(customer)/handoff/calendar-import/page.tsx` and `components/locale-provider.tsx`; those files were not changed in this task.
