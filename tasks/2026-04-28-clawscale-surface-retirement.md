# ClawScale Surface Retirement

Date: 2026-04-28

## Scope

- Retired legacy workspace/member API routes: `/auth`, `/api/users`, `/api/tenant`, `/api/end-users`, `/api/onboard`, `/api/channels`.
- Retired legacy admin surfaces: `/api/admin/channels`, `/api/admin/agents`, `/admin/channels`, `/admin/agents`.
- Retired unused generic channel adapters: Discord, WeCom, Baileys WhatsApp, Telegram, Slack, Matrix, LINE, Signal, Teams, and Meta WhatsApp Business.
- Retired the old internal personal WeChat bridge route `/api/internal/user/wechat-channel` and the legacy `User` JWT middleware behind it.
- Retired bridge-side personal WeChat proxy client/service code and its stale deployment settings.
- Kept current product surfaces: customer auth, personal WeChat, shared-channel Evolution/Ecloud/Linq, outbound dispatch, internal Coke routes, admin customers/shared-channels/deliveries/admins.

## Verification

- `pnpm --dir gateway/packages/api test`
- `pnpm --dir gateway/packages/web test`
- `pnpm --dir gateway/packages/api build`
- `pnpm --dir gateway/packages/web build`
- `git diff --check`
- `zsh scripts/check`
