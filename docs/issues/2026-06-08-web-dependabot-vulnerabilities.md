---
kind: active_issue
status: resolved
surface:
  - coke-web
  - repo-os
created_at: 2026-06-08
updated_at: 2026-06-08
---

# 2026-06-08 Web Dependabot Vulnerabilities

## What Happened

GitHub reported 31 open Dependabot alerts on the default branch for npm
dependencies under `web/`.

## Why It Matters

The affected packages are part of the web application build and test surface.
The alert set includes critical Vitest UI server exposure and multiple high
severity Next.js App Router, middleware/proxy, Server Components, and SSRF
advisories.

## Affected Surfaces

- `web/package.json`
- `web/pnpm-lock.yaml`
- `web/pnpm-workspace.yaml`
- `coke-web` verification routing

## Evidence

- `gh api --paginate 'repos/yidianyiko/openCoke/dependabot/alerts?state=open'`
  returned 31 open npm alerts across `next`, `vitest`, and transitive
  `postcss`.
- `cd web && pnpm audit --audit-level low --json` reproduced 16 deduplicated
  advisories: 1 critical, 8 high, 5 moderate, and 2 low.
- `uvx pip-audit -r requirements.txt --format json` returned no known Python
  vulnerabilities.
- Final evidence is recorded in
  `artifacts/evidence/web-dependabot-vulnerabilities/2026-06-08-verification.md`.

## Current Status

- Resolved locally in fix commit `2201426d`.

## Resolution

- Updated `next` and `eslint-config-next` from `16.2.1` to `16.2.7`.
- Updated `vitest` from `3.2.4` to `4.1.8`.
- Added a PNPM 11 workspace override so Next's transitive `postcss` resolves
  to patched `8.5.15`.
- Downgraded `eslint` from `10.4.1` to supported `9.39.4` because the Next
  lint plugin graph does not support ESLint 10.
- Fix commit: `2201426d fix: update vulnerable web dependencies`.

## Verification

- `cd web && pnpm audit --audit-level low --json`: zero vulnerabilities.
- `cd web && pnpm peers check`: no peer dependency issues.
- `zsh scripts/verify-surface clean-rebuild-web repo-os-docs`: passed.
- `uvx pip-audit -r requirements.txt --format json`: no known Python
  vulnerabilities.
- `pnpm lint`: not part of the suggested surface verification and still fails
  on existing `react-hooks/set-state-in-effect` findings in customer pages.
  This remediation did not weaken lint rules or refactor unrelated UI code.
