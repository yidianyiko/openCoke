---
kind: active_issue
status: resolved
surface:
  - agent-runtime
  - gateway-scheduling
  - tools/agent_smoke
github_issue:
github_state:
github_url:
created_at: 2026-05-25
updated_at: 2026-05-25
---

# 2026-05-25 Block/Unblock Does Not Restore Shared Reminder Path

## What Happened

The block/unblock smoke provisioned Alice and Bob, created an Alice -> Bob
friendship, and then had Alice block Bob. Postgres showed the expected
`account_blocks` row after the block.

The blocked Bob attempt did not create a shared reminder and did not leak an
internal account id. Alice then tried `取消屏蔽 Bob`, but the live path did not
remove the `account_blocks` row. Bob's retry after the unblock attempt did not
create a shared reminder.

## Why It Matters

The intended lifecycle for this smoke is:

- Alice and Bob are friends.
- Alice blocks Bob.
- Bob cannot silently create a shared reminder while blocked.
- Alice unblocks Bob.
- Bob can create the shared reminder after unblock.

The current runtime cannot prove that lifecycle. A blocked relationship remains
blocked in the live smoke, and the current gateway contract also removes the
active friendship during `blockAccount` while `unblockAccount` only deletes the
block row. Making Bob's post-unblock retry succeed may require a product
contract decision about whether unblock restores the previous friendship or the
users must become friends again.

## Affected Surfaces

- `agent/agno_agent/runtime/agent_runtime.py`
- `gateway/packages/api/src/scheduling/friendship-service.ts`
- `tools/agent_smoke/_runner_phase_block_unblock.py`

## Evidence

- Unit runner checks passed:
  `.venv/bin/python -m pytest tests/unit/tools/test_runner_phase_block_unblock.py -q`
  with `3 passed`.
- First live run failed before setup because Bob's friend request prompt varied
  from the known working badminton smoke phrase:
  `artifacts/evidence/shared-reminder-agent-smoke/block-unblock-block-unblock-20260525t134047Z.json`.
- After aligning the setup prompt, live smoke reached the block lifecycle:
  `.venv/bin/python -m tools.agent_smoke._runner_phase_block_unblock`
  with batch `block-unblock-20260525t134646Z`.
- Evidence file:
  `artifacts/evidence/shared-reminder-agent-smoke/block-unblock-block-unblock-20260525t134646Z.json`.
- Observed replies:
  - Alice link: `这是你的好友邀请链接：http://localhost:4040/u/5SoRvmRwOcTH`
  - Bob friend request: `已发送好友请求。`
  - Alice accept: `已通过好友请求。`
  - Alice block: `已屏蔽该用户。`
  - Bob while blocked: `我没接住你刚才的意思。你可以换个说法再说一次吗？`
  - Alice unblock attempt:
    `操作失败了，系统说 Bob 的账号可能不存在或者还在黑名单校验有点问题。你确认下这个名字是对的吗？或者 TA 已经在你好友列表里吗？`
  - Bob retry: `我没接住你刚才的意思。你可以换个说法再说一次吗？`
- Final Postgres snapshot for the successful-setup batch:
  `customers=2`, `friendships=1`, `friend_requests=1`,
  `shared_reminder_requests=0`, `account_blocks=1`.
- Direct Postgres check showed the remaining block row:
  `ck_smoke_20260525t134646z_alice -> ck_smoke_20260525t134646z_bob`.
- Gateway logs for the successful-setup batch showed:
  - `send_friend_request_by_user_link_code` returned 200.
  - `accept_friend_request` returned 200.
  - `block_account` returned 200.
  - later block/unblock-related calls returned 400 and the block row remained.

## Current Status

- Resolved by feature removal. Block / unblock is no longer a Coke
  capability. Users coordinate via `removeFriendship`; if a user wants
  to stop a friend, they remove the friendship and decline future
  invites. Removing the feature also removed the underlying bugs (the
  unblock 400, the empty-fallback on a blocked write attempt, and the
  open friendship-restore contract question).

## Resolution

- Gateway commit `af48532 fix: retire account blocking scheduling
  surface` (drops `account_blocks` table + removes `blockAccount` /
  `unblockAccount` + HTTP routes + tests).
- Outer commit `763a22af fix: stabilize shared reminder scheduling
  flow` (removes `block_account` / `unblock_account` intent + tool
  surface in the agent).
- Smoke runner `tools/agent_smoke/_runner_phase_block_unblock.py` is
  obsolete and was retired as part of the removal.
