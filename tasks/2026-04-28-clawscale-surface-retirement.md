# ClawScale Surface Retirement

Date: 2026-04-28

## Scope

- Retired legacy workspace/member API routes: `/auth`, `/api/users`, `/api/tenant`, `/api/end-users`, `/api/onboard`, `/api/channels`.
- Retired legacy admin surfaces: `/api/admin/channels`, `/api/admin/agents`, `/admin/channels`, `/admin/agents`.
- Retired unused generic channel adapters: Discord, WeCom, Baileys WhatsApp, Telegram, Slack, Matrix, LINE, Signal, Teams, and Meta WhatsApp Business.
- Kept current product surfaces: customer auth, personal WeChat, shared-channel Evolution/Ecloud/Linq, outbound dispatch, internal Coke routes, admin customers/shared-channels/deliveries/admins.

## Verification

- `pnpm --dir gateway/packages/api test`
- `pnpm --dir gateway/packages/web test`
- `pnpm --dir gateway/packages/api build`
- `pnpm --dir gateway/packages/web build`
- `git diff --check`
- `zsh scripts/check`
