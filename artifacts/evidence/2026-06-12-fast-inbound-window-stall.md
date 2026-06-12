# 2026-06-12 Fast Inbound Window Stall Evidence

## Local Verification

- Commit `ccfa56ec032eff7e457c0d067e4c4ce71baef9cf`
  (`fix(worker): avoid stuck fast inbound windows`) added cancellation rollback
  and active-window-covered ack behavior.
- Commit `c30a58f46995173abf6215d53a45244b084721a5`
  (`fix(worker): make open-window recovery retryable`) made startup recovery use
  a fresh synthetic trigger per attempt.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed after
  the first commit: `931 passed, 1 skipped`; `scripts/check` passed.
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs` passed after
  the second commit: `932 passed, 1 skipped`; `scripts/check` passed.

## Production Deploy

- Deployed backend tier twice with `bash scripts/deploy-compose-to-gcp.sh`.
- Final deployed SHA on `gcp-coke:/home/whoami/coke-clean/.deployed-sha`:
  `c30a58f46995173abf6215d53a45244b084721a5`.
- Deploy health check returned `{"ok":true}`.

## Original Stuck Window Recovery

Conversation `7fed5c7c-08f9-4778-bdcc-c14b7f2cf346`, account
`ae02ff01-6fcd-4d39-a189-e51c8c8a31e6`, originally had:

- `latest_inbound_seq=216`
- `last_closed_inbound_seq=213`
- `open_lag=3`

After the recovery-trigger fix deploy:

- Conversation closed to `latest_inbound_seq=216`,
  `last_closed_inbound_seq=216`, `open_lag=0`.
- Recovery turn `778777cd-3c7e-4d2a-a39d-ccb3fe70de30` claimed
  `input_from_seq=214`, `input_to_seq=216` and completed as
  `replied/reply_ready`.
- Final outbound text:
  `这个晚饭提醒已经存在了，和eva的「晚饭」，今天19:30，时长1小时`
- Delivery attempt for that reply was `wechat_personal`, `status=sent`.
- Redis `XPENDING coke.work workers` returned `0`.
- Redis group showed `pending=0`, `lag=0`.
- Postgres activity showed `lock_waits=0`, `long_idle_xacts=0`.

## Production 1ms Three-Message Simulation

Simulation was executed directly inside the production `coke-api` container
against the same account/channel/conversation using
`ConversationRuntimeService.record_inbound`. It recorded three messages with
`time.sleep(0.001)` between commits:

- seq `217`, text `晚上好`, causal
  `manual_fast_triplet_20260612T1055Z_2af71a70_1`
- seq `218`, text `我现在有几个提醒？`, causal
  `manual_fast_triplet_20260612T1055Z_2af71a70_2`
- seq `219`, text `和eva约一个今天晚上七点半点的晚饭`, causal
  `manual_fast_triplet_20260612T1055Z_2af71a70_3`

The worker handled the window as one interactive turn:

- Turn `4abac7f2-6375-407f-b033-e528ee3f5e5d`
- Trigger `inbound:manual_fast_triplet_20260612T1055Z_2af71a70_1`
- `input_from_seq=217`, `input_to_seq=219`
- `disposition=replied`, `reason_code=reply_ready`
- Conversation closed to `latest_inbound_seq=219`,
  `last_closed_inbound_seq=219`, `open_lag=0`.
- Worker logs included two
  `interactive_inbound_event_acked_as_active_window_covered` entries for the
  later outbox events.

Final outbound segments:

- Segment 1: `晚上好～`
- Segment 2: `这个晚饭提醒已经有了哦，和eva的「晚饭」，今天19:30，时长1小时`

Delivery attempts:

- Segment 1: `wechat_personal`, `status=sent`, latency `893ms`.
- Segment 2: `wechat_personal`, `status=sent`, latency `376ms`.

Final health checks:

- Active interactive turns for the conversation: `0`.
- Conversation open lag: `0`.
- Redis `XPENDING coke.work workers`: `0`.
- Redis group: `pending=0`, `lag=0`.
- Postgres activity: `lock_waits=0`, `long_idle_xacts=0`.
