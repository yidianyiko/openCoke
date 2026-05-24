# Agent Smoke — Codex Briefing

You are running an end-to-end smoke of Coke's agent system as a real user
would: two synthetic users (Alice and Bob) hold a Chinese conversation through
the bridge, exchange a friend link, and end with a working **shared reminder**
that both sides accepted.

This is not a unit test. The goal is **finding real defects**, not making a
JSON green. Read the rules at the bottom before fixing anything.

---

## 1. Stack you need running

These are assumed UP. Verify before starting; do not try to start them from
scratch — they need env vars (CLAWSCALE_*_API_URL, gateway DATABASE_URL, real
JWT/STRIPE secrets) that live in the user's shell, not in the repo.

| Service | Check | If down |
|---|---|---|
| bridge :8090 | `curl http://127.0.0.1:8090/bridge/healthz` → `{"ok":true}` | Stop, report blocker |
| gateway :4041 | `curl http://127.0.0.1:4041/health` → `{"ok":true,...}` | Stop, report blocker |
| agent_runner | `pm2 status` → `coke-agent` online | Stop, report blocker |
| mongo 27017, redis 6379, postgres 15432 (gateway db) | `pgrep -a mongod redis postgres` | Stop, report blocker |

If any are down, this is an **environment issue** — fix it or stop. Do **not**
patch the helpers to skip the missing service.

## 2. Helpers (the only "mechanical" plumbing — reuse, don't reinvent)

All helpers live in `tools/agent_smoke/`. Run from repo root so `tools.*`
imports resolve.

```python
from tools.agent_smoke.bridge_client   import send_as, BridgeError
from tools.agent_smoke.account_factory import provision_account
from tools.agent_smoke.transcript      import Transcript, Turn
import time

batch_id = time.strftime("%Y%m%dt%H%M%SZ", time.gmtime())

alice = provision_account("alice", batch_id=batch_id, display_name="Alice Smoke")
bob   = provision_account("bob",   batch_id=batch_id, display_name="Bob Smoke")

# Each account carries its tenant_id / clawscale_user_id from provisioning.
# Splat `account.send_kwargs()` so the bridge sees a fully-identified user.
reply = send_as(alice.coke_account_id, "你好，今天天气怎么样？", **alice.send_kwargs())
print(reply.reply)       # assistant's Chinese text
print(reply.output_id)
```

Notes:
- `provision_account` does two things behind the scenes: (1) seeds Customer +
  Identity + Membership rows into gateway's postgres at port 15432 (no public
  API exists for synthetic accounts), (2) calls
  `/api/internal/coke-users/provision` to mint tenant + clawscale user. Both
  are idempotent across batch ids — but emails are batch-scoped to dodge the
  `identities_email_key` unique constraint.
- `send_as` POSTs to `/bridge/inbound` with the 6 required identity fields
  (tenant, channel, platform, external, end_user, coke_account). Synthesizes
  deterministic placeholders for any you don't pass — but `tenant_id` and
  `clawscale_user_id` should come from provision so they match the real
  postgres records.
- The bridge's `reply_timeout_seconds` is **25s** (production config). When
  the worker is contended, `send_as` falls back to polling `outputmessages` in
  Mongo for up to `request_timeout` (default 180s) keyed on
  `causal_inbound_event_id`. Empty reply after that means the worker really
  never produced output — that's a finding.
- All Chinese strings — Alice and Bob speak Chinese to the assistant, just
  like real users.

## 3. The flow (v1 = core closed loop)

You speak as Alice and Bob. Generate each turn yourself in natural Chinese,
read the assistant's reply, decide the next message. Aim for **20+ turns
total** across both speakers.

Minimum scenario that must succeed:

1. **Alice greets and checks inbox.** "我是 Alice，先看看我有没有未处理的好友请求或系统通知。" → assistant should report none.
2. **Alice requests her user link.** "把我自己的好友链接给我。" → assistant returns a code (e.g. `r23nsWHRmwEP`) and a URL.
3. **Bob adds Alice via the link.** Bob says "我要加好友，链接码 `<alice_code>`，备注：跑步搭子。" → assistant should call the scheduling tool that creates a friend request from Bob to Alice.
4. **Alice sees the pending request and accepts.** "看看我的好友请求，把 Bob 通过。" → assistant lists, then accepts.
5. **Alice proposes a shared reminder.** "我想约 Bob 这周五晚上 19:00 一起跑步，帮我建一个共享提醒。" → assistant should call `create_shared_reminder`.
6. **Bob sees and accepts the shared reminder.** "我有什么待处理的共享提醒？接受 Alice 那条。" → assistant lists, then accepts.
7. **Both confirm via assistant.** Each asks "我有哪些 reminder？" — both should now own the same event (different reminder ids, same shared link).

Use the assistant's text as your only signal — don't peek into mongo unless
you suspect a bug. That's how a real user would experience it.

Record every turn:

```python
t = Transcript(batch_id=batch_id)
t.add_account(alice); t.add_account(bob)

start = time.monotonic()
reply = send_as(alice.coke_account_id, text, display_name=alice.display_name)
t.add_turn(Turn(
    turn=len(t.turns) + 1,
    speaker="alice",
    coke_account_id=alice.coke_account_id,
    input_text=text,
    inbound_event_id=reply.causal_inbound_event_id,
    reply_text=reply.reply,
    output_id=reply.output_id,
    elapsed_ms=int((time.monotonic() - start) * 1000),
))
```

At the end:

```python
t.set_verdict(passed=True, problems=[])      # or passed=False with problems
path = t.save("artifacts/evidence/shared-reminder-agent-smoke")
print(f"evidence: {path}")
```

## 4. When something goes wrong (READ THIS)

Testing exists to find product bugs. **Do not edit tests, scenarios, or
assertions to make the smoke green.** Follow CLAUDE.md's "classify before
editing" rule:

| Failure shape | Layer to fix |
|---|---|
| Assistant returns wrong/empty text, calls wrong tool, ignores friend link, mis-schedules | **Product / runtime** — fix the relevant agent prompt, scheduling tool, or runtime module |
| Bridge / worker / scheduler crashes or hangs | **Product / runtime** — file an issue, fix the root cause |
| Service not running, env var missing, port blocked | **Environment** — start the service, set the var; do not patch helpers around it |
| Helper sends wrong payload, JSON parsing wrong | **Helper** — fix `tools/agent_smoke/` |
| Behavior the briefing didn't ask for | **Scope** — note it as a finding, don't expand v1 |

For every **product** bug found:

1. Stop the smoke at the failing turn.
2. Create or update `docs/issues/2026-05-24-<short>.md` with:
   - what the user said
   - what the assistant did
   - what should have happened
   - minimal reproduction (one `send_as` call if possible)
3. Locate root cause in the code (`agent/`, `gateway/`, `connector/`).
4. Fix at the smallest reasonable layer — **do not** add compatibility shims
   or weaken contracts to bypass.
5. Re-run the smoke from a fresh `batch_id`.
6. Record the fix commit hash in the issue record.

Never:
- run pytest "until it passes" — this is real-stack smoke, not unit tests
- bypass the scheduling tools by writing friend-request / shared-reminder docs
  directly into Mongo
- declare success when the assistant produced apologetic vague text instead of
  the expected tool call
- skip provisioning ("works on my id") — every user goes through `provision_account`

## 5. Output

- **Evidence:** one JSON per run at
  `artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-<batch_id>.json`
- **Issues filed:** zero or more `docs/issues/2026-05-24-*.md`
- **Final stdout summary:** one line per finding + `verdict.passed` + evidence
  path. If `passed=False`, list each problem with the issue file it maps to.

## 6. Known boot-time accidental couplings (already observed, do NOT chase as bugs)

These were found when investigating helper setup. They are not blocking your
smoke, but they're the kind of "gateway pulls in stuff we don't use" the user
asked about. If you happen to touch the related routes, flag them — otherwise
leave them alone:

- **Stripe ctor at module load.** `customer-subscription-routes.ts` constructs
  Stripe SDK during import, so `STRIPE_SECRET_KEY` is required just to boot
  even though our smoke never touches subscriptions.
- **WeChat adapter prisma probe at boot.** `initWeixinAdapters` runs
  `prisma.channel.findMany()` on startup; logs a non-fatal
  `PrismaClientInitializationError` if the DB is misconfigured.
- **Gateway agent_runner restart count.** `pm2 status` shows `coke-agent`
  restarted ~119 times historically. If your smoke reveals more crashes,
  that's relevant — restart count alone is not.

These would be cleanup candidates (per the user's "remove unused gateway
features" goal) for a follow-up, not part of this v1.

That's it. Speak Chinese, read carefully, fix the right layer.
