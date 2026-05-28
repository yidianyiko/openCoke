# Product Notification Context Leak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop stale product-notification context from turning ordinary reminder queries into no-tool LLM turns.

**Architecture:** Gateways may attach recent product-notification context only when the current user text is plausibly a direct notification reply. Worker runtime treats product-notification metadata as a delivery turn only when the bridge-propagated message type says `product_notification`; normal `user.turn` requests keep reminder and scheduling tools.

**Tech Stack:** TypeScript gateway API with Vitest, Python worker runtime with pytest, GCP compose deploy script.

---

### Task 1: Gateway Context Gate

**Files:**
- Modify: `gateway/packages/api/src/lib/route-message.test.ts`
- Modify: `gateway/packages/api/src/lib/route-message.ts`

- [ ] **Step 1: Write the failing test**

Add a Vitest case proving `我有几个提醒` does not persist or forward `product_notification` even when recent delivered notifications exist for the same business conversation.

- [ ] **Step 2: Run red**

Run:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts -t "does not thread recent product notifications into ordinary reminder list requests" --pool forks --maxWorkers=1
```

Expected: FAIL because current gateway attaches the recent notification context unconditionally.

- [ ] **Step 3: Implement minimal gateway gate**

Add a small text classifier in `route-message.ts` that permits context lookup for short acknowledgement/reference replies such as `确认`, `取消`, `同意`, `这条`, and skips lookup for ordinary reminder/list questions.

- [ ] **Step 4: Run green**

Run the same Vitest command and then the full route-message file:

```bash
pnpm --dir gateway/packages/api exec vitest run src/lib/route-message.test.ts --pool forks --maxWorkers=1
```

### Task 2: Worker Runtime Defense

**Files:**
- Modify: `tests/unit/agent/test_agent_runtime_construction.py`
- Modify: `tests/unit/agent/test_agent_handler.py`
- Modify: `tests/unit/agent/test_chat_response_instructions.py`
- Modify: `agent/runner/agent_handler.py`
- Modify: `agent/agno_agent/runtime/agent_runtime.py`
- Modify: `agent/agno_agent/runtime/chat_response_instructions.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests proving stale `product_notification` metadata without `message_type: product_notification` keeps domain tools, and true delivery turns still hide tools and include the trusted delivery prompt.

- [ ] **Step 2: Run red**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_create_interaction_agent_stale_product_notification_context_keeps_domain_tools tests/unit/agent/test_agent_handler.py::test_agent_handler_extracts_product_notification_metadata_for_runtime tests/unit/agent/test_chat_response_instructions.py::test_prompt_ignores_stale_product_notification_context_without_delivery_message_type -q
```

Expected: FAIL because the runtime currently treats any product-notification metadata as a delivery turn and the handler does not expose message type to runtime metadata.

- [ ] **Step 3: Implement minimal worker defense**

Copy `business_protocol.message_type` into runtime metadata in `agent_handler.py`. In `agent_runtime.py` and `chat_response_instructions.py`, require `message_type == "product_notification"` before disabling tools, resolving notification focus, or injecting trusted delivery instructions.

- [ ] **Step 4: Run green**

Run:

```bash
.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py tests/unit/agent/test_agent_handler.py tests/unit/agent/test_chat_response_instructions.py -q
```

### Task 3: Verify, Commit, Deploy, Smoke

**Files:**
- Commit nested gateway repo changes first.
- Commit root repo changes including the gateway gitlink and this plan.

- [ ] **Step 1: Run repository checks**

Run:

```bash
git diff --check
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

- [ ] **Step 2: Commit**

Commit `gateway/packages/api/src/lib/route-message.ts` and its test inside `gateway/`, then commit worker, docs, tests, and the updated gateway gitlink in the root repo.

- [ ] **Step 3: Deploy**

Run:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

- [ ] **Step 4: Smoke test**

After deploy, verify service health and send or replay an ordinary reminder list request that has recent delivered product notifications in conversation history. Expected result: worker logs show domain tools are available and the user receives a normal reminder/todo answer instead of `系统刚才没能生成回复，请稍后再试一次。`.
