# Task: Design WeChat Ecloud Shared Channel

- Status: In Review
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

## Notes

- Design spec:
  `docs/superpowers/specs/2026-04-28-wechat-ecloud-shared-channel-design.md`
- User confirmed that `snsSendImage` / Moments publishing is not in this scope.
