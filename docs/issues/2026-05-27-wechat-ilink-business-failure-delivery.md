---
kind: progress_note
status: resolved
title: WeChat iLink business failure was treated as delivered
created_at: 2026-05-27
updated_at: 2026-05-27
surface:
  - gateway
  - wechat-personal
  - production-smoke
---

# WeChat iLink Business Failure Delivery

## Problem

Production logs and a direct live probe showed that sending a WeChat personal
message to `olivers` through the restored iLink channel returned HTTP 200 with
body `{"ret":-2}`:

- Channel: `ch_2zs3tGFqYZLJSLonvet7W`
- Target: `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat`
- Probe marker: `ilink-direct-probe-20260527T135731Z`
- Response: HTTP 200, body `{"ret":-2}`

The gateway treated this as success because the adapter only awaited `fetch()`
and ignored the response body. Downstream outbound delivery then persisted a
successful result, so scheduling notifications could be marked `delivered`
even though WeChat rejected the message.

## External Meaning

The available public iLink protocol documentation is reverse-engineered rather
than official Tencent documentation, but the independent sources agree on the
important contract:

- `/ilink/bot/sendmessage` and `/ilink/bot/getupdates` are iLink bot API
  endpoints.
- `ret: 0` means success.
- `ret: -2` means parameter error or can appear when the send context token is
  stale after inactivity.
- `errcode: -14` means the session expired.
- `context_token` is returned with inbound messages and is part of correct
  routed replies.

Sources:

- https://www.wechatbot.dev/en/protocol
- https://openclawdir.com/plugins/weixin-bridge-8npli4
- https://github.com/epiral/weixin-bot/blob/main/docs/protocol-spec.md

## Root Cause

`gateway/packages/api/src/adapters/wechat.ts` handled iLink transport success
as delivery success. It did not inspect non-zero `ret` or `errcode` values from
either `sendmessage` or restored-channel `getupdates`.

That created two false-positive states:

- `sendmessage` returned `ret:-2`, but outbound delivery completed without
  throwing.
- A restored channel could keep reporting `connected` even if iLink had already
  declared the session invalid through a business error.

## Fix Direction

Fail closed at the WeChat adapter boundary:

- Parse every iLink response body used by `sendmessage` and `getupdates`.
- Treat non-zero `ret` and `errcode` as delivery/runtime failures even when
  HTTP status is 200.
- Mark restored personal WeChat channels as `error` when `getupdates` returns
  an iLink business failure.
- Do not add scheduler-level rules or compatibility shims.

## Verification

Local:

```bash
pnpm exec vitest run src/adapters/wechat.test.ts -t "sendmessage business failures|restored channels as error" --pool forks --maxWorkers=1
pnpm exec vitest run src/adapters/wechat.test.ts --pool forks --maxWorkers=1
pnpm exec tsc -p tsconfig.json --noEmit
pnpm exec vitest run src/adapters/wechat.test.ts src/routes/outbound.test.ts src/scheduling/notification-service.test.ts --pool forks --maxWorkers=1
zsh scripts/check
pnpm run build
```

Result:

- Targeted adapter checks: 2 passed
- Full adapter file: 11 passed
- TypeScript: passed
- Adapter/outbound/notification checks: 51 passed
- Repo-OS checks: passed
- API build: passed

Deployment:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Result:

- Remote gateway/web/API build: passed
- Remote health checks: passed
- Public site checks: passed

Production:

- Raw iLink probe marker `ilink-raw-probe-20260527T1429Z` returned HTTP 200
  with `{}` and was confirmed received by `olivers`.
- `/api/outbound` marker `outbound-final-20260527T1438Z` returned HTTP 200
  with `ok:true`.
- Outbound row `cmpo60xeb0000m81u4uazj1r1` was persisted as `succeeded` on
  channel `ch_2zs3tGFqYZLJSLonvet7W` for
  `o9cq802Y5W-kzfSNDAL4gUrWK_OQ@im.wechat`.

The observed post-fix production state is that olivers' iLink route is
currently sendable. If iLink returns `ret:-2` again, the adapter now fails the
delivery instead of reporting success.
