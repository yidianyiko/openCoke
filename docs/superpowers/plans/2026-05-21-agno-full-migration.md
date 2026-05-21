---
title: agno Full Migration
spec: docs/superpowers/specs/2026-05-21-agno-full-migration-design.md
status: active
date: 2026-05-21
---

# agno Full Migration Implementation Plan

## Phase 1: Delete dead code

1. Remove the retired orchestrator and context-retrieve tool surfaces.
   - Files to change:
     - Modify `agent/agno_agent/agents/__init__.py`
     - Modify `agent/agno_agent/schemas/__init__.py`
     - Delete `agent/agno_agent/schemas/orchestrator_schema.py`
     - Modify `agent/agno_agent/tools/__init__.py`
     - Delete `agent/agno_agent/tools/context_retrieve_tool.py`
   - What exactly to do:
     - In `agent/agno_agent/agents/__init__.py`, delete the `OrchestratorResponse` import, `DESCRIPTION_ORCHESTRATOR` and `INSTRUCTIONS_ORCHESTRATOR` imports, `get_orchestrator_instructions()`, the module-level `orchestrator_agent`, and the `orchestrator_agent` / `get_orchestrator_instructions` entries from `__all__`.
     - In `agent/agno_agent/schemas/__init__.py`, remove imports and exports for `ContextRetrieveParams` and `OrchestratorResponse`.
     - Delete `agent/agno_agent/schemas/orchestrator_schema.py`.
     - In `agent/agno_agent/tools/__init__.py`, remove the `context_retrieve_tool` import, export, and module doc entry.
     - Delete `agent/agno_agent/tools/context_retrieve_tool.py`.
     - Keep `agent/agno_agent/capabilities/context_retrieve.py`; the spec explicitly defers the RAG/business-query split.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/prompt/test_agent_instructions_prompt.py tests/unit/test_reminder_detect_structured_output.py -q`
   - Test files affected:
     - `tests/unit/prompt/test_agent_instructions_prompt.py`
     - `tests/unit/test_reminder_detect_structured_output.py`

2. Remove dead default capability ports that never became agno tools.
   - Files to change:
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
   - What exactly to do:
     - In `_default_capability_ports()`, remove the imports and returned entries for `AlbumCapabilityPort`, `ContextRetrieveCapabilityPort`, and `UsageCapabilityPort`.
     - Leave only `ReminderIntentPort`, `TimezoneCapabilityPort`, `CalendarImportPort`, and `UrlContextPort` in the default port map.
     - Do not delete the capability modules themselves; only remove these dead registrations from the main agno runtime.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_envelope.py tests/unit/agent/test_agent_runtime_output_rules.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_construction.py`
     - `tests/unit/agent/test_agent_runtime_envelope.py`
     - `tests/unit/agent/test_agent_runtime_output_rules.py`

## Phase 2: Simplify context.py

3. Remove relation trust validation and raw metadata smuggling hooks.
   - Files to change:
     - Modify `agent/agno_agent/runtime/context.py`
   - What exactly to do:
     - Delete `_optional_relation_id()`, `_trusted_relation_id()`, and `_metadata_from_raw()`.
     - In `build_agent_run_context()`, set `relation_uid = user_id` and `relation_cid = character_id` directly.
     - Remove all `metadata=_metadata_from_raw(...)` arguments when constructing `TrustedUserContext`, `TrustedCharacterContext`, `TrustedConversationContext`, and `TrustedRelationContext`; let the dataclass defaults provide empty frozen metadata.
     - Keep `AgentRunContext` and the trusted context dataclasses as plain frozen data containers.
     - Keep `recent_chat_history` on `AgentRunContext` for compatibility during this step; Phase 3 stops injecting it into the model prompt.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_event_adapter_routing.py tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_reminder_command_executor.py tests/unit/agent/test_chat_response_instructions.py -q`
   - Test files affected:
     - `tests/unit/agent/test_event_adapter_routing.py`
     - `tests/unit/agent/test_agent_runtime_types.py`
     - `tests/unit/agent/test_reminder_command_executor.py`
     - `tests/unit/agent/test_chat_response_instructions.py`

## Phase 3: Rewrite agent_runtime.py (session + history)

4. Add the shared agno session database module.
   - Files to change:
     - Create `agent/agno_agent/runtime/session.py`
   - What exactly to do:
     - Add `build_agent_session_db()` that imports `MongoDb` from `agno.db.mongo` and builds:
       - `session_collection="agent_sessions"`
       - `db_url="mongodb://{CONF['mongodb']['mongodb_ip']}:{CONF['mongodb']['mongodb_port']}/"`
       - `db_name=CONF["mongodb"]["mongodb_name"]`
     - Add module-level storage for the shared db object.
     - Add `initialize_agent_session_db(db: Any | None = None) -> Any` so worker boot can create and store the shared db once; when `db` is provided, store that injected object for tests.
     - Add `get_agent_session_db() -> Any` to return the stored db and lazily initialize only if a unit test or direct runtime call did not run the boot hook.
     - Add `reset_agent_session_db_for_tests() -> None` for unit tests that need isolation.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_construction.py`

5. Inline tool wrapper construction into `agent_runtime.py` and remove `tool_wrappers.py`.
   - Files to change:
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
     - Delete `agent/agno_agent/runtime/tool_wrappers.py`
   - What exactly to do:
     - Move `_model_facing_envelope()` and `_jsonable()` into `agent_runtime.py`.
     - Reuse the existing `_run_capability_port()` instead of keeping a separate `_run_port()` helper.
     - Move the concrete wrapper functions for `reminder_intent`, `timezone`, `calendar_import`, and `url_context` into `agent_runtime.py`.
     - Keep the per-turn `tool_results` closure list, the reminder duplicate guard dict, and the reminder `asyncio.Lock`.
     - Remove `_TOOL_NAMES` and `_build_missing_wrapper`; build wrappers only for the ports returned by `_default_capability_ports()`.
     - Update `_create_agent()` to call the new local wrapper builder.
     - Delete the import of `build_capability_tool_wrappers` from `runtime/tool_wrappers.py`.
     - Delete `agent/agno_agent/runtime/tool_wrappers.py` after all runtime imports have moved.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_envelope.py tests/unit/agent/test_agent_runtime_async_offload.py tests/unit/agent/test_agent_runtime_construction.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_envelope.py`
     - `tests/unit/agent/test_agent_runtime_async_offload.py`
     - `tests/unit/agent/test_agent_runtime_construction.py`

6. Move runtime metadata into chat instructions.
   - Files to change:
     - Modify `agent/agno_agent/runtime/chat_response_instructions.py`
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
   - What exactly to do:
     - Change `build_chat_response_instructions(run_context)` to `build_chat_response_instructions(run_context, agent_input)`.
     - Add a runtime context block to the returned instruction string with `current_time`, `user id/nickname`, `character id/nickname`, `platform`, `input_type`, `conversation_id`, and `route_key` when present.
     - For `ReminderFirePayload`, add the reminder-fired contract block from the old `_model_input()` logic, including `reminder_id`, `reminder_title`, `scheduled_for`, and `fire_id`.
     - Keep the existing persona cleanup, user-visible reply boundary, reminder tool boundary, and default timezone text.
     - Do not include `recent_chat_history` in the instructions.
     - Update `_create_agent()` to pass both `run_context` and `agent_input` to `build_chat_response_instructions()`.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py -q`
   - Test files affected:
     - `tests/unit/agent/test_chat_response_instructions.py`
     - `tests/unit/agent/test_agent_runtime_construction.py`
     - `tests/unit/agent/test_agent_runtime_output_rules.py`

7. Configure the main chat agent to use agno session history.
   - Files to change:
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
   - What exactly to do:
     - Add `agent_input: AgentInput` and optional `session_db: Any | None = None` to `_create_agent()`.
     - In `_create_agent()`, resolve the db with `session_db or get_agent_session_db()`.
     - Construct `Agent(...)` with `db=<resolved db>`, `add_history_to_context=True`, `num_history_messages=20`, and `add_session_state_to_context=False`.
     - Keep `id="coke-single-agent"`, `name="CokeSingleAgent"`, the `chat_response` model, `tool_call_limit=4`, and `markdown=False`.
     - Update `run_agent_runtime()` to pass `agent_input` into `_create_agent()`.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_unknown_tool.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_construction.py`
     - `tests/unit/agent/test_agent_runtime_output_rules.py`
     - `tests/unit/agent/test_agent_runtime_unknown_tool.py`

8. Remove `_model_input()` and use raw user input plus `RunResponse.content`.
   - Files to change:
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
   - What exactly to do:
     - Delete `_message_value()` and `_extract_final_text()`.
     - Delete `_model_input()`.
     - In `run_agent_runtime()`, call `agent.arun(input=input_message, session_id=run_context.conversation.id)`.
     - Set `final_text = _string_content(getattr(run_output, "content", None))`.
     - Keep `_string_content()` because it is still useful for normalizing `RunResponse.content`.
     - Keep `_message_source()` because post-analyze input still records message source.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_durable_write_contract.py tests/unit/agent/test_agent_runtime_final_text_extraction.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_construction.py`
     - `tests/unit/agent/test_agent_runtime_output_rules.py`
     - `tests/unit/agent/test_agent_runtime_durable_write_contract.py`
     - `tests/unit/agent/test_agent_runtime_final_text_extraction.py`

9. Remove runtime recovery that manually invokes reminder intent after an unconfirmed durable-write promise.
   - Files to change:
     - Modify `agent/agno_agent/runtime/agent_runtime.py`
   - What exactly to do:
     - Delete `_recover_unconfirmed_durable_write_promise()`.
     - In `run_agent_runtime()`, keep `_check_unconfirmed_durable_write_promise()`, but do not run a second reminder port call when it returns an error.
     - Let `runtime_contract_error = durable_write_error or unconfirmed_promise_error` suppress visible text as it already does.
     - Keep `_check_durable_write_contract()` unchanged.
   - Acceptance criterion:
     - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_durable_write_contract.py -q`
   - Test files affected:
     - `tests/unit/agent/test_agent_runtime_output_rules.py`
     - `tests/unit/agent/test_agent_runtime_durable_write_contract.py`

## Phase 4: Fix sub-agent singletons (reminder_intent)

10. Instantiate the reminder detector per invocation.
    - Files to change:
      - Modify `agent/agno_agent/capabilities/reminder_intent.py`
    - What exactly to do:
      - Remove the local import of `reminder_detect_agent` from `agent.agno_agent.agents`.
      - Add a private `_create_reminder_detector()` helper that imports `Agent`, `create_llm_model`, `DESCRIPTION_REMINDER_DETECT`, and `INSTRUCTIONS_REMINDER_DETECT`, then returns an `Agent` with:
        - `model=create_llm_model(role="reminder_detect", max_tokens=8000)`
        - `description=DESCRIPTION_REMINDER_DETECT`
        - `instructions=INSTRUCTIONS_REMINDER_DETECT`
        - `output_schema=ReminderDetectDecision`
        - `structured_outputs=True`
        - `markdown=False`
      - In `ReminderIntentPort.run()`, call `_create_reminder_detector()` for the primary detector call.
      - Keep the current `session_state` payload passed to `arun()`.
      - Pass `session_id=run_context.conversation.id`.
      - Do not configure `db` on the reminder detector.
    - Acceptance criterion:
      - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_intent_retry_schema.py -q`
    - Test files affected:
      - `tests/unit/agent/test_reminder_intent_capability.py`
      - `tests/unit/agent/test_reminder_intent_retry_schema.py`

11. Delete the reminder corrective retry state machine.
    - Files to change:
      - Modify `agent/agno_agent/capabilities/reminder_intent.py`
    - What exactly to do:
      - Remove `_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_TIMEOUT_RETRY_SECONDS` and `_DEFAULT_AGENT_RUNTIME_REMINDER_DETECT_RETRY_TIMEOUT_SECONDS`.
      - Remove `_agent_runtime_reminder_detect_timeout_retry_seconds()` and `_agent_runtime_reminder_detect_retry_timeout_seconds()`.
      - Remove all imports and references to `reminder_detect_retry_agent`.
      - Delete retry-specific prompt repair, retry reason selection, retry detector invocation, and retry timeout branches.
      - When the primary detector returns invalid structured output, no executable decision, or times out, return the existing failed `CapabilityResult` path immediately without attempting a second detector call.
      - Keep deterministic local normalization and safety checks that run after a valid primary decision; only remove the second LLM attempt and the reason-based retry routing.
    - Acceptance criterion:
      - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_intent_retry_schema.py tests/unit/prompt/test_agent_instructions_prompt.py -q`
    - Test files affected:
      - `tests/unit/agent/test_reminder_intent_capability.py`
      - `tests/unit/agent/test_reminder_intent_retry_schema.py`
      - `tests/unit/prompt/test_agent_instructions_prompt.py`

## Phase 5: Extract post_analyze

12. Extract post-analyze logic into `runtime/post_analyze.py` with a temporary workflow shim.
    - Files to change:
      - Create `agent/agno_agent/runtime/post_analyze.py`
      - Modify `agent/agno_agent/workflows/post_analyze_workflow.py`
    - What exactly to do:
      - Move the body of `PostAnalyzeWorkflow.run()` and its helper logic into module-level functions in `agent/agno_agent/runtime/post_analyze.py`.
      - Expose `async def run_post_analyze(session_state: dict[str, Any]) -> None`.
      - Preserve the in-place mutation of `session_state["relation"]`.
      - Preserve the skip behavior for `relation["reminder_created_with_time"]`.
      - Preserve prompt rendering, usage tracking, reminder schedule normalization, relation description compression, and relation/user/character field mapping.
      - Replace the imported module-level `post_analyze_agent` singleton with a private per-call factory that creates:
        - `Agent(model=create_llm_model(role="post_analyze", max_tokens=8000), output_schema=PostAnalyzeResponse, use_json_mode=True, markdown=False)`
      - Do not configure `db` on this post-analyze agent.
      - Temporarily reduce `agent/agno_agent/workflows/post_analyze_workflow.py` to a small compatibility shim whose `PostAnalyzeWorkflow.run()` delegates to `run_post_analyze()`. This keeps the existing runner import testable until Phase 6 performs the allowed runner boot wiring and call-site cleanup.
    - Acceptance criterion:
      - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_post_analyze_internal_followups.py tests/unit/agent/test_agent_handler.py -q`
    - Test files affected:
      - `tests/unit/agent/test_post_analyze_internal_followups.py`
      - `tests/unit/agent/test_agent_handler.py`

13. Delete the remaining agno agent singleton module.
    - Files to change:
      - Delete `agent/agno_agent/agents/__init__.py`
    - What exactly to do:
      - Confirm no source file imports from `agent.agno_agent.agents` after the reminder and post-analyze migrations.
      - Delete `agent/agno_agent/agents/__init__.py`.
      - Do not replace it with a new singleton registry.
    - Acceptance criterion:
      - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/prompt/test_agent_instructions_prompt.py tests/unit/test_reminder_detect_structured_output.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_post_analyze_internal_followups.py -q`
    - Test files affected:
      - `tests/unit/prompt/test_agent_instructions_prompt.py`
      - `tests/unit/test_reminder_detect_structured_output.py`
      - `tests/unit/agent/test_reminder_intent_capability.py`
      - `tests/unit/agent/test_post_analyze_internal_followups.py`

## Phase 6: Wire session.py into runner boot

14. Initialize the shared agno session db at runner boot and switch the post-analyze call to the extracted function.
    - Files to change:
      - Modify `agent/runner/agent_handler.py`
      - Delete `agent/agno_agent/workflows/post_analyze_workflow.py`
    - What exactly to do:
      - Replace `from agent.agno_agent.workflows.post_analyze_workflow import PostAnalyzeWorkflow` with imports for `run_post_analyze` from `agent.agno_agent.runtime.post_analyze` and `initialize_agent_session_db` from `agent.agno_agent.runtime.session`.
      - Remove the module-level `post_analyze_workflow = PostAnalyzeWorkflow()` singleton.
      - At module boot, after DAO/Mongo singletons are created, call `initialize_agent_session_db()` once so the shared `MongoDb` instance is ready before per-turn `_create_agent()` calls.
      - In `_run_post_analyze_background()`, replace `await post_analyze_workflow.run(session_state=context)` with `await run_post_analyze(session_state=context)`.
      - Keep `_run_post_analyze_background()` gating, logging, exception handling, and `mongo.replace_one("relations", ...)` ownership unchanged.
      - Delete `agent/agno_agent/workflows/post_analyze_workflow.py` after the runner import moves to `runtime/post_analyze.py`.
    - Acceptance criterion:
      - Unit tests pass after this step: `.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py tests/unit/runner/test_agent_handler_inflight_interrupt.py tests/unit/runner/test_typed_runtime_events.py tests/unit/agent/test_post_analyze_internal_followups.py tests/unit/agent/test_agent_runtime_construction.py -q`
    - Test files affected:
      - `tests/unit/agent/test_agent_handler.py`
      - `tests/unit/runner/test_agent_handler_inflight_interrupt.py`
      - `tests/unit/runner/test_typed_runtime_events.py`
      - `tests/unit/agent/test_post_analyze_internal_followups.py`
      - `tests/unit/agent/test_agent_runtime_construction.py`

15. Run the final unit-only migration gate.
    - Files to change:
      - No source files; this is the final unit-test gate for the migration branch.
    - What exactly to do:
      - Run the unit tests that cover the changed `agent/agno_agent/` and allowed runner boot surfaces:
        - `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_runtime_envelope.py tests/unit/agent/test_agent_runtime_async_offload.py tests/unit/agent/test_agent_runtime_output_rules.py tests/unit/agent/test_agent_runtime_durable_write_contract.py tests/unit/agent/test_agent_runtime_unknown_tool.py tests/unit/agent/test_agent_runtime_types.py tests/unit/agent/test_event_adapter_routing.py tests/unit/agent/test_chat_response_instructions.py tests/unit/agent/test_reminder_intent_capability.py tests/unit/agent/test_reminder_intent_retry_schema.py tests/unit/agent/test_post_analyze_internal_followups.py tests/unit/agent/test_agent_handler.py tests/unit/runner/test_agent_handler_inflight_interrupt.py tests/unit/runner/test_typed_runtime_events.py tests/unit/prompt/test_agent_instructions_prompt.py tests/unit/test_reminder_detect_structured_output.py -q`
      - Do not add eval, E2E, smoke, or behavior-validation gates in this plan; the approved spec defers those.
    - Acceptance criterion:
      - Unit tests pass after this step with the command above.
    - Test files affected:
      - `tests/unit/agent/test_agent_runtime_construction.py`
      - `tests/unit/agent/test_agent_runtime_envelope.py`
      - `tests/unit/agent/test_agent_runtime_async_offload.py`
      - `tests/unit/agent/test_agent_runtime_output_rules.py`
      - `tests/unit/agent/test_agent_runtime_durable_write_contract.py`
      - `tests/unit/agent/test_agent_runtime_unknown_tool.py`
      - `tests/unit/agent/test_agent_runtime_types.py`
      - `tests/unit/agent/test_event_adapter_routing.py`
      - `tests/unit/agent/test_chat_response_instructions.py`
      - `tests/unit/agent/test_reminder_intent_capability.py`
      - `tests/unit/agent/test_reminder_intent_retry_schema.py`
      - `tests/unit/agent/test_post_analyze_internal_followups.py`
      - `tests/unit/agent/test_agent_handler.py`
      - `tests/unit/runner/test_agent_handler_inflight_interrupt.py`
      - `tests/unit/runner/test_typed_runtime_events.py`
      - `tests/unit/prompt/test_agent_instructions_prompt.py`
      - `tests/unit/test_reminder_detect_structured_output.py`
