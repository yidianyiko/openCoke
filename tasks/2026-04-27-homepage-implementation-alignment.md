# Task: Homepage Implementation Alignment

- Status: Complete
- Owner: Codex
- Date: 2026-04-27

## Goal

Align the public homepage copy with the product capabilities currently shipped
in this repository.

## Scope

- In scope:
- Homepage and root metadata copy
- Homepage component tests and root page/metadata tests
- Out of scope:
- Visual redesign
- Runtime behavior changes
- Gateway API, bridge, or worker behavior changes

## Touched Surfaces

- gateway-web
- repo-os

## Acceptance Criteria

- Homepage lead copy describes Kap as a supervision/follow-up product, not a
  generic AI assistant.
- Homepage claims only currently implemented public/product surfaces:
  personal WeChat, global WhatsApp, visible reminders/follow-up, subscription
  access, and Google Calendar import.
- Homepage no longer claims broad platform coverage, uptime, latency, or
  drafting as a primary product promise.
- Existing public routes and CTAs remain unchanged.

## Verification

- Command: `pnpm --dir gateway/packages/web test -- components/coke-homepage.test.tsx app/page.test.tsx app/layout.metadata.test.ts`
- Expected evidence: targeted homepage and metadata tests pass.
- Command: `pnpm --dir gateway/packages/web test`
- Expected evidence: full web Vitest suite passes.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and task routing checks pass.

## Notes

The implementation audit found the current homepage copy was broader than the
implemented product: it presented Kap as a general AI partner with broad
platform and performance claims, while the shipped product surface is a
supervision runtime with personal WeChat, WhatsApp, reminders, calendar import,
subscription, and account recovery flows.
