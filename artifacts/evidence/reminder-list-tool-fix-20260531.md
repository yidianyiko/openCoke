# Reminder List Tool Fix Evidence

Date: 2026-05-31

## Production Root Cause

Production run evidence for `现在我一共有几个提醒？` showed:

```text
semantic_decision.intent_family=reminder_op
semantic_decision.intent_action=list_reminders
tool_name=reminder_tool
tool_args={"operation": "list_reminders", "account_id": "ae02ff01..."}
tool_result.ok=false
tool_result.reason_code=unsupported_reminder_operation
```

The affected account's active reminders were present in Postgres, so the issue
was a missing Interaction Agent tool operation, not unavailable reminder state.

## Commands

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_tool_list_reminders_returns_active_count_without_write_guard -q
```

Result: failed before implementation because `ReminderToolAdapter.execute`
entered the write guard before recognizing `list_reminders`.

```text
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard -q
```

Result: failed before implementation because the reminder tool doc did not
expose `list_reminders`.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_tool_list_reminders_returns_active_count_without_write_guard -q
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard -q
.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py::test_inbound_reminder_count_uses_tool_result_for_visible_reply -q
```

Result: all focused tests passed after implementation.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py tests/integration/coke/test_composition_turn_integration.py -q
```

Result: 81 passed in 2.25s.

```text
.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/check
git diff --check
```

Result: 588 unit tests passed in 17.42s; repo structure check passed; whitespace
check passed.

```text
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result: clean-rebuild-backend passed with 588 unit tests in 17.61s;
repo-os-docs passed.

```text
zsh scripts/review-trigger --base HEAD~1
```

Result: `human_review_required: no`. Remaining medium risk triggers were
repo-OS issue-record changes; the evidence gap was resolved after this evidence
file was added to the indexed diff.

```text
scripts/deploy-compose-to-gcp.sh
```

Result: deployed local SHA `ba4c005cc4e2aa220e6fd9b2fd3bfac3f24ec58a` to
`gcp-coke`; clean deploy health checks passed. Remote `.deployed-sha` returned
`ba4c005cc4e2aa220e6fd9b2fd3bfac3f24ec58a`.

```text
ssh gcp-coke 'cd /home/whoami/coke-clean && docker compose -p coke-clean -f docker-compose.prod.yml -f docker-compose.clean.yml ps coke-api coke-worker coke-outbox-relay coke-scheduler'
```

Result: `coke-api` was healthy; `coke-worker`, `coke-outbox-relay`, and
`coke-scheduler` were up after deploy.

```text
runtime.adapters.reminder_tool.execute(
    {'operation': 'list_reminders', 'account_id': 'ae02ff01-6fcd-4d39-a189-e51c8c8a31e6'},
    object(),
)
```

Result: production direct tool check returned `ok=True`, `reason_code=None`,
`action=list_reminders`, and `count=28`.

```text
POST /webhooks/wechat/personal
raw_event_id=codex-reminder-list-smoke-20260531T133138Z-retrybody
text=现在我一共有几个提醒？
```

Result: production user-path smoke created turn
`9d6bf3e5-780c-4f4a-a010-49f4bf6ebeca` with disposition
`replied / reply_ready`. Outbound message
`d109fd5f-4b48-4ee7-bcff-6527991411ee` was `你目前一共有 28 个提醒。`;
delivery attempt status was `sent` with provider id
`coke-1780234489305-3e06d9d15c26`.

## Follow-up UX Contract

The first production smoke proved the read path worked but still produced a
count-only reply. The follow-up change makes a successful reminder list/count
query return and request rendering of every active reminder.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py::test_reminder_tool_list_reminders_returns_active_count_without_write_guard -q
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_reminder_list_instructions_require_full_list_not_count_only tests/unit/coke/llm/test_interaction_agent.py::test_tool_ports_are_exposed_as_agno_tools_and_execute_with_guard -q
.venv/bin/python -m pytest tests/integration/coke/test_composition_turn_integration.py::test_inbound_reminder_count_uses_tool_result_for_visible_reply -q
```

Result: all focused checks passed after the UX contract change.

```text
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py tests/integration/coke/test_composition_turn_integration.py -q
```

Result: 82 passed in 2.22s.

```text
.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/check
git diff --check
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Result: 589 unit tests passed in 20.34s; `scripts/check` passed; whitespace
check passed; `verify-surface` passed clean-rebuild-backend with 589 tests in
18.41s and repo-os-docs. Verification suggestion matched
`clean-rebuild-backend repo-os-docs`. Risk report returned
`human_review_required: no`; the only risk trigger was the medium
`sensitive_repo_os_change` for updating the incident record.

```text
scripts/deploy-compose-to-gcp.sh
```

Result: deployed `202d13084e108674958aa6b1ad7e6dc9988a9833`. Service health
checks passed and remote `.deployed-sha` matched that commit.

```text
runtime.adapters.reminder_tool.execute(
    {'operation': 'list_reminders', 'account_id': 'ae02ff01-6fcd-4d39-a189-e51c8c8a31e6'},
    object(),
)
```

Result: production direct tool check returned `ok=True`, `count=28`,
`display_line_count=28`, and `reply_contract=render_reminder_list`.

```text
POST /webhooks/wechat/personal
raw_event_id=codex-reminder-list-detail-smoke-20260531T135815Z
text=现在我一共有几个提醒？
```

Result: the prompt/tool-contract-only deployment still produced a count-only
outbound message `你现在一共有 28 个提醒。` with provider status `sent`. This
confirmed the need for a runtime guard rather than prompt-only enforcement.

```text
.venv/bin/python -m pytest tests/unit/coke/llm/test_interaction_agent.py::test_reminder_list_tool_result_overrides_count_only_final_reply -q
.venv/bin/python -m pytest tests/unit/coke/turn/test_turn_runner.py tests/unit/coke/llm/test_interaction_agent.py tests/integration/coke/test_composition_turn_integration.py -q
.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/check
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Result: the runtime guard focused test passed; the affected set passed with
83 tests in 2.26s; full unit passed with 590 tests in 17.59s; `scripts/check`
passed; `verify-surface` passed clean-rebuild-backend with 590 tests in 18.32s
and repo-os-docs; verification suggestion remained
`clean-rebuild-backend repo-os-docs`; risk report returned
`human_review_required: no`.

```text
RSYNC_RSH='ssh -o ProxyCommand=none -o KexAlgorithms=curve25519-sha256' \
bash -c 'ssh() { command ssh -o ProxyCommand=none -o KexAlgorithms=curve25519-sha256 "$@"; }; export -f ssh; scripts/deploy-compose-to-gcp.sh'
```

Result: deployed `17bb046f8d1865c6c1c9d3a0564b2a911cbfa630`.
The normal SSH KEX path stalled while reading the remote sha, so the deploy
was rerun with direct SSH and `curve25519-sha256`; remote `.deployed-sha`
matched `17bb046f8d1865c6c1c9d3a0564b2a911cbfa630`. `coke-api` was healthy,
and `coke-worker`, `coke-outbox-relay`, and `coke-scheduler` were up.

```text
POST /webhooks/wechat/personal
raw_event_id=codex-reminder-list-guard-smoke-20260531T141402Z
text=现在我一共有几个提醒？
```

Result: production user-path smoke completed turn
`b641cf8f-ceb7-4969-9d15-4fb92fcddebd` as `replied / reply_ready`.
Outbound message `7db0dfff-cf1b-4470-9189-69a333f90b60` was 1433 characters
and 30 lines. It began:

```text
你现在一共有 29 个提醒：
1. 跑步（2026-05-31T01:00:00+00:00）
2. 一起喝水（2026-05-30T19:21:37.032838+00:00）
3. 喝水（2029-01-20T02:00:00+00:00）
```

Delivery attempt `d3e3a69e-d021-46c7-b355-e0f0866a4e5c` sent through
`wechat_personal` with provider id `coke-1780237015724-d10ffa2b6afa`.
