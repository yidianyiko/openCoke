# Task: Design WeChat Ecloud Shared Channel

- Status: Implemented
- Owner: Codex
- Date: 2026-04-28

## Goal

Write the design for adding a `wechat_ecloud` shared-channel integration that
maps the old GitHub `coke` Ecloud messaging surface into a phased shared-channel
design without adding QR-code login or Moments publishing.

## Scope

- In scope:
  - Review local OpenCoke shared-channel architecture
  - Review private GitHub `yidianyiko/coke` Ecloud connector behavior
  - Review the current Eyun docs at `https://wkteam.cn/`
  - Define the `wechat_ecloud` gateway integration boundary
  - Capture explicit non-goals for login and `snsSendImage`
- Out of scope:
  - Implementing the channel type
  - Writing the implementation plan
  - Supporting QR-code login, reconnect, or Moments publishing
  - Expanding outbound beyond text in the first implementation

## Touched Surfaces

- gateway-api
- gateway-web
- repo-os

## Acceptance Criteria

- The spec names the channel type `wechat_ecloud`
- The spec states that QR login and session lifecycle APIs are out of scope
- The spec states that Moments / `snsSendImage` is out of scope
- The spec maps old `coke` Ecloud message types to the proposed gateway
  behavior
- The spec follows the current `whatsapp_evolution` shared-channel pattern
- The spec preserves ClawScale shared-channel customer provisioning and does
  not reintroduce direct Mongo connector behavior
- The spec records text-only outbound as phase 1 and media handling as a
  follow-up
- The spec includes production constraints for webhook token safety, inbound
  deduplication, private-message filtering, XML parsing, and Eyun success
  handling

## Verification

- Command: `zsh scripts/check`
- Expected evidence: repo-OS checks pass after the spec is written
- Evidence: passed on 2026-04-28 with `check passed`

## Implementation Handoff

- Plan: `docs/superpowers/plans/2026-04-28-wechat-ecloud-shared-channel.md`
- Worktree: `/data/projects/coke/.worktrees/wechat-ecloud-shared-channel`
- Superproject branch: `feature/wechat-ecloud-shared-channel`
- Gateway branch: `feature/wechat-ecloud-shared-channel`
- Gateway head: `cd9ea0e fix: reject generic ecloud channel detail`
- Verification:
  - `pnpm --filter @clawscale/shared build`
  - `pnpm --filter @clawscale/api db:generate`
  - `pnpm --filter @clawscale/api exec vitest run src/lib/wechat-ecloud-config.test.ts src/lib/wechat-ecloud-api.test.ts src/lib/wechat-ecloud-webhook.test.ts src/lib/outbound-delivery.test.ts src/lib/route-message.test.ts src/gateway/message-router.test.ts src/routes/admin-shared-channels.test.ts src/routes/admin-channels.test.ts src/routes/channels.test.ts`
  - `pnpm --filter @clawscale/api build`
  - `pnpm --filter @clawscale/web test -- app/'(admin)'/admin/shared-channels/page.test.tsx app/'(admin)'/admin/shared-channels/detail/page.test.tsx`
  - `zsh scripts/check`

## Notes

- Design spec:
  `docs/superpowers/specs/2026-04-28-wechat-ecloud-shared-channel-design.md`
- User confirmed that `snsSendImage` / Moments publishing is not in this scope.
