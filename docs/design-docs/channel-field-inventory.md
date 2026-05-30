# Channel Field Inventory

This document classifies channel fields after the Frontend / Platform /
Channel boundary split. The detailed ownership rule lives in
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.

## Classification

| Field or type | Classification | Owner | Allowed importers | Notes |
| --- | --- | --- | --- | --- |
| `ChannelType` | frontend-safe DTO | Channel System | web, api | Public channel kind identifier. |
| `ChannelStatus` | frontend-safe DTO | Channel System | web, api | Displayable status only; action truth comes from backend contracts. |
| `ChannelConfigField` | backend-only provider schema field | Channel System | api only | Lives in `provider-config-schema.ts`; may describe secrets or provider-only knobs. |
| `CHANNEL_CONFIG_SCHEMA` | backend-only provider schema | Channel System | api only | Lives in backend-only Channel module. |
| config-bearing admin channel create/update bodies | backend-only admin/write contract | Channel System | api/admin only | Keep out of `@clawscale/shared`; define locally in backend modules or route validators. |

## Rule

No provider secret, webhook token, app token, access token, or
provider-specific credential field may be imported by the top-level `web/`
client.
