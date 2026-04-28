# Task: Poke Architecture Reconstruction Archive

- Status: Complete
- Owner: Codex
- Date: 2026-04-23

## Goal

Produce one task-local archive that reconstructs Poke's architecture and prompt
design from public evidence so Coke can use it as a direct refactor reference.

## Scope

- In scope:
  - public Poke architecture signals from docs, SDKs, CLI bundles, status
    pages, release notes, FAQs, and package metadata
  - public prompt-leak mirrors and third-party reverse-engineering material
  - confidence grading for each major claim
  - concrete guidance for what Coke should borrow and what Coke should not copy
- Out of scope:
  - implementing an OpenPoke clone in this repository
  - unsupported claims that cannot be tied to public evidence
  - a general product strategy memo not tied to Coke's refactor

## Touched Surfaces

- repo-os

## Acceptance Criteria

- One file in `tasks/` acts as the primary archive for future Coke refactor
  work.
- The archive separates official facts, official-artifact reverse-engineering,
  third-party reconstruction, and weak signals.
- The archive includes a Poke architecture reconstruction, prompt findings,
  evolution timeline, and a Coke-specific recommendation section.
- The archive includes a source index with direct links.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS structure test passes after adding the new task
  and plan.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and routing checks pass.

## Notes

### How To Use This Archive

Read this file when deciding how far Coke's next refactor should go beyond the
current `PrepareWorkflow -> StreamingChatWorkflow -> PostAnalyzeWorkflow`
pipeline. This is not a generic competitor note. It is a reconstruction of
Poke's likely runtime boundaries and product-control-plane boundaries, written
specifically to support Coke's agent redesign.

The archive answers five questions:

1. What can be stated as fact about Poke today?
2. What can be inferred with high confidence from Poke's published artifacts?
3. What does the leaked prompt material suggest about its internal split
   between "Poke" and execution workers?
4. Which third-party reconstructions are actually consistent with the evidence?
5. What should Coke borrow, and what should Coke avoid copying?

### Confidence Model

Every important claim in this document uses one or more evidence classes:

- `A. Official statement`
  - Official docs, release notes, FAQ, status pages, marketing pages.
- `B. Official published artifact`
  - Published npm/PyPI packages, CLI bundles, SDK typings, package metadata, and
    other artifacts shipped by Poke itself.
- `C. Public leaked artifact with cross-checks`
  - Publicly mirrored prompt text that is not officially confirmed but aligns
    with product behavior and official artifacts.
- `D. Third-party reconstruction`
  - Community bridge projects, reverse-engineering writeups, open-source clones,
    and architecture explanations based on observation.
- `E. Weak signal`
  - Single-source claims or claims that remain plausible but unverified.

Rules used in this archive:

- Only `A` and `B` evidence is treated as directly actionable fact.
- `C` evidence is used for structure, agent roles, and prompt behavior, but not
  for exact implementation claims unless `A` or `B` corroborates it.
- `D` evidence is only used when it matches `A`, `B`, or `C`.
- `E` evidence is recorded only when useful as a watchlist item.

### Executive Summary

The shortest useful summary is this:

- Poke is no longer just "a chat assistant in texts." Public materials show a
  layered system with messaging/API ingress, a user-facing agent, an execution
  agent or subagent runtime, native primitives, MCP integrations, automations,
  and a separate control plane for Connections, API keys, Recipes, and tunnels.
- Official MCP docs explicitly distinguish the `user-facing agent` from the
  `execution agent`. This is the strongest public architecture signal. `A`
- Official SDK and CLI artifacts show a separate control plane with device-code
  login, MCP connection management, tunnel activation, tool syncing, recipe
  creation, and webhook ingress. `B`
- Public leaked prompt text is internally consistent with the official docs and
  package behavior: there is a "Poke" personality/orchestration layer and a
  separate execution engine that does not talk to the user directly. `B+C`
- Third-party OpenPoke reconstruction is directionally right on the major
  boundaries: interaction agent, persistent execution agents, trigger runtime,
  inbox monitor, and layered memory. Some details remain speculative. `C+D`

For Coke, the main takeaway is not "copy Poke's consumer platform shell." The
main takeaway is to stop letting one runtime path own orchestration, user UX,
execution, and side effects at the same time.

### Coke Baseline

The current Coke baseline matters because Poke should only be used as a
reference where it actually improves Coke's next architecture.

Current Coke facts:

- Phase 1 is implemented as a personal supervision companion with reminders,
  proactive follow-up, and personal-channel delivery. `docs/roadmap.md`
- The production runtime is still a shared turn pipeline:
  `PrepareWorkflow -> StreamingChatWorkflow -> PostAnalyzeWorkflow`, invoked for
  both user turns and deferred actions. `docs/architecture.md`
- `agent_runner.py` still boots three concerns together:
  message workers, deferred-action scheduler/executor, and background handler.
  [agent/runner/agent_runner.py](/data/projects/coke/agent/runner/agent_runner.py:39)
- `handle_message()` remains the effective orchestration center for lock
  renewal, rollback detection, streaming, moderation, and post-analysis.
  [agent/runner/agent_handler.py](/data/projects/coke/agent/runner/agent_handler.py:333)
- `PrepareWorkflow` already contains a lightweight orchestration layer via
  `OrchestratorAgent`, but that layer still writes into a giant mutable
  `session_state` dict rather than explicit subsystems.
  [agent/agno_agent/workflows/prepare_workflow.py](/data/projects/coke/agent/agno_agent/workflows/prepare_workflow.py:64)
  [agent/runner/context.py](/data/projects/coke/agent/runner/context.py:179)

This matters because Coke is already strong in one area Poke also values:
durable reminders / deferred actions as first-class runtime state. Coke is weak
where Poke appears stronger: clear separation between user-facing orchestration,
execution workers, integrations, and control plane.

## Reconstruction

### 1. Public Product Shape

What Poke publicly presents today:

- Messaging-first assistant in `iMessage`, `Telegram`, and `SMS`.
  `A`  
  Source: https://poke.com/docs
- Older developer docs still mention `WhatsApp`, and release notes explain that
  Telegram was introduced as an alternative while WhatsApp was unavailable
  outside Italy and Brazil. This indicates a real channel abstraction rather
  than a single hard-coded surface. `A`
  Sources:
  - https://poke.com/docs/developers/introduction
  - https://poke.com/docs/release-notes
- Built-in primitives are `email`, `calendar`, `reminders`, and `web search`,
  plus integrations. `A`
  Source: https://poke.com/docs
- The public site now also foregrounds `Recipes`, which is a packaging layer
  above the assistant runtime. `A`
  Sources:
  - https://poke.com/
  - https://poke.com/docs/creating-recipes

At the product level, Poke already looks like:

```text
Messaging channels + API ingress
    -> Poke conversation layer
    -> execution / integrations / automations
    -> packaging + control plane (Connections, Recipes, API keys)
```

### 2. Official Architecture Signals

The most important official signal is in Poke's MCP client specification.

Confirmed from docs:

- Poke implements only the `tools` capability of MCP. It does not support
  `prompts`, `resources`, `roots`, `elicitation`, or `sampling`. `A`
- Poke discovers tools at connection time and caches tool schemas for the life
  of the connection. Tools do not hot-refresh automatically. `A`
- The MCP server `instructions` field is passed to the `execution agent`. `A`
- Tool results are then returned to the `user-facing agent` for synthesis. `A`
- Transport preference is `Streamable HTTP`; Poke falls back to `SSE` on
  non-authentication failures for legacy support. `A`
- Timeouts default to 30 seconds, and auth is API key or OAuth 2.0 PKCE, with
  tokens encrypted at rest. `A`

Source:
https://poke.com/docs/developers/integrations/mcp-client-specification

This is enough to establish that Poke is not a single monolithic agent.
Officially, there are at least two roles:

```text
user-facing agent
    -> handles user-visible conversation and tool-result synthesis

execution agent
    -> receives MCP server instructions and executes work
```

That split matches later evidence from leaked prompts and third-party
reconstructions.

### 3. Official Control Plane Signals

Published docs and packages show a separate control plane around the assistant:

- `Connections` manages integrations. Users can add pre-built integrations or a
  custom MCP server, then refresh or disconnect them. `A`
  Source: https://poke.com/docs/managing-integrations
- `Recipes` package prompts, integrations, and distribution. The docs treat
  Recipes as a distinct share/install surface, not just a saved prompt. `A`
  Source: https://poke.com/docs/creating-recipes
- Public package docs expose `API keys`, `webhooks`, and programmatic message
  ingress. `A+B`
  Source: https://pypi.org/project/poke/

The published Node CLI bundle makes this even clearer. Reverse-engineering the
`poke@0.4.2` npm package shows these behaviors and endpoints:

- `poke login` uses device-code login via:
  - `POST /cli-auth/code`
  - `poll /cli-auth/poll/<deviceCode>` `B`
- `poke whoami` reads `GET /user/profile` with stored auth. `B`
- `poke mcp add` creates a remote MCP connection through
  `POST /mcp/connections/cli`. `B`
- `poke tunnel` also creates a connection through the same control plane, then
  activates it with:
  - `POST /mcp/connections/:id/activate-tunnel`
  - `POST /mcp/connections/:id/sync-tools`
  - `POST /mcp/connections/:id/create-recipe`
  - `DELETE /mcp/connections/:id` on cleanup `B`
- Tool syncing runs on an interval that defaults to five minutes. `B`

These findings came from the published npm tarball:

- package page: https://www.npmjs.com/package/poke
- inspected package version: `0.4.2`

The key takeaway is structural:

```text
Poke runtime
    !=
Poke control plane

The control plane owns auth, connections, tunnel lifecycle, recipe creation,
tool refresh, and API-key governed ingress.
```

### 4. Programmatic Ingress And Webhooks

Poke exposes more than messaging channels.

From the official Python SDK page:

- `send_message()` sends text into the user-facing assistant. `A`
- `create_webhook()` returns a `triggerId`, `webhookUrl`, and `webhookToken`.
  `A`
- Public examples use
  `https://poke.com/api/v1/inbound/webhook` as the webhook endpoint. `A`
- The SDK default base URL is `https://poke.com/api/v1`. `A`

Source: https://pypi.org/project/poke/

From the Node SDK bundle:

- `sendMessage()` posts to `/inbound/api-message`. `B`
- `createWebhook()` posts to `/api-keys/webhook`. `B`
- `sendWebhook()` POSTs user data to the webhook URL using the returned bearer
  token. `B`

This is important for Coke because it shows how Poke turns "external event ->
assistant" into a first-class surface rather than a hidden product hack.

### 5. Tunnel Architecture

The most technically revealing artifact is the published Node CLI bundle.

The tunnel implementation is not a generic "open localhost to the internet"
wrapper. The published code shows:

- A WebSocket upstream URL shaped like `/piko/v1/upstream/<endpointId>`. `B`
- A custom framed multiplexed stream transport with message types:
  `Data`, `WindowUpdate`, `Ping`, `GoAway`. `B`
- Stream flags:
  `SYN`, `ACK`, `FIN`, `RST`. `B`
- Connection keepalive, reconnection backoff, stream proxying, and local HTTP
  forwarding into the user's MCP server. `B`

That means the tunnel layer likely looks something like this:

```text
local MCP server (localhost)
    <- HTTP proxying over multiplexed streams ->
Poke upstream tunnel service
    <- control-plane registration / auth ->
Connections API
```

This custom stream layer is close in spirit to `yamux`-style multiplexing,
though the public artifact does not name it explicitly. Treat that protocol
family comparison as inference, not fact. `B+E`

### 6. Public Prompt Leak Findings

There are multiple public mirrors of leaked prompt text associated with Poke.
The most useful current public mirror is:

- GitHub repository folder with `Poke agent.txt` plus `Poke_p1.txt` through
  `Poke_p6.txt`:  
  https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/tree/main/Poke

Direct raw files used here:

- execution-oriented prompt:
  https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke%20agent.txt
- interaction-oriented prompt fragments:
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p1.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p2.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p3.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p4.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p5.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p6.txt

These are not officially authenticated, so they remain `C`, not `A` or `B`.
However, they align unusually well with the official docs and published package
behavior.

#### 6.1 What The Leaked Prompts Suggest

The leaked material strongly suggests a two-layer prompt stack:

- `Poke` as the user-facing layer
  - witty, warm, human texting style
  - owns message formatting, reactions, approvals, and the "single unified
    entity" illusion
  - delegates work to agents without exposing those agents to the user
- an `execution engine`
  - does not talk to the user directly
  - seeks maximum parallelism
  - uses subagents and tasks
  - manages triggers, drafts, integrations, and search

Short, compliant excerpts that capture the architecture:

- execution prompt: it calls itself the `"execution engine"` and says it does
  not have direct access to the user. `C`
- official MCP docs separately refer to an `execution agent` and a
  `user-facing agent`. `A`
- interaction prompt fragments repeatedly say to maintain the illusion of a
  single unified entity and never expose tools or agents. `C`

The structure is consistent enough to reconstruct this boundary:

```text
Poke (interaction layer)
    - user-visible persona
    - approvals
    - message formatting
    - draft display
    - notification gating
    - "single entity" illusion

Execution engine
    - task execution
    - tool calls
    - search
    - integrations
    - triggers / reminders / automations
    - browser use when absolutely necessary
```

#### 6.2 Prompt-Level Behavior That Matters Architecturally

Important patterns exposed by the leaked prompts:

- Parallelism is a first-class instruction in both the interaction and execution
  layers. They are told to split independent work and fan it out concurrently.
  `C`
- Email and calendar actions require user confirmation before send/update/delete
  execution, and drafts are displayed as a separate surface. `C`
- Trigger execution can be canceled silently with a `wait` tool if it appears to
  be a false positive. `C`
- The prompt distinguishes different inbound message classes:
  user, agent, triggered automation, email, system, reminder, summary, memory.
  `C`
- Memory is summarized automatically and injected back as context rather than
  exposed as a tool. `C`
- The leaked prompt explicitly mentions first-party integrations like `Notion`,
  `Linear`, `Vercel`, `Intercom`, and `Sentry`, and tells the assistant to
  assume custom MCP integrations are available when the user asks for them. `C`
- One fragment says bad trigger activations are decided by a "very small model."
  This is a useful but still unverified signal that Poke may use cheaper models
  for guard or routing flows. `C`

#### 6.3 Trustworthiness Of The Prompt Leak

Why the leaked prompt material is useful despite not being official:

- It describes an interaction/execution split that the official MCP spec also
  exposes. `A+C`
- It describes integrations and triggers in ways that match public docs,
  release notes, and SDK behavior. `A+B+C`
- It describes public channel mix and membership/onboarding details that align
  with release notes and FAQs. `A+C`
- Third-party OpenPoke reconstruction independently arrived at the same major
  architecture based on both usage and leaked prompt analysis. `C+D`

What still should not be treated as hard fact:

- exact internal prompt wording
- exact subagent lifecycle rules
- exact model routing and cost optimization implementation
- exact persistence schemas behind memory and triggers

### 7. Third-Party Reverse-Engineering

#### 7.1 OpenPoke

OpenPoke is the strongest third-party reconstruction because its author
explicitly ties the design to two inputs: heavy Poke usage and leaked prompt
analysis.

Sources:

- article:
  https://www.shloked.com/writing/openpoke
- repo:
  https://github.com/shlokkhemani/openpoke

What OpenPoke claims:

- Interaction Agent owns user conversation, context, delegation, and
  personality.
- Execution Agents are spawned per domain task and can persist across time.
- Execution Agents can be reused for later follow-ups in the same work thread.
- Trigger runtime belongs to the agent that created the trigger.
- A background email monitor classifies important emails and pushes them back to
  the interaction layer.
- Memory is multi-tiered: recent context, compressed summaries, durable agent
  logs, and email as external memory.

What is likely right:

- the interaction/execution split `C+D`
- prompt/personality separated from execution `A+C+D`
- parallel worker fan-out for independent tasks `C+D`
- durable trigger/automation runtime `A+C+D`
- layered memory with conversation summary plus execution-local continuity
  `C+D`

What remains interpretive:

- exact persistence model for execution agents
- exact thresholds, scheduler cadence, and monitor topology
- how much of OpenPoke is Poke versus Shlok's own best-effort design

#### 7.2 Poke Gate

Poke Gate is a community project, not affiliated with Poke:

- https://poke-gate.fka.dev/

It is still useful because it exposes how independent builders are reasoning
about Poke's tunnel and local-agent surfaces.

Useful third-party signals:

- It positions itself as an MCP tunnel between a local machine and Poke.
  `D`
- It assumes a two-way relationship: Poke pulls from your machine when asked,
  and your machine pushes to Poke via scheduled agents. `D`
- It uses the Poke SDK tunnel layer rather than inventing a fake integration
  model. `D`
- Its docs show access modes, approval flows, and HMAC approval tokens for
  risky actions. Those are Poke Gate's design choices, not proof about Poke's
  own internal security model. `D`

Why it matters anyway:

- It confirms that the public Poke tunnel surface is robust enough for community
  tooling.
- It reinforces the interpretation that Poke's integrations/control plane are
  meant to be platform primitives, not one-off extensions.

### 8. Evolution Timeline

#### 2025-09-08: public launch

- Public launch press release positions Poke as a messaging-native assistant
  that connects email, calendar, and task execution through conversation.
  `A`
  Source:
  https://www.webwire.com/ViewPressRel.asp?aId=343533

#### 2025-11-03: integration library refresh

- Release notes show a redesigned integration library and new first-party
  categories:
  productivity, developer, and business integrations. `A`
- Same notes mention:
  - fewer emojis
  - fixes for approval loops while drafting emails
  - fixes for failed web searches

Source: https://poke.com/docs/release-notes

Interpretation:

- by November 2025 Poke already had enough integration usage to justify a
  visible library redesign
- approval loops were a real enough problem to appear in public notes, which
  lines up with the leaked prompt's careful approval rules

#### 2026-01 to 2026-03: ops and integration maturity

- Status page records incidents for:
  - email functionality
  - calendar timezone issues
  - Todoist MCP transport issues
  - increased subagent failure rate
  - increased MCP failure rate
  - iMessage delivery / lag / group-chat issues
  `A`
  Source: https://status.poke.com/history

Interpretation:

- Poke tracks subagents and MCP integrations as meaningful operational
  components, not just hidden implementation details.
- Messaging channels are still a distinct failure domain.
- Calendar timezone handling is hard enough to show up as a production concern.

#### 2026-02-02: Telegram fallback and charts/tables

- Release notes add Telegram as an alternative while WhatsApp is temporarily
  unavailable except in Italy and Brazil. `A`
- The same release adds chart/table generation and fixes automation formatting
  and timezone/day-of-week bugs. `A`

Interpretation:

- channel abstraction is real
- automations are already first-class enough to need formatting fixes

#### 2026-03-19: Recipes

- Release notes announce `Poke Recipes`. `A`

Interpretation:

- the packaging/distribution layer is now important enough to headline the
  release stream

### 9. Reconstructed Architecture

The most defensible reconstruction, combining `A+B+C+D` evidence, looks like
this:

```text
                           +-----------------------+
                           |    Control Plane      |
                           | Connections           |
                           | API Keys              |
                           | Recipes               |
                           | OAuth / device login  |
                           | tunnel lifecycle      |
                           +-----------+-----------+
                                       |
                                       v
+------------------+         +-----------------------+
| Messaging/API    |         | User-Facing Poke      |
| Ingress          +-------->+ interaction layer     |
| iMessage/SMS/... |         | persona + approvals   |
| /inbound/*       |         | result synthesis      |
+------------------+         | draft display         |
                             +-----------+-----------+
                                         |
                            delegates via tasks / agents
                                         |
                                         v
                             +-----------------------+
                             | Execution Runtime     |
                             | execution agent       |
                             | subagents / workers   |
                             | search fan-out        |
                             | browser fallback      |
                             +-----+-----+-----+-----+
                                   |     |     |
                                   v     v     v
                              +----+--+  |  +--+-----------------+
                              | native |  |  | MCP integrations  |
                              | email  |  |  | first-party +     |
                              | cal    |  |  | custom servers    |
                              | search |  |  +-------------------+
                              +----+---+  |
                                   |      |
                                   v      v
                             +-----------------------+
                             | Automation Runtime    |
                             | reminders / triggers  |
                             | scheduled jobs        |
                             | notification gating   |
                             +-----------------------+
```

#### 9.1 User-Facing Layer

Responsibilities inferred from official docs and leaked prompt:

- owns the product persona
- owns user-visible text formatting
- manages approvals and confirmations
- turns execution results into user-facing messages
- hides internal tool/agent boundaries
- decides whether to forward background results or silently drop them

This layer is where "Poke" as a product personality lives.

#### 9.2 Execution Layer

Responsibilities:

- perform tasks without direct user conversation
- use tools and subagents
- search in parallel across sources
- handle integrations, browser tasks, drafts, and triggers
- return contextual execution results upward

This layer is closer to an agentic runtime than a chatbot.

#### 9.3 Automation Layer

Public docs and prompt fragments make it highly likely that Poke has a durable
automation/reminder substrate:

- users can set reminders and email-based automations `A`
- prompts describe cron-based reminders and email-triggered automations `C`
- release notes discuss automations and automation bugs `A`
- status pages show subagent / MCP / timezone incidents that fit a background
  runtime `A`

This is why OpenPoke's trigger scheduler interpretation is believable, even if
its internal implementation choices are still its own. `D`

#### 9.4 Integrations Layer

This is more mature than a "tool plugin" story:

- official docs have integration-specific management flows `A`
- MCP subset, auth, and transport behavior are clearly documented `A`
- CLI and tunnel bundle expose dedicated connection lifecycle APIs `B`
- release notes treat integrations as a top-level product surface `A`

Poke appears to treat integrations as platform resources with lifecycle,
authentication, discovery, refresh, and user-facing management.

#### 9.5 Memory Model

The most plausible memory model from public evidence:

- user-facing conversation summary gets injected when history is too long `C`
- user profile / preferences are carried in hidden memory context `C`
- external systems like email act as recall surfaces, not just tool outputs
  `A+C+D`
- execution workers may keep durable work-thread state or at least durable logs
  that make follow-up actions cheaper `C+D`

What can be said safely:

- Poke almost certainly does not rely on a single flat conversation transcript.
- It likely combines summarized conversation memory, hidden user-profile memory,
  and external data sources as context.
- It may additionally preserve execution-thread continuity in a more durable
  form.

### 10. What Coke Should Borrow

This is the section that matters for refactor decisions.

#### 10.1 Borrow: explicit interaction/execution split

This is the single best architectural lesson.

Why:

- official MCP docs already confirm the split
- leaked prompts reinforce that the two layers have different goals
- OpenPoke shows why this makes orchestration, UX, and task execution easier to
  reason about

What this means for Coke:

- `PrepareWorkflow` should not just be a pre-processing step inside one monolith
  turn handler
- the user-facing turn coordinator should become a separate subsystem from the
  task executor
- side effects should move out of the same path that renders user text

#### 10.2 Borrow: integrations as a subsystem, not a tool list

Poke's integrations are not "some tools we sometimes call." They have:

- connection lifecycle
- auth UI
- refresh/retry semantics
- tunnel support
- packaging into recipes

For Coke, this argues for an `integration runtime` boundary rather than more
logic stuffed into `session_state`.

#### 10.3 Borrow: formal event ingress

Poke's inbound API and webhook triggers show a clean pattern for:

- operator-side interventions
- external workflow triggers
- machine-originated context

This is directly useful for Coke Phase 2. Learning-institution supervision will
need a formal event ingress for operator actions, learner events, and exception
signals.

#### 10.4 Borrow: background runtime with clear notification gating

Poke's prompts and public behavior both imply a background layer that can:

- wake on schedules
- wake on email events
- decide whether to notify the user
- silently cancel bad activations

Coke already has durable deferred actions, which is good. The lesson is to keep
that runtime durable and explicit, not to fold it back into turn-local context.

#### 10.5 Borrow: separate control plane from runtime

Poke's published artifacts make this separation obvious.

For Coke this suggests:

- user/channel/integration/operator configuration belongs in control-plane data
  and APIs
- turn runtime should consume resolved config, not own it
- future TOB features should land in control-plane artifacts before being wired
  into the worker runtime

### 11. What Coke Should Not Copy

#### 11.1 Do not copy the consumer-platform shell first

Poke is expanding outward into Recipes, integrations, and broad consumer
use-cases. Coke's roadmap does not support prioritizing that right now.

`docs/roadmap.md` is explicit:

- Phase 2 is a TOB supervision solution
- the first product is operator-facing for learning institutions
- Phase 3 platformization should not become the driver too early

So the wrong move is to react to Poke by chasing generic assistant breadth.

#### 11.2 Do not copy prompt-driven illusion as the core design

Poke's "single unified entity" illusion is useful UX, but Coke should not
mistake that for an architecture principle.

The architecture principle is the split.
The UX illusion is just the presentation layer on top.

#### 11.3 Do not over-index on leaked prompt wording

The leaked prompt material is useful for:

- agent boundary inference
- tool/approval patterns
- message-class taxonomy
- memory hints

It is not a stable design source for:

- exact implementation logic
- exact model mix
- exact safety rules
- exact persistence or orchestration internals

#### 11.4 Do not bury TOB operator workflows inside chat-first UX

Poke's product is still fundamentally chat-first.
Coke Phase 2 should not reduce operator workflows to a chat interface if the
operator actually needs batch actions, exceptions, reporting, and supervision
queues.

### 12. Concrete Implications For Coke Refactor

If this archive is used correctly, the immediate design direction for Coke is:

```text
Ingress
  -> Interaction Orchestrator
  -> Execution Runtime
  -> Automation / Deferred Action Runtime
  -> Integration Runtime
  -> Control Plane
```

Translated into Coke's current codebase:

- split user-facing orchestration concerns out of
  [agent/runner/agent_handler.py](/data/projects/coke/agent/runner/agent_handler.py:333)
- keep `PrepareWorkflow` ideas, but stop treating them as just one phase in a
  monolithic turn function
- preserve durable deferred actions as their own runtime service
- move integrations and operator/event ingress into dedicated boundaries
- make control-plane state explicit instead of carrying it through giant mutable
  turn context dicts

The practical rule is:

- use Poke as a reference for runtime decomposition
- do not use Poke as a reference for product scope

### 13. Open Questions

These questions remain unresolved after public research:

- Does Poke persist execution workers as true long-lived entities, or does it
  recreate them from durable logs and memory summaries?
- What exact storage model powers triggers, summaries, and notification state?
- How many model tiers are used in production, and which subsystems use smaller
  models versus premium ones?
- How much of prompt behavior has already shifted since the public leak?

These unknowns should not block Coke refactor. They only limit how literally
Poke can be copied.

### 14. Source Index

Official docs and pages:

- Welcome: https://poke.com/docs
- Developer introduction: https://poke.com/docs/developers/introduction
- MCP client specification:
  https://poke.com/docs/developers/integrations/mcp-client-specification
- Managing integrations: https://poke.com/docs/managing-integrations
- Creating recipes: https://poke.com/docs/creating-recipes
- Release notes: https://poke.com/docs/release-notes
- FAQ: https://poke.com/faq
- Home page: https://poke.com/
- Status history: https://status.poke.com/history
- Example status incident:
  https://status.poke.com/incidents/01KEH20JCPSMWFVTMT1T92FJX6
- Company page: https://interaction.co/
- Press release:
  https://www.webwire.com/ViewPressRel.asp?aId=343533

Official published artifacts:

- Python SDK page: https://pypi.org/project/poke/
- npm package page: https://www.npmjs.com/package/poke

Leaked prompt mirrors and public summaries:

- GitHub prompt mirror folder:
  https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools/tree/main/Poke
- Raw execution prompt:
  https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke%20agent.txt
- Raw interaction prompt fragments:
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p1.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p2.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p3.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p4.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p5.txt
  - https://raw.githubusercontent.com/x1xhlol/system-prompts-and-models-of-ai-tools/main/Poke/Poke_p6.txt
- Mintlify mirror / summary:
  https://www.mintlify.com/x1xhlol/system-prompts-and-models-of-ai-tools/commercial/poke

Third-party reverse-engineering:

- OpenPoke article: https://www.shloked.com/writing/openpoke
- OpenPoke repo: https://github.com/shlokkhemani/openpoke
- Poke Gate: https://poke-gate.fka.dev/
- Poke Gate CLI: https://poke-gate.fka.dev/cli.html
- Poke Gate security: https://poke-gate.fka.dev/security

Related Coke references:

- [docs/roadmap.md](/data/projects/coke/docs/roadmap.md:1)
- [docs/architecture.md](/data/projects/coke/docs/architecture.md:1)
- [agent/runner/agent_runner.py](/data/projects/coke/agent/runner/agent_runner.py:39)
- [agent/runner/agent_handler.py](/data/projects/coke/agent/runner/agent_handler.py:333)
- [agent/agno_agent/workflows/prepare_workflow.py](/data/projects/coke/agent/agno_agent/workflows/prepare_workflow.py:64)
- [agent/runner/context.py](/data/projects/coke/agent/runner/context.py:179)
