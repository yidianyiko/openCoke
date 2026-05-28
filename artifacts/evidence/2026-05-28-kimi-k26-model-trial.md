# 2026-05-28 Kimi K2.6 model trial

## Scope

- Source table: `docs/issues/2026-05-12-reminder-detect-model-bake-off.md`.
- Highest raw accuracy in that table: `Pro/moonshotai/Kimi-K2.6`, 18/20
  (90%) on the `reminder_detect` bake-off.
- Trial change: route `chat_response` and `semantic_interpreter` to
  `Pro/moonshotai/Kimi-K2.6`.
- Left unchanged: `reminder_detect` stays on `Pro/zai-org/GLM-5.1` with
  thinking disabled.

## Local verification

- RED before config change:
  `.venv/bin/python -m pytest tests/unit/agent/test_model_factory.py::test_chat_response_config_uses_siliconflow_kimi_k26 tests/unit/agent/test_model_factory.py::test_semantic_interpreter_config_uses_siliconflow_kimi_k26 -q`
  failed because `chat_response` still used MiniMax M2.5 and
  `semantic_interpreter` was not configured.
- JSON validation:
  `.venv/bin/python -m json.tool conf/config.json >/dev/null`
  and
  `.venv/bin/python -m json.tool deploy/config/coke.config.json >/dev/null`
  passed.
- Unit tests:
  `.venv/bin/python -m pytest tests/unit/agent/test_model_factory.py -q`
  passed: 6 passed.
- Deploy script regression:
  `bash scripts/test-deploy-compose-to-gcp.sh` passed.
- Repo check:
  `zsh scripts/check` passed.

## Production deployment

- Deployed only `deploy/config/coke.config.json` to `gcp-coke` to avoid
  syncing unrelated dirty workspace files.
- Backed up the remote config before replacing it.
- Restarted `coke-agent`.
- Verified remote container config:
  - `chat_response`: `siliconflow`, `Pro/moonshotai/Kimi-K2.6`
  - `semantic_interpreter`: `siliconflow`, `Pro/moonshotai/Kimi-K2.6`
  - `reminder_detect`: `siliconflow`, `Pro/zai-org/GLM-5.1`,
    `extra_body.enable_thinking=false`
- Verified health:
  - bridge `/bridge/healthz`: `{"ok":true}`
  - gateway `/health`: `{"ok":true,"version":"0.1.0"}`
  - `coke-agent` restarted and workers came up.

## Real-user smoke

- Marker: `kimi-smoke-20260528T154222Z`.
- Route/account under test:
  - requester: Li Zihao, `ck_CsFu-A91jbCSBwtizPx1K`
  - friend: olivers, `ck_SXk_J0U0V5JKcK09QHEuo`
  - active friendship: `cmpmw9gs60001ru1tc4y12851`
- Friend count prompt: `wo xianzai you ji ge haoyou?`
  - Result: still failed with the same fallback saying no friend-list function
    was found.
  - Chat run model: `Pro/moonshotai/Kimi-K2.6`.
  - The chat prompt had no trusted friend-count facts.
- Shared meeting prompt for olivers at 2029-01-01 09:00 Asia/Shanghai:
  - Created shared reminder:
    `sr_31a303c61b1c20923226f9fde58ebabe9d3502f7`.
  - Fire time: `2029-01-01 01:00:00` UTC.
  - Product notification to olivers:
    `cmppo0iak0008ln1t6mwdiuzt`, kind `shared_reminder_created`,
    delivered.
  - Requester output confirmed the meeting with olivers.
  - Receiver output notified olivers of the created shared reminder.
  - Chat run model: `Pro/moonshotai/Kimi-K2.6`.
  - The chat prompt included trusted pre-executed
    `create_shared_reminder` facts.
- Cleanup:
  - Cancelled shared reminder with idempotency key
    `cleanup-kimi-smoke-20260528T154222Z`.
  - Reminder status became `cancelled`.
  - Cancellation notification to olivers:
    `cmppo3ztb000gln1t0a6cqs3u`, kind `shared_reminder_cancelled`,
    delivered.

## Readout

The model switch fixed the shared-reminder phrasing path for this marked
production test, but it did not fix the friend-count request. The remaining
friend-count failure is therefore not explained by MiniMax alone; the runtime
needs a deterministic friendship/list/count capability path or routing change.

Kimi K2.6 also showed the expected latency cost: the friend-count
`chat_response` run took about 74 seconds end to end.
