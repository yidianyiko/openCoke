# Task: Kap User Surface Priority

- Status: In Progress
- Owner: Codex
- Date: 2026-04-24

## Goal

Correct the Kap redesign so the user-facing auth, account, and channel surfaces become the true visual main stage, and `/global` matches the homepage family instead of using a separate dark style.

## Scope

- In scope:
  - `/auth/*` shared shell presentation
  - `/channels/*` shared shell presentation
  - `/account/*` shared shell presentation
  - `/global` visual language
  - targeted tests for the revised contract
- Out of scope:
  - route changes
  - business logic changes
  - admin redesign

## Acceptance Criteria

- `/auth/*` renders a stronger homepage-family branded stage, not just a light shell
- `/channels/*` and `/account/*` render as the primary product stage with stronger spotlight/workspace framing
- `/global` uses the same warm Kap homepage family instead of the separate dark theme
- WhatsApp CTA behavior on `/global` remains intact
- targeted tests, full web tests, and build all pass
