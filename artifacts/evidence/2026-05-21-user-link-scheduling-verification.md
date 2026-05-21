# User Link Scheduling Verification

Date: 2026-05-21

## Environment Notes

- `memo-runtime` could not be checked out at the root gitlink commit because local source `/data/projects/coke-memo-runtime` does not contain `769aa46bf1d3e5f769236913846230fe4b0c654f`; a local uncommitted `memo-runtime/OWNERS.md` fixture was used only so repo-OS guardrails could read the required metadata file.
- Gateway API/Web package test scripts run their full package suites even when file paths are supplied.
- `zsh scripts/verify-surface product-memo` failed because that script invokes `pytest memo-runtime/tests` from the root cwd while memo-runtime schema tests read paths relative to the submodule root. Running the same submodule test suite from `memo-runtime/` passed.

## Command Results

### pnpm --dir gateway/packages/api test -- src/scheduling/schema-contract.test.ts src/scheduling/time.test.ts src/scheduling/user-link-service.test.ts src/scheduling/service-link-service.test.ts src/scheduling/availability-service.test.ts src/scheduling/appointment-service.test.ts src/scheduling/notification-service.test.ts src/routes/public-user-link-routes.test.ts src/routes/customer-scheduling-routes.test.ts src/routes/internal-scheduling-routes.test.ts

Exit code: 0

```text
 ✓ src/lib/stranded-model-retirement-schema.test.ts (2 tests) 11ms
 ✓ src/lib/platformization-migration.test.ts (9 tests) 31ms
 ✓ src/lib/personal-wechat-channel.test.ts (11 tests) 31ms
 ✓ src/lib/platformization-schema.test.ts (2 tests) 16ms
 ✓ src/channel/wechat-ecloud-config.test.ts (6 tests) 20ms
 ✓ src/lib/stranded-model-audit.test.ts (4 tests) 15ms
 ✓ src/routes/coke-user-provision.test.ts (5 tests) 36ms
 ✓ src/lib/parked-inbound.test.ts (2 tests) 14ms
 ✓ src/scripts/verify-shared-channel-runtime.test.ts (2 tests) 13ms
 ✓ src/routes/admin-auth-routes.test.ts (6 tests) 4486ms
   ✓ admin auth routes > logs in with an AdminAccount and returns the current admin session  1474ms
   ✓ admin auth routes > rejects the current session after an admin is disabled post-login  1403ms
   ✓ admin auth routes > treats logout as a stateless acknowledgment and does not invalidate the JWT  869ms
   ✓ admin auth routes > rejects login for inactive admins  729ms

 Test Files  76 passed (76)
      Tests  683 passed (683)
   Start at  22:27:00
   Duration  6.27s (transform 9.11s, setup 0ms, collect 25.16s, tests 17.05s, environment 39ms, prepare 17.28s)

```

### pnpm --dir gateway/packages/api build

Exit code: 0

```text

> @clawscale/api@0.1.0 build /data/projects/coke/.worktrees/user-link-scheduling/gateway/packages/api
> tsc -p tsconfig.json

```

### pnpm --dir gateway/packages/web test -- app/u/[code]/page.test.tsx app/u/[code]/qr/route.test.ts app/(customer)/auth/login/page.test.tsx app/(customer)/auth/register/page.test.tsx app/(customer)/auth/verify-email/page.test.tsx

Exit code: 0

```text
 ✓ app/(customer)/account/layout.test.tsx (1 test) 156ms
 ✓ app/(customer)/auth/claim-entry/page.test.tsx (5 tests) 232ms
 ✓ app/terms/page.test.tsx (1 test) 154ms
 ✓ app/u/[code]/qr/route.test.ts (1 test) 144ms
 ✓ app/(customer)/auth/layout.test.tsx (6 tests) 312ms
 ✓ app/privacy/page.test.tsx (1 test) 139ms
 ✓ app/faqs/page.test.tsx (1 test) 161ms
 ✓ app/u/[code]/page.test.tsx (3 tests) 38ms
 ✓ lib/customer-auth.test.ts (4 tests) 17ms
 ✓ app/(admin)/admin/shared-channels/[id]/page.test.tsx (1 test) 3ms
 ✓ lib/customer-reminders.test.ts (5 tests) 11ms
 ✓ app/dashboard-removal.test.ts (1 test) 4ms
 ✓ lib/admin-api.test.ts (1 test) 6ms
 ✓ app/layout.metadata.test.ts (4 tests) 5ms

 Test Files  43 passed (43)
      Tests  166 passed (166)
   Start at  22:27:25
   Duration  6.62s (transform 5.33s, setup 0ms, collect 22.83s, tests 9.43s, environment 45.79s, prepare 10.20s)

```

### pnpm --dir gateway/packages/web build

Exit code: 0

```text
├ ○ /auth/forgot-password
├ ○ /auth/login
├ ○ /auth/register
├ ○ /auth/reset-password
├ ○ /auth/verify-email
├ ○ /channels
├ ○ /channels/wechat-personal
├ ○ /demos
├ ○ /faqs
├ ○ /global
├ ○ /handoff/calendar-import
├ ○ /privacy
├ ○ /terms
├ ƒ /u/[code]
└ ƒ /u/[code]/qr


○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand

```

### .venv/bin/python -m pytest tests/unit/connector/clawscale_bridge/test_message_gateway.py tests/unit/connector/clawscale_bridge/test_bridge_app.py tests/unit/agent/test_scheduling_capability.py tests/unit/agent/test_agent_runtime_scheduling_tools.py tests/unit/agent/test_chat_response_scheduling_instructions.py -v

Exit code: 0

```text
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_preflight_returns_target_conversation PASSED [ 80%]
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_preflight_forwards_business_conversation_context PASSED [ 81%]
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_preflight_returns_conversation_required PASSED [ 82%]
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_run_rejects_missing_bearer_token PASSED [ 83%]
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_run_returns_counts_and_warnings PASSED [ 84%]
tests/unit/connector/clawscale_bridge/test_bridge_app.py::test_google_calendar_import_run_uses_provided_target_without_re_resolving PASSED [ 85%]
tests/unit/agent/test_scheduling_capability.py::test_get_user_link_calls_gateway_tool_with_trusted_customer_identity PASSED [ 87%]
tests/unit/agent/test_scheduling_capability.py::test_request_appointment_forwards_representative_tool_args PASSED [ 88%]
tests/unit/agent/test_scheduling_capability.py::test_scheduling_gateway_client_uses_internal_auth PASSED [ 89%]
tests/unit/agent/test_scheduling_capability.py::test_scheduling_gateway_client_returns_error_envelope PASSED [ 90%]
tests/unit/agent/test_scheduling_capability.py::test_port_turns_gateway_domain_error_into_model_visible_failure PASSED [ 91%]
tests/unit/agent/test_scheduling_capability.py::test_port_turns_gateway_exception_into_model_visible_failure PASSED [ 92%]
tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_default_runtime_exposes_all_scheduling_tools PASSED [ 94%]
tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_runtime_scheduling_wrapper_dispatches_model_args PASSED [ 95%]
tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_runtime_scheduling_tool_schema_exposes_top_level_arguments PASSED [ 96%]
tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_runtime_scheduling_tool_schema_exposes_bookable_window_preview_shape PASSED [ 97%]
tests/unit/agent/test_agent_runtime_scheduling_tools.py::test_runtime_scheduling_wrapper_serializes_preview_model PASSED [ 98%]
tests/unit/agent/test_chat_response_scheduling_instructions.py::test_scheduling_tool_boundary_is_present PASSED [100%]

============================== 85 passed in 3.67s ==============================
```

### zsh scripts/suggest-verification --base HEAD~1

Exit code: 0

```text
base: HEAD~1
changed_files: 5
- agent/agno_agent/__init__.py
- gateway
- memo-runtime
- tests/unit/agent/test_agent_runtime_construction.py
- artifacts/evidence/2026-05-21-user-link-scheduling-verification.md
changed_surfaces: repo-os-docs product-memo
suggested_command: zsh scripts/verify-surface repo-os-docs product-memo

== repo-os-docs ==
zsh scripts/check
== product-memo ==
.venv/bin/python -m pytest tests/unit/agent/test_memo_capability_adapter.py -v
.venv/bin/python -m pytest memo-runtime/tests -v
```

### zsh scripts/verify-surface repo-os-docs gateway-api gateway-web bridge worker-runtime

Exit code: 0

```text
.venv/bin/python -m pytest tests/unit/test_clawscale_only_topology.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.3, pluggy-1.6.0 -- /data/projects/coke/.worktrees/user-link-scheduling/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /data/projects/coke/.worktrees/user-link-scheduling
configfile: pyproject.toml
plugins: xdist-3.8.0, anyio-4.13.0, cov-7.1.0, timeout-2.4.0, asyncio-1.3.0, hypothesis-6.152.3
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 7 items

tests/unit/test_clawscale_only_topology.py::test_runtime_configs_remove_legacy_connector_sections PASSED [ 14%]
tests/unit/test_clawscale_only_topology.py::test_compose_and_nginx_expose_only_clawscale_services PASSED [ 28%]
tests/unit/test_clawscale_only_topology.py::test_local_runtime_assets_remove_legacy_connectors PASSED [ 42%]
tests/unit/test_clawscale_only_topology.py::test_legacy_connector_directories_are_removed PASSED [ 57%]
tests/unit/test_clawscale_only_topology.py::test_legacy_gateway_assets_are_removed PASSED [ 71%]
tests/unit/test_clawscale_only_topology.py::test_legacy_python_payment_runtime_is_removed PASSED [ 85%]
tests/unit/test_clawscale_only_topology.py::test_runtime_sources_remove_legacy_wechat_identity_fallbacks PASSED [100%]

============================== 7 passed in 0.26s ===============================
```

### zsh scripts/review-trigger --base HEAD~1

Exit code: 0

```text
base: HEAD~1
changed_files: 5
- agent/agno_agent/__init__.py
- gateway
- memo-runtime
- tests/unit/agent/test_agent_runtime_construction.py
- artifacts/evidence/2026-05-21-user-link-scheduling-verification.md
human_review_required: no
```

### zsh scripts/verify-surface product-memo (environment/script cwd issue; see note)

Exit code: 1

```text
             errors=None, newline=None):
        """
        Open the file pointed by this path and return a file object, as
        the built-in open() function does.
        """
        if "b" not in mode:
            encoding = io.text_encoding(encoding)
>       return io.open(self, mode, buffering, encoding, errors, newline)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       FileNotFoundError: [Errno 2] No such file or directory: 'memo_runtime/storage/postgres.py'

/usr/lib/python3.12/pathlib.py:1015: FileNotFoundError
=========================== short test summary info ============================
FAILED memo-runtime/tests/test_postgres_schema.py::test_initial_schema_contains_core_tables_and_indexes
FAILED memo-runtime/tests/test_postgres_schema.py::test_review_items_allow_proposal_card_ids
FAILED memo-runtime/tests/test_postgres_schema.py::test_event_idempotency_index_is_not_unique
FAILED memo-runtime/tests/test_postgres_schema.py::test_mutations_store_result_snapshots_for_idempotent_replay
FAILED memo-runtime/tests/test_postgres_schema.py::test_postgres_proposal_transitions_are_status_guarded
FAILED memo-runtime/tests/test_postgres_schema.py::test_postgres_empty_mutation_snapshots_fail_closed
=================== 6 failed, 32 passed, 3 skipped in 0.74s ====================
```

### (cd memo-runtime && ../.venv/bin/python -m pytest tests -v)

Exit code: 0

```text
tests/test_postgres_schema.py::test_postgres_mutation_snapshot_round_trips_card_state PASSED [ 58%]
tests/test_proposals.py::test_create_and_accept_create_card_proposal_records_deterministic_events PASSED [ 60%]
tests/test_proposals.py::test_create_proposal_replays_by_owner_operation_and_idempotency_key PASSED [ 63%]
tests/test_proposals.py::test_accept_proposal_replays_original_card_without_duplicate_events PASSED [ 65%]
tests/test_proposals.py::test_rejected_or_accepted_proposal_cannot_transition_again PASSED [ 68%]
tests/test_proposals.py::test_accept_create_card_proposal_validates_candidate_fields PASSED [ 70%]
tests/test_proposals.py::test_review_action_can_accept_or_reject_proposals_with_events_and_idempotency PASSED [ 73%]
tests/test_proposals.py::test_proposal_review_action_requires_proposal_card_id_and_does_not_hide_cards PASSED [ 75%]
tests/test_search_review.py::test_agent_search_excludes_private_deleted_and_other_owner_cards PASSED [ 78%]
tests/test_search_review.py::test_search_scores_keyword_tag_and_kind_matches_deterministically PASSED [ 80%]
tests/test_search_review.py::test_keyword_search_matches_tags PASSED     [ 82%]
tests/test_search_review.py::test_tag_filter_matches_any_requested_tag PASSED [ 85%]
tests/test_search_review.py::test_deterministic_embedding_provider_returns_stable_vectors PASSED [ 87%]
tests/test_search_review.py::test_review_queue_prioritizes_reasons_and_respects_visibility_and_lifecycle PASSED [ 90%]
tests/test_search_review.py::test_record_review_action_marks_card_reviewed_and_replays_without_new_event PASSED [ 92%]
tests/test_search_review.py::test_dismiss_records_review_event_without_incrementing_review_count PASSED [ 95%]
tests/test_search_review.py::test_proposal_review_actions_require_proposal_id[accept_proposal] PASSED [ 97%]
tests/test_search_review.py::test_proposal_review_actions_require_proposal_id[reject_proposal] PASSED [100%]

======================== 38 passed, 3 skipped in 0.39s =========================
```

