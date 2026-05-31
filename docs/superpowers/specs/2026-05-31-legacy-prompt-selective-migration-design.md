---
status: implemented
created_at: 2026-05-31
updated_at: 2026-05-31
owner: agent-runtime
kind: design
---

> **Status note (2026-05-31):** Implemented and merged to `main` (commits
> `8c2bd4ec feat: migrate prompt decision and voice contracts`, `61ff87a7 merge:
> selective legacy prompt migration`) and deployed to gcp-coke at SHA
> `d5ef1d0f`: enriched semantic-decision prompt, `turn_source` framing, the
> prompt-builder blocks, domain-result narration, dynamic current-time injection,
> and the voice policy. See [[2026-05-29-coke-clean-rebuild-prompt-migration]].

# Legacy Prompt Selective Migration Design

## Purpose

This spec records the prompt-design advantages observed in
`/data/projects/coke-legacy-server` and proposes how Coke should selectively
reuse them during the clean rebuild.

This is a review input, not an instruction to copy the legacy runtime. Reviewers
should treat every legacy prompt idea as a candidate pattern that must be
accepted, adapted, or rejected according to the current Coke architecture,
product contract, and verification evidence.

## Decision

Coke should absorb legacy prompt strengths in these areas:

- source-aware dynamic context assembly
- field-specific semantic decision prompts with examples
- structured domain execution facts for response grounding
- concise WeChat-native voice rules
- challenge and confusion handling
- explicit current-time and trigger-source framing
- post-turn memory/proactive rules that avoid inventing facts or duplicating
  timed reminders

Coke must not absorb legacy runtime ownership, compatibility behavior, or broad
fallback paths. The current boundary remains:

- Semantic interpreter or domain detector owns natural-language product intent.
- Domain executors own permissions, freshness, concrete arguments, and writes.
- The Interaction Agent owns final user-visible prose and renders trusted facts.
- Malformed or untrusted output is a runtime failure, not a prompt-repair or
  template-fallback path.

## Source Material Reviewed

Legacy prompt sources:

- `/data/projects/coke-legacy-server/docs/architecture/agent-prompt.md`
- `/data/projects/coke-legacy-server/agent/prompt/agent_instructions_prompt.py`
- `/data/projects/coke-legacy-server/agent/prompt/chat_taskprompt.py`
- `/data/projects/coke-legacy-server/agent/prompt/chat_contextprompt.py`
- `/data/projects/coke-legacy-server/agent/prompt/personality_prompt.py`
- `/data/projects/coke-legacy-server/agent/prompt/character/coke_prompt.py`
- `/data/projects/coke-legacy-server/agent/agno_agent/workflows/chat_workflow_streaming.py`
- `/data/projects/coke-legacy-server/agent/agno_agent/tools/reminder_tools.py`

Current Coke constraints:

- `docs/ARCHITECTURE.md`
- `docs/design-docs/coke-working-contract.md`
- `docs/design-docs/prompt-rule-ownership.md`
- `docs/superpowers/specs/2026-05-26-coke-focus-and-semantic-router-design.md`
- `docs/superpowers/specs/2026-05-26-coke-context-system-design.md`
- `docs/superpowers/specs/2026-05-28-visible-output-protocol-design.md`
- `coke/llm/agno_interaction_agent.py`
- `coke/llm/semantic_interpreter.py`

## Selective Absorption Rule

Legacy prompt content is useful only when it strengthens a current owner.

Before importing a rule, assign it to exactly one owner:

- character voice prompt
- semantic interpreter or domain detector prompt
- typed schema or Pydantic model
- domain execution result contract
- runtime guard
- eval corpus or few-shot set
- memory/proactive policy

Do not move a rule into the final response prompt if it is actually a routing,
permission, argument-validation, write-confirmation, or runtime-safety rule.
Do not keep a rule merely because it existed in legacy. If it conflicts with
clean-rebuild architecture, reject or redesign it.

## Current Gap

The current Interaction Agent prompt is intentionally compact, but it still
contains transitional business-routing instructions such as when to call
reminder, scheduling, friendship, settings, and calendar tools. This makes the
final response prompt carry decisions that should move into the semantic
interpreter and domain executors.

The current semantic interpreter is too thin for the behavior expected from
Coke. It returns only `reply_necessity`, broad `intent_family`, and optional
`language_hint`. It does not yet encode typed product actions, ambiguity
reasons, clarification needs, retrieval needs, or representative examples.

The current Interaction Agent input mostly provides a user message and a JSON
trusted context payload. It lacks the legacy system's useful source-aware and
condition-aware block rendering: inbound user message, reminder fire, proactive
message, onboarding, domain result, missing information, anti-repeat, retrieved
history, and output contract are not yet rendered as distinct prompt sections.

## Legacy Advantages To Reuse

### 1. Three-Layer Prompt Separation

Legacy documents a useful split:

- description: who the agent is
- instructions: how the agent decides
- schema field descriptions: what output shape and field formats mean

This maps well to Coke if the split is made stricter:

- character description belongs to the voice prompt
- decision instructions belong to semantic interpreter or executor prompts
- field constraints belong to schemas and typed result models

This should become the default style for new agent prompts. Avoid hardcoded
magic strings inside agent construction where a named prompt module would make
ownership clearer.

### 2. Field-Specific Decision Rules With Examples

Legacy reminder detection is effective because it teaches the model the
decision boundary with examples:

- create, update, delete, complete, query, and batch operations
- vague time expressions such as "晚一点", "过一会", and "待会" should not become
  a concrete trigger time
- incomplete current messages may complete a recently requested reminder, but
  should not reopen an already confirmed reminder
- multi-operation utterances should be treated as a batch
- current time must be injected before relative-time interpretation

Coke should not copy the old reminder tool schema or string formats. The
reusable part is the prompt pattern: field-specific rules, positive examples,
negative examples, and explicit ambiguity behavior.

### 3. Source-Aware Context Framing

Legacy explicitly tells the model whether the current turn is:

- a real user message
- a system reminder fire
- a proactive message

This is valuable because it prevents the model from treating a reminder title or
planned proactive action as if the user had just said it. Coke should represent
this as a trusted `turn_source` block assembled by the runtime.

Target pattern:

```xml
<trusted kind="turn_source">
  trigger_type: ReminderFireTurn
  user_spoke_this_turn: false
  instruction: Render the reminder fact to the user. Do not answer it as a user message.
</trusted>
```

### 4. Conditional Prompt Blocks

Legacy only injects some prompt sections when they are relevant:

- pending reminders only when there are reminders
- relevant history only when retrieval found non-duplicate history
- onboarding only for new users
- anti-repeat rules only when proactive repetition is a risk
- tool-result context only when a tool actually executed
- web-search context only when a search ran

Coke should adopt the conditional assembly principle, but the data sources must
be current clean-rebuild sources: trusted facts, Focus, semantic decision,
domain execution result, memory context, and domain read models.

### 5. Structured Domain Result Narration

Legacy's reminder tool writes a human-oriented execution context:

- `user_intent`
- `action_executed`
- `intent_fulfilled`
- `result_summary`
- optional details such as frequency-limit reasons

This is a strong pattern. Coke should generalize it into a domain-neutral
`DomainExecutionResult` or narration contract:

```text
domain
intent
action
effect
intent_fulfilled
visible_summary
reply_contract
privacy_notes
```

The Interaction Agent should render this trusted result. It should not infer
success from transcript text or from the existence of a requested operation.

### 6. WeChat-Native Voice Rules

Legacy's chat-response and personality prompts contain practical voice rules:

- speak like a WeChat friend or supervisor, not a customer-service bot
- keep most normal replies to one to three short text segments
- match the user's level of formality and length
- do not ask "还有什么可以帮您的吗"
- do not use technical workflow, agent, log, or tool explanations
- avoid forced jokes and repeated jokes
- do not use invented facts or invented times
- if the user challenges the system, first acknowledge the confusion, verify
  trusted state, and avoid blaming the user

Coke should absorb these as a `CokeVoicePolicy`. The policy must stay separate
from business routing rules.

### 7. Coke-Specific Role Texture

Legacy's Coke character is more concrete than the current default:

- Coke is a supervisor, friend, and teacher in a messaging channel
- Coke helps the user confirm goals, start tasks, and report completion
- Coke understands procrastination, startup difficulty, GTD, and ADHD-like
  friction
- Coke can be warm and direct without blind encouragement

This product texture should be preserved, but not all legacy restrictions should
be copied. For example, legacy rejects coding and deep research as a hard role
rule. Current Coke should only keep that if product requirements still define
those tasks as out of scope.

### 8. Post-Turn Memory And Proactive Discipline

Legacy post-analysis has two useful rules:

- summarize only explicit facts from the latest messages
- if a timed reminder was already created, skip creating a separate future
  proactive message for the same need

Coke should eventually express these as memory/proactive runtime policy, not as
an Interaction Agent responsibility. Do not import relationship-score
simulation unless a current product spec reinstates it.

## Legacy Content To Reject Or Redesign

Do not import:

- Mongo-backed runtime state
- legacy session-state coupling
- old reminder action names or string time formats as current contracts
- compatibility fallback branches
- deterministic fallback prose after invalid model output
- keyword or regex routing as the authoritative user-intent layer
- response-agent ownership of business routing
- voice, photo, Moments, media-generation, or relationship-score systems
  unless current product specs reintroduce them
- broad transcript-first context hierarchy for product facts

The current trust rule is stricter than legacy: user transcript is language
evidence, while trusted blocks and domain facts are authoritative for product
state.

## Target Prompt Ownership

### Semantic Interpreter

Owns:

- product intent classification
- typed action selection
- ambiguity classification
- required clarification reason
- language hint as non-authoritative display context

Should receive:

- current user utterance
- turn source
- Focus summary
- minimal recent conversation as advisory language evidence
- trusted environment such as timezone and current time

Should emit a structured decision such as:

```json
{
  "reply_necessity": "reply_needed",
  "intent_family": "reminder_op",
  "intent_action": "create_reminder",
  "ambiguity": "missing_time",
  "required_clarification": "ask_trigger_time",
  "language_hint": "zh"
}
```

The first migration may split these fields into domain-specific typed models,
but it must include at least a typed action, ambiguity state, and clarification
signal. Returning only the current broad family enum is not sufficient.

### Domain Executors

Own:

- concrete operation selection inside the domain
- argument validation
- permissions and privacy
- current-state freshness checks
- durable writes
- result facts for narration

They should return a trusted result that says what happened and what the
Interaction Agent may or must say.

### Interaction Agent

Owns:

- final channel-visible prose
- tone and segmentation
- rendering trusted facts
- asking required clarification questions
- honest failure or limitation wording

Should not own:

- first-pass business intent classification
- permission checks
- concrete durable write arguments
- write-confirmation truth
- parser repair

## Prompt Builder Design

Introduce a prompt builder that renders stable blocks in this order:

1. `turn_source`: inbound user, reminder fire, proactive fire, notification,
   access denied, recovery, or other The Turn trigger.
2. `current_input`: the current user message or trusted structured trigger fact.
3. `identity`: account, channel, assistant name, user address name.
4. `persona`: Coke voice settings and user-configured style.
5. `environment`: current time, timezone, locale, provider constraints.
6. `semantic_decision`: typed intent, ambiguity, and clarification requirement.
7. `focus`: authoritative current actionable object, if any.
8. `domain_result`: trusted execution/read result, if any.
9. `memory`: approved profile, settings, and relevant memories.
10. `conversation`: recent transcript as advisory language evidence.
11. `voice_policy`: concise WeChat expression constraints.
12. `output_contract`: JSON envelope and segment limits, last for recency.

The builder should omit empty blocks and should avoid duplicate representations
of volatile facts.

## Reference Prompt Fragments To Adapt

These fragments describe behaviors to preserve, not text to copy verbatim.

### Source Framing

User inbound:

```text
This is a real message from the user. Reply to the user's latest message.
```

Reminder fire:

```text
This is a system-triggered reminder fact, not a message from the user.
Render the reminder to the user. Do not answer the reminder title as if the user said it.
```

Proactive:

```text
This turn was initiated by Coke. The planned action is what Coke intends to say
or check. Do not answer it as a user question.
```

### Missing Or Unfulfilled Domain Action

```text
The user's intent was not fully fulfilled.
Do not claim the action succeeded.
Ask only for the missing information or explain the trusted failure reason.
```

### Executed Domain Action

```text
The trusted domain result says the action succeeded.
Confirm the concrete result naturally and briefly.
Do not add unsupported details.
```

### Voice Policy

```text
Speak like Coke in a chat thread: concise, direct, warm when useful, and not
customer-service-like. Avoid generic closers. Do not expose internal tools,
agents, logs, or architecture. Match the user's language and rough message
length. Use one to three short text segments for normal replies.
```

### Challenge Handling

```text
When the user challenges or questions system behavior, do not defend the system
first and do not blame the user. Acknowledge the confusion, check trusted facts,
then state what actually happened or ask for the missing detail.
```

## Evaluation Cases Required Before Implementation

Prompt migration should add or update eval/unit cases for:

- create reminder with explicit time
- create reminder with vague time, requiring clarification
- batch reminder request
- update/delete/complete/list reminder intent
- user provides only a time after Coke asked for time
- user provides a new topic after a reminder was already confirmed
- shared-reminder creation with friend name resolution
- friend-list query
- availability query
- reminder fire where the reminder title is not treated as a user message
- proactive message where Coke is the initiator
- domain result success confirmation
- domain result failure or missing information
- user challenge: "我没设过这个" or "你是不是搞错了"
- no success claim without a trusted domain result
- invalid final output fails closed
- no duplicate proactive follow-up when a timed reminder was created

## Review Questions

Reviewers should answer these before this spec becomes an implementation plan:

1. Which legacy voice rules should become default Coke personality, and which
   should stay user-configurable?
2. Which typed `intent_action` values should be in the first semantic
   interpreter migration?
3. Should `DomainExecutionResult` be one shared model across all domains or a
   common interface with domain-specific payloads?
4. Which eval corpus should be the release gate for this prompt migration?
5. Are any legacy role restrictions, such as refusing coding or deep research,
   still current product requirements?

## Out Of Scope

- Implementing the prompt builder.
- Changing tool signatures.
- Changing runtime routing.
- Migrating memory or proactive scheduling logic.
- Reintroducing any legacy storage or compatibility behavior.

Those belong in a later execution plan after this spec is reviewed.
