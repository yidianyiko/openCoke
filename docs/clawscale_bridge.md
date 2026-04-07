## Environment

- `COKE_BRIDGE_API_KEY`
- `COKE_BIND_BASE_URL`
- `COKE_USER_AUTH_SECRET`
- `COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE`
- `COKE_WEB_ALLOWED_ORIGIN`
- `CLAWSCALE_OUTBOUND_API_URL`
- `CLAWSCALE_OUTBOUND_API_KEY`
- `CLAWSCALE_IDENTITY_API_URL`
- `CLAWSCALE_IDENTITY_API_KEY`

`COKE_WECHAT_PUBLIC_CONNECT_URL_TEMPLATE` must contain a `{bind_token}` placeholder and the
WeChat entry flow must round-trip that token into inbound WeChat `metadata.contextToken`.

Example:

```text
https://wx.example.com/coke-entry?bind_token={bind_token}
```

## Rollout

1. Set `CLAWSCALE_IDENTITY_API_URL` and `CLAWSCALE_IDENTITY_API_KEY` in the bridge environment.
2. Apply the gateway database migration from the gateway workspace:
   `pnpm -C gateway db:migrate`
3. Regenerate Prisma client types in the gateway workspace:
   `pnpm -C gateway --filter @clawscale/api db:generate`
4. Deploy or restart the Coke bridge so it picks up the new identity API settings.
5. Run the one-off backfill for active identities missing `clawscale_user_id`:
   `python -m connector.clawscale_bridge.backfill_clawscale_users`
6. Keep the bridge running and monitor for any bind sync failures before proceeding with traffic cutover.

## Start Coke bridge

Run `python -m connector.clawscale_bridge.app`

## Start proactive dispatcher

Run `python -m connector.clawscale_bridge.output_dispatcher`

## Start Coke workers in poll mode

Run `QUEUE_MODE=poll bash agent/runner/agent_start.sh`

## ClawScale custom backend config

- `baseUrl`: `http://<bridge-host>:8090/bridge/inbound`
- `authHeader`: `Bearer <COKE_BRIDGE_API_KEY>`
- `transport`: `http`
- `responseFormat`: `json-auto`

## Coke User Frontend

- User login: `http://<web-host>:4040/coke/login`
- User registration: `http://<web-host>:4040/coke/register`
- User bind page: `http://<web-host>:4040/coke/bind-wechat`

The Coke user frontend calls the Python bridge directly. Set:

- `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090`

If `NEXT_PUBLIC_COKE_API_URL` is unset, the web app falls back to `NEXT_PUBLIC_API_URL`.

## Manual Smoke Test

1. Confirm the gateway `clawscale_user_id` field has been generated for the target binding records and that the bridge rollout is complete.
2. Confirm Mongo `external_identities.clawscale_user_id` is populated for the same active identities after the backfill runs.
3. Start the ClawScale WeChat channel and confirm the official Coke WeChat entrypoint is already connected.
4. Start the Coke bridge: `python -m connector.clawscale_bridge.app`
5. Start the web app:
   `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090 pnpm -C gateway --filter @clawscale/web dev`
6. Open `http://127.0.0.1:4040/coke/register`, create a test user, and confirm the browser lands on `/coke/bind-wechat`.
7. Confirm the QR code renders on desktop.
8. Scan the QR code with an unbound personal WeChat account.
9. Send any message from that WeChat account to Coke.
10. Confirm the follow-up message routes through the bound account path after the bind completes, and that the response behavior matches the bound-identity flow.
11. Confirm `http://127.0.0.1:4040/coke/bind-wechat` refreshes to the bound state and shows the masked WeChat identity.
12. Confirm `external_identities` contains one active mapping for the bound `coke_user_id`.
