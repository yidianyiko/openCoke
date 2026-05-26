---
title: Coke Unified L3 Transcript and L7 Long-Term Memory Design
date: 2026-05-26
status: draft
owners: Spec B prime lane
scope: L3 chat history and L7 long-term memory
out_of_scope: L4 event log shape; see docs/superpowers/specs/2026-05-26-coke-context-system-design.md
---

# Coke Unified L3 Transcript and L7 Long-Term Memory Design

## 1. L3 Single-Source Decision

Decision: **(c) hybrid with a hard boundary**.

Agno `agent_sessions.runs[*].messages` is the single source for model-visible
L3 chat transcript. Coke keeps `inputmessages` and `outputmessages` as
operational transport stores only: queueing, routing, bridge dispatch, reply
waiting, and rollback detection. They must not be treated as the L3 transcript
for prompt construction after migration.

This is a hybrid storage topology, not a hybrid L3 source. The L3 source is
only Agno S1. The operational queue and dispatch stores remain because current
runtime consumers read fields that are not chat-history semantics.

Current verified facts:

- Agno S1 is already wired to MongoDB `agent_sessions`: `build_agent_session_db`
  constructs `agno.db.mongo.MongoDb(session_collection="agent_sessions")`
  (`agent/agno_agent/runtime/session.py:10-21`).
- The main interaction agent already enables Agno history injection with
  `add_history_to_context=True` and `num_history_messages=20`
  (`agent/agno_agent/runtime/agent_runtime.py:881-890`).
- Agno stores session data, metadata, `runs`, and `summary` on
  `AgentSession` (`.venv/lib/python3.12/site-packages/agno/session/agent.py:14-39`).
  Each run is appended or replaced by `AgentSession.upsert_run`
  (`.../agno/session/agent.py:90-107`).
- Agno history selection comes from `AgentSession.get_messages`, which filters
  by agent/team/status, skips messages already tagged `from_history`, supports
  `limit` and `last_n_runs`, preserves at most one system message in limit
  mode, and removes leading tool messages (`.../agno/session/agent.py:115-225`).
- `AgentSession.get_chat_history` is a user/assistant helper over
  `get_messages(skip_roles=["system", "tool"])`
  (`.../agno/session/agent.py:227-237`).
- Agno injects history only when `add_history_to_context` is true, a session is
  present, and the input does not already contain history; it calls
  `session.get_messages(last_n_runs=agent.num_history_runs,
  limit=agent.num_history_messages, ...)` and tags injected copies
  `from_history=True` (`.../agno/agent/_messages.py:1584-1642`).
- If both `num_history_messages` and `num_history_runs` are set, Agno warns and
  uses runs; if neither is set, it defaults to `num_history_runs=3`
  (`.../agno/agent/agent.py:127-133`, `.../agno/agent/agent.py:539-548`).
- Coke still derives rendered transcript strings from legacy conversation
  history: `agent/runner/context.py` slices the last 15 messages into
  `chat_history_str` (`agent/runner/context.py:333-366`), and
  `agent/runner/message_history.py` renders a six-message
  `recent_chat_history` string (`agent/runner/message_history.py:82-129`).
  `agent/runner/agent_handler.py` writes that value into runtime context
  (`agent/runner/agent_handler.py:383-389`).

Operational consumers that must be preserved:

- Queue acquisition reads pending `inputmessages` via
  `read_top_inputmessages` (`entity/message.py:22-36`,
  `agent/runner/message_processor.py:125-132`).
- Per-conversation batching reads `inputmessages` via `read_all_inputmessages`
  (`entity/message.py:79-87`, `agent/runner/message_processor.py:283-290`).
- Business request/response routing reads `metadata.business_protocol` from
  the top input message, including `delivery_mode`,
  `business_conversation_key`, `gateway_conversation_id`, and
  `causal_inbound_event_id`
  (`agent/runner/message_processor.py:320-373`,
  `agent/runner/message_processor.py:420-488`).
- Rollback detection reads `inputmessages`, excludes product-notification
  messages, and compares message positions
  (`agent/runner/rollback_detection.py:6-67`).
- Bridge outbound dispatch claims and finalizes `outputmessages`
  (`connector/clawscale_bridge/output_dispatcher.py:62-88`).
- Synchronous bridge reply waiting polls and consumes `outputmessages`
  (`connector/clawscale_bridge/reply_waiter.py:44-112`).
- Gateway product-notification context is sourced from the gateway database and
  attached as inbound metadata, not from chat transcript
  (`gateway/packages/api/src/lib/route-message.ts:105-112`,
  `gateway/packages/api/src/lib/route-message.ts:397-413`,
  `gateway/packages/api/src/lib/route-message.ts:506-508`).
- The bridge preserves that metadata into Mongo `inputmessages`
  (`connector/clawscale_bridge/message_gateway.py:124-163`,
  `connector/clawscale_bridge/message_gateway.py:206-210`), and the runtime
  copies `metadata.product_notification` into runtime metadata
  (`agent/runner/agent_handler.py:249-256`).

Migration rule: remove prompt dependence on Coke-rendered `recent_chat_history`
only after the affected prompt/capability call sites have an Agno S1 or L7
replacement. Do not delete `inputmessages`/`outputmessages`; they are not L3
after this boundary, but they are still operationally authoritative.

L4 boundary: event causality, task state transitions, product-action events,
and notification lifecycle are not decided here. L4 belongs to Spec A.

## 2. L7 Long-Term Memory Ontology

L7 memory is not transcript. It contains durable, scoped facts that should
survive the short L3 window and should be injected as trusted context only when
their source, scope, and decay state allow it.

Canonical entry shape:

```yaml
memory_id: string
kind: user_preference | agent_commitment | accepted_fact | learned_style
body: string
owner:
  type: user | character | system | agent
  id: string
scope:
  level: per_user | per_conversation | per_character
  user_id: string?
  character_id: string?
  platform_route: string?
  conversation_id: string?
source:
  layer: L3 | L4 | tool_result | operator_seed | import
  evidence_refs: [string]
trust:
  level: explicit_user | tool_verified | agent_inferred | operator_seeded
  writable_by: runtime_memory_writer | operator | migration
decay:
  state: active | cooling | dormant | superseded | deleted
  activation_score: number
  last_activated_at: timestamp?
  expires_at: timestamp?
version:
  created_at: timestamp
  updated_at: timestamp
  supersedes: string?
```

Memory kinds:

- `user_preference`: stable user likes, dislikes, constraints, language
  preferences, notification preferences, and interaction preferences. These
  need high protection against prompt injection because user text can ask the
  agent to remember hostile instructions.
- `agent_commitment`: commitments the assistant made and should honor later,
  such as "I will remind you after the package ships." These are scoped to the
  conversation unless explicitly promoted.
- `accepted_fact`: facts accepted by a trusted tool result, operator seed, or
  explicit user correction. Product notification fields are not L7 by default;
  if they become memory, the source must point to L4/tool evidence.
- `learned_style`: durable style adaptation, such as preferred brevity or
  language. This kind is low-authority: it may shape tone but cannot override
  tool results, safety policy, product state, or explicit current user intent.

## 3. Storage Choice

Options:

- Reuse `embeddings` as the only memory store.
  Current code already queries MongoDB `embeddings` for
  `character_global`, `character_private`, `user`, and
  `character_knowledge` rows (`agent/agno_agent/capabilities/context_retrieve.py:79-118`).
  It also performs vector and keyword retrieval over `embeddings`
  (`agent/agno_agent/capabilities/context_retrieve.py:240-308`) and has a
  separate `chat_history` retrieval path keyed by `metadata.type="chat_history"`
  (`agent/agno_agent/capabilities/context_retrieve.py:311-355`). This option
  is cheap, but it makes vector rows the system of record for lifecycle,
  trust, scope, and decay. That overfits search infrastructure to memory
  governance.
- Use a sibling Mongo collection as the memory source of truth, with optional
  vector shadow rows in `embeddings`.
  This supports the ontology above, clear ownership, conflict resolution,
  auditability, and decay while reusing the existing vector retrieval path for
  searchable bodies.
- Use Agno built-in memory directly.
  Agno provides `MemoryManager`, DB-backed `UserMemory`, and retrieval methods
  (`last_n`, `first_n`, `agentic`)
  (`.venv/lib/python3.12/site-packages/agno/memory/manager.py:45-98`,
  `.../agno/memory/manager.py:588-705`). Its schema is intentionally simple:
  `UserMemory` stores `memory`, `memory_id`, `topics`, `user_id`, input text,
  timestamps, feedback, `agent_id`, and `team_id`
  (`.venv/lib/python3.12/site-packages/agno/db/schemas/memory.py:8-45`).
  Agno's default table name is `agno_memories`
  (`.venv/lib/python3.12/site-packages/agno/db/base.py:36-60`), and DB
  methods search by user/agent/team/topics/content
  (`.../agno/db/base.py:225-267`). This does not carry Coke's required owner,
  scope, trust, evidence, or decay fields. Agno also has no installed
  `MemoryTopic` class in this environment; topics are a list field, not an
  ontology.

Recommendation: **create a sibling source-of-truth collection**, for example
`memory_entries`, and write vector shadow rows into `embeddings` with
`metadata.type="memory_entry"`, `memory_id`, `kind`, `scope.level`,
`uid`, `cid`, `platform_route`, and `conversation_id`.

Agno built-in memory should be treated as reference material, not the Coke L7
source of truth. It may be reused later as an adapter only if the Coke schema
remains authoritative.

## 4. Retrieval and Always-Loaded Subset

Always-loaded subset:

- Maximum 800 input tokens for the full always-loaded memory block.
- Maximum 8 entries.
- Priority order: active explicit user preferences, active agent commitments,
  active accepted facts, then learned style.
- No dormant, superseded, deleted, or low-confidence inferred entries in the
  always-loaded subset.

Searchable subset:

- Retrieve at most 5 entries per turn, with a default 600-token cap.
- Search over vector shadow rows plus metadata filters from the sibling
  memory source.
- Require namespace filters before semantic similarity: user id, character id,
  platform route, conversation id when scoped.
- Return structured memory records to prompt assembly; do not return raw vector
  documents as prompt text.

Prompt integration:

```xml
<trusted layer="memory">
  <entry kind="user_preference" scope="per_user" trust="explicit_user" id="...">
    ...
  </entry>
</trusted>
```

This block follows Spec A's trusted-layer direction. It is above transcript in
authority, below current tool results and L4 event state, and must never be
mixed into free-form `<conversation>` text. If a current user message conflicts
with a memory, the conflict is surfaced to the memory writer after the run; the
model should not silently rewrite durable memory.

## 5. Write Triggers and Decay

Writers:

- A deterministic post-run memory writer owns L7 writes.
- The model may propose candidate memories, but the runtime writer validates
  schema, scope, evidence, trust level, and conflict handling before writing.
- Operators and migration scripts may seed `operator_seeded` memory entries.

Write triggers:

- Explicit user request to remember, forget, update, or prefer something.
- Explicit user correction of a durable fact or preference.
- Repeated consistent behavior across multiple turns that qualifies as
  `learned_style`; one turn is not enough unless the user states it directly.
- Assistant commitments that survive beyond the current run.
- Tool-verified or L4-verified facts that should be useful later; product
  event state itself remains L4 and is out of scope here.
- L3 pre-compaction flush: before Agno's configured history window would lose
  relevant turns, run extraction over the outgoing window and write only
  memory-worthy entries.

Trust levels:

- `explicit_user`: user directly stated the memory or correction.
- `tool_verified`: came from a trusted tool result or L4 event reference.
- `operator_seeded`: came from an admin import or seed.
- `agent_inferred`: inferred by model/rules; never allowed to override
  explicit current user intent, tool state, or higher-trust memories.

Decay:

- New entries start `active` with an activation score based on trust and kind.
- Retrieval or explicit confirmation increases activation.
- Time without activation moves entries from `active` to `cooling` to
  `dormant`.
- Contradiction creates a new version and marks the old entry `superseded`.
- Deletion marks `deleted` first; physical purge is governed by retention and
  privacy policy.

Agno primitives:

- Agno provides session summarization via `SessionSummary` and
  `SessionSummaryManager`; summaries are generated from `session.get_messages`
  (`.venv/lib/python3.12/site-packages/agno/session/summary.py:21-42`,
  `.../agno/session/summary.py:61-75`,
  `.../agno/session/summary.py:139-164`,
  `.../agno/session/summary.py:212-246`).
- Agno's memory manager can add/update/delete user memories with model tool
  calls (`.../agno/memory/manager.py:969-1024`,
  `.../agno/memory/manager.py:1040-1108`,
  `.../agno/memory/manager.py:1326-1426`).
- Agno has a summarization optimization strategy that compresses multiple
  `UserMemory` rows into one while preserving topics/user id
  (`.venv/lib/python3.12/site-packages/agno/memory/strategies/summarize.py:15-42`,
  `.../agno/memory/strategies/summarize.py:44-119`).

These are useful references, but Coke should not delegate memory writes
directly to Agno's generic memory prompt because Coke needs explicit scope,
trust, evidence, and decay controls.

Eval coverage, if added during implementation, should be a focused 30-50 case
subset covering L3 source removal, product-notification context preservation,
memory write triggers, namespace filtering, and decay conflict behavior. Do
not require a full corpus run for the first storage migration.

## 6. Namespacing

Namespace levels:

- `per_user`: applies across a user's conversations with a character unless a
  stricter route says otherwise. Example: language preference.
- `per_conversation`: applies only to `conversation_id = user_id x
  character_id x platform_route`. Example: an assistant commitment made in one
  business route.
- `per_character`: applies to character-global behavior or knowledge. It must
  not contain private user facts unless separately scoped per user.

Resolution:

1. Load matching `per_conversation` entries.
2. Load matching `per_user` entries for the same user and character.
3. Load allowed `per_character` entries.
4. On conflict, more specific scope wins, then higher trust wins, then newer
   active version wins.

Prompt-injection guard:

- User text cannot choose its own namespace. The writer derives namespace from
  authenticated runtime ids and platform route.
- Retrieved memory bodies are data, not instructions. The prompt block must
  identify kind, scope, trust, and id.
- A memory cannot expand scope from per-conversation to per-user without an
  explicit user or operator signal.

## 7. Migration Sequencing

Deploy without freezing the system:

1. Add the sibling memory collection and indexes without changing prompt
   assembly.
2. Start dual-writing new memory entries and vector shadow rows for high-trust
   triggers only.
3. Add read-only memory retrieval behind a feature flag; render it only in
   `<trusted layer="memory">`.
4. Remove prompt dependence on Coke-rendered `recent_chat_history` after each
   affected prompt/capability has an Agno S1 or L7 replacement.
5. Keep `inputmessages` and `outputmessages` unchanged for queueing, routing,
   rollback detection, bridge dispatch, and reply waiting.
6. Backfill only from high-confidence existing rows. Existing
   `embeddings.metadata.type in {"user", "character_private"}` may seed
   candidate memories after validation. Existing `chat_history` vector rows and
   Mongo transcripts must not be bulk-promoted into memory.
7. Leave existing `inputmessages` and `outputmessages` data in place under the
   current operational retention policy. Do not rewrite historical operational
   rows as memory.

Rollout validation should compare:

- Agno S1 transcript continuity across the 20-message configured window.
- No loss of product-notification metadata through gateway, bridge, and runtime
  metadata paths.
- L7 retrieval respects user, conversation, character, and platform-route
  filters.
- L7 memory does not override current tool/L4 facts.

## 8. Open Questions

- Should short conversation-specific commitments also be cached in
  `AgentSession.session_data`, or should the sibling memory collection be the
  only L7 source even for per-conversation memory?
- What exact retention and user deletion semantics are required for memories
  derived from conversation text versus operator-seeded data?
- Should `agent_inferred` memories ever be always-loaded, or should they always
  require retrieval plus confirmation?
- Who approves promotion from `per_conversation` to `per_user` when the user
  implies a stable preference but does not say "remember"?
- How should memory conflict UI or operator audit work when two trusted sources
  disagree?
- Until L4 exists, which product-action facts are safe to write as L7 accepted
  facts, and which must remain current-turn metadata only?
- What is the exact token budget split between always-loaded memory, retrieved
  memory, current tool state, and Agno S1 history for small-context models?

## 9. Comparison Appendix

| System | Primary sources | Write triggers | Retrieval | Eviction / decay | Namespacing | Prompt-injection posture |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code | Anthropic docs: `https://code.claude.com/docs/en/memory` | Official docs name the durable file surface `CLAUDE.md`; it is the Claude Code analogue of project-scoped `MEMORY.md`. Auto memory is written from corrections and preferences; active conversation context remains separate from durable memory. | `CLAUDE.md` and auto memory load at session start; `#` shortcut and `/memory` help edit. | No automatic semantic decay for `CLAUDE.md` in the cited docs; auto memory loads with documented size limits. | Org, project, user, local project, and repository-scoped auto memory. | File-backed memory is inspectable, but Claude treats memory as context rather than enforced configuration, so imported text still needs trust boundaries. |
| Mem0 | Mem0 docs: `https://docs.mem0.ai/overview`, `https://docs.mem0.ai/platform/quickstart`, `https://docs.mem0.ai/core-concepts/memory-types` | API writes from conversations or app events; memories can be user, agent, session/run, or org scoped. | Semantic memory search through SDK/API with filters. | Docs describe managed memory updates and lifecycle APIs; application still chooses retention and delete policy. | User, agent, session/run, org/project style scopes. | Scoping filters reduce cross-user bleed; applications still need to treat recalled memory as data and validate write sources. |
| ChatGPT user memory | OpenAI Help: `https://help.openai.com/en/articles/8590148-memory-faq` | User asks ChatGPT to remember, or ChatGPT saves details inferred as useful when memory is enabled. | Saved memories and referenced chat history can be used to personalize future chats. | Users can view, delete, clear memories, and turn saved memory/reference chat history on or off. | Account-level personalization, not project-specific by default. | User-visible controls and deletion reduce persistence risk, but saved memory must be subordinate to current instructions and safety policy. |
| Letta / MemGPT | Letta docs: `https://docs.letta.com/guides/core-concepts/stateful-agents`, `https://docs.letta.com/guides/core-concepts/memory/memory-blocks`, `https://docs.letta.com/guides/core-concepts/memory/archival-memory`, `https://docs.letta.com/guides/core-concepts/memory/context-hierarchy` | Agent writes to core memory blocks and archival memory through memory tools. | Core memory blocks are always in context; archival memory is searched/retrieved; conversation history supports past interaction lookup. | Context pressure pushes information out of core memory into archival/recall structures; applications govern deletion. | Memory blocks, agents, humans/personas, shared blocks, archival stores. | Tool-mediated writes and explicit memory blocks make memory inspectable, but agents can still write bad memories without policy gates. |
| OpenClaw-style layered memory | OpenClaw docs: `https://docs.openclaw.ai/concepts/memory`, `https://docs.openclaw.ai/concepts/compaction`, `https://docs.openclaw.ai/concepts/agent-workspace`; supplementary guide: `https://openclawcrew.com/guides/memory` | Explicit durable notes, daily memory logs, action-sensitive notes, inferred short-lived commitments, and pre-compaction memory flush. | Always-loaded durable notes plus `memory_search` hybrid retrieval when embeddings are configured. | Public docs cover pre-compaction flush, action boundaries, expiry conditions, and freshness tracking; activation/decay is the broader layered-memory pattern named in this review directive. | Agent workspace, durable memory files, daily logs, agent/channel-scoped commitments. | Durable files are auditable; semantic retrieval and inferred commitments need trust labels and namespace filters to resist injection. |
| Manus context engineering | Manus blog: `https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus` | The system externalizes durable state and compresses context through offloading and reduction. | Retrieval and caching bring back only relevant context; isolation separates contexts for different work. | Reduction summarizes/compacts; offloading moves state out of model context; caching avoids repeated context costs. | Isolation keeps tool/task contexts separated. | The five disciplines reduce prompt bloat and contamination, but retrieved/offloaded content still needs source and trust metadata. |
