## Coke user channel model

The Coke user frontend now uses a personal WeChat channel lifecycle instead of the old
tenant-shared bind flow.

Primary user journey:

1. A Coke user signs in or registers.
2. The user opens `/channels/wechat-personal`.
3. The page fetches `GET /api/customer/channels/wechat-personal/status` to show the current lifecycle state.
4. The user clicks `Create my WeChat channel` to create that user’s personal `wechat_personal`
   channel through `POST /api/customer/channels/wechat-personal`.
5. The user starts or refreshes the QR login session through
   `POST /api/customer/channels/wechat-personal/connect`.
6. A successful create or connect response may already return `pending` with QR/connect info, so
   the page can render the login step immediately without waiting for a later status poll.
7. The page continues polling `GET /api/customer/channels/wechat-personal/status` while the session is pending.
8. The user can disconnect the channel with `POST /api/customer/channels/wechat-personal/disconnect`.
9. The user can archive the channel with `DELETE /api/customer/channels/wechat-personal` and later create a fresh one.

Lifecycle states surfaced to the UI:

- `missing`
- `disconnected`
- `pending`
- `connected`
- `error`
- `archived`

The user page should treat the channel record as the source of truth for ownership and state.
It should not depend on a shared bind record or a tenant-level shared WeChat connection for the
primary onboarding path.
The customer-facing API lives under `/api/customer/*`; `/api/internal/*` stays internal, and
retired public entrypoints `/login`, `/coke/login`, and `/api/coke/auth/login` return 404.

## Environment

The Coke user frontend talks to the bridge directly. Set:

- `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090`

If `NEXT_PUBLIC_COKE_API_URL` is unset, the web app falls back to `NEXT_PUBLIC_API_URL`.

Bridge/runtime environment:

- `COKE_BRIDGE_API_KEY`
- `COKE_USER_AUTH_SECRET`
- `COKE_WEB_ALLOWED_ORIGIN`
- `CLAWSCALE_OUTBOUND_API_URL`
- `CLAWSCALE_OUTBOUND_API_KEY`
- `CLAWSCALE_IDENTITY_API_URL`
- `CLAWSCALE_IDENTITY_API_KEY`

## Rollout

1. Ensure the bridge environment has `CLAWSCALE_IDENTITY_API_URL` and `CLAWSCALE_IDENTITY_API_KEY`.
2. Confirm the gateway and web app are deployed with the personal-channel UI and
   `/api/customer/channels/wechat-personal` endpoints.
3. Set `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090` for local web testing or the equivalent bridge URL in deployment.
4. Restart the Coke bridge so it picks up the current identity API settings.
5. Verify a test Coke user can create, connect, disconnect, and archive their own WeChat channel from `/channels/wechat-personal`.
6. Verify that a successful create or connect response can land the page directly in `pending` with QR/connect info and that the page keeps polling while the session remains active.
7. Verify the retired public entrypoints `/login`, `/coke/login`, and `/api/coke/auth/login` now return 404 instead of acting as compatibility aliases.

## Start Coke bridge

Run:

```bash
python -m connector.clawscale_bridge.app
```

## Start proactive dispatcher

Run:

```bash
python -m connector.clawscale_bridge.output_dispatcher
```

## Start Coke workers in poll mode

Run:

```bash
QUEUE_MODE=poll bash agent/runner/agent_start.sh
```

## ClawScale custom backend config

- `baseUrl`: `http://<bridge-host>:8090/bridge/inbound`
- `authHeader`: `Bearer <COKE_BRIDGE_API_KEY>`
- `transport`: `http`
- `responseFormat`: `json-auto`

## Coke User Frontend

- User login: `http://<web-host>:4040/auth/login`
- User registration: `http://<web-host>:4040/auth/register`
- Personal WeChat channel page: `http://<web-host>:4040/channels/wechat-personal`
- Subscription page: `http://<web-host>:4040/account/subscription`

## Manual Smoke Test

1. Start the Coke bridge:
   `python -m connector.clawscale_bridge.app`
2. Start the web app:
   `NEXT_PUBLIC_COKE_API_URL=http://127.0.0.1:8090 pnpm -C gateway --filter @clawscale/web dev`
3. Open `http://127.0.0.1:4040/auth/register` and create a test user.
4. Confirm the browser lands on `/auth/verify-email?email=...`.
5. Complete email verification and confirm the verified flow lands on `/channels/wechat-personal`.
6. Confirm the page first loads channel status and shows `Create my WeChat channel` for a user with no channel row.
7. Click `Create my WeChat channel` and confirm the page can transition directly to `pending` with QR/connect info.
8. Start or refresh the QR login session as needed and confirm the QR code renders for that user’s personal channel.
9. Scan the QR code with the WeChat account that should own the channel.
10. Confirm the page transitions to the connected state and shows the masked WeChat identity.
11. Click disconnect and confirm the page returns to `disconnected`.
12. Click archive and confirm the page shows the archived state with a create-again action.
