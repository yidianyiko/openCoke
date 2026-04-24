# Task: Deprecated Public Entrypoint Removal

- Status: Completed
- Owner: Codex
- Date: 2026-04-24

## Goal

Remove deprecated user-visible public entrypoints and their lingering references while keeping supported Kap routes and business APIs unchanged.

## Acceptance Criteria

- product code no longer presents retired public entrypoints as usable paths
- operational guidance no longer treats retired public entrypoints as supported
- explicit `404` regression checks for retired routes remain in place
- supported `/auth/*`, `/channels/*`, `/account/*`, and `/global` entrypoints are unaffected
- relevant web tests and build pass

## Verification

- Verified `pnpm --dir gateway/packages/web test` on 2026-04-24
- Verified `pnpm --dir gateway/packages/web build` on 2026-04-24
- Verified `bash scripts/test-deploy-compose-to-gcp.sh` on 2026-04-24
