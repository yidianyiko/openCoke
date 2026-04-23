# Task: Kap Public UI Redesign

- Status: Completed
- Owner: Codex
- Date: 2026-04-23

## Goal

Rebrand the outward-facing gateway web experience from `coke` to `kap` and restyle it around the `tasks/index (1)(1).html` visual language without changing routes or runtime behavior.

## Scope

- In scope:
  - Public homepage at `/`
  - Global marketing page at `/global`
  - Public auth surfaces under `/auth/*`
  - Customer-facing account and channel surfaces under `/account/*` and `/channels/*`
  - Shared public shell, outward-facing metadata, and outward-facing brand copy in gateway web
- Out of scope:
  - Admin pages under `/admin/*`
  - API routes, storage keys, cookies, route paths, and backend behavior
  - Internal codebase renaming outside outward-facing web UI needs

## Touched Surfaces

- gateway-web

## Acceptance Criteria

- The `/` homepage uses the `index (1)(1).html` visual direction and a similar marketing-page information architecture while preserving Coke's existing functional entry points and locale switch.
- Outward-facing gateway web pages show `kap` branding instead of `coke` where the user sees the brand.
- `/global`, `/auth/*`, `/account/*`, and `/channels/*` share the same Kap visual system instead of mixing the current homepage, auth, and customer styles.
- Existing flows still work: locale switch, login/register links, account subscription, and personal WeChat channel setup.
- Admin pages remain behaviorally unchanged.

## Verification

- Command: `pnpm --dir gateway/packages/web test`
- Evidence: `36` test files passed, `135` tests passed on 2026-04-23 after the Kap homepage, customer shell, subscription, and calendar-import redesign landed.
- Command: `pnpm --dir gateway/packages/web build`
- Evidence: Next.js production build completed successfully on 2026-04-23, including TypeScript and static page generation for `/`, `/global`, `/auth/*`, `/channels/*`, and `/account/*`.

## Notes

- The reference visual is `tasks/index (1)(1).html`.
- The user explicitly approved:
  - homepage structure should follow the reference style
  - bilingual locale switching must remain
  - `coke` should be rebranded to `kap` on outward-facing pages
  - implementation should use subagent-driven execution
- Attempted isolated worktree setup at `.worktrees/kap-public-ui-redesign` per repo workflow.
- That worktree cannot fully initialize because the `gateway` submodule reference on `main` currently points at commit `d4d909bc352ec16c14160eb389de9b4973595407`, which the remote no longer serves.
- Implementation continues in the current workspace with targeted verification and subagent isolation instead of a runnable clean worktree.
- Final implementation kept routes and runtime behavior unchanged while migrating the public homepage, global page, auth shell, customer shell, subscription page, calendar-import page, and outward-facing brand copy to the Kap visual system.
