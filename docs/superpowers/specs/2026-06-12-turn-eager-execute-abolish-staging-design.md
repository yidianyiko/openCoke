# Turn Eager Execute: Abolish Staging And Materialize-At-Close

## Status

design-ready (2026-06-12). This amends the implemented 2026-06-10 Plan → Execute
→ Express design. The Plan / PlanCompile / Execute / Express bounded split remains
the canonical inbound interactive spine: the earlier spec explicitly made the
inbound pipeline the only interactive inbound path and kept render/notification
turns out of scope (`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:5`,
`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:19`).
The bounded Express rationale remains valid: Express describes `settled_outcome`,
which is the structural no-false-success guarantee
(`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:62`,
`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:88`).

This spec replaces the 2026-06-10 close/materialization sub-design. The old data
contract allowed `ActionOutcome.staged_command_id?` and a `MaterializationPlan`
(`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:302`,
`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:308`).
The old close contract materialized staged commands at close and buffered
mutating-turn replies until materialization
(`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:328`,
`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:339`).
Those parts are superseded.

Provenance: drafted independently by two reviewers and cross-checked; both
converged on the same decision, deletions, and contracts. Then reviewed by two
more independent reviewers (reference-completeness lens + design-soundness lens),
both of which REJECTed the first merge. This is Revision 2, incorporating every
blocker:

- The execute boundary is pinned to **B2** (write into the shared turn session;
  commit only at the close boundary), which resolves the transaction-boundary,
  supersession, and most idempotency findings at once (see "Transaction
  Boundary").
- Express-failure recovery is grounded from `settled_outcome` **inside the
  pipeline** (the runner has no carrier for it).
- Streaming is buffer-then-deliver-after-commit (no pre-commit delivery).
- Deletions/tests/smoke completeness gaps closed (`staging.py`, runner
  `staged_command_id` parsing, agno staged-pending-close surfaces, the full test
  inventory, smoke scripts).

## Scope

This is an inbound interactive refactor only. The v2 inbound path is
`run_inbound_turn_async` → `_run_inbound_pipeline_async` → `turn_pipeline.run`:
the runner starts a turn and calls `_run_inbound_pipeline_async`
(`coke/turn/runner.py:530`, `coke/turn/runner.py:557`), then
`_run_inbound_pipeline_async` constructs a `_TurnPipelineRunnerDelivery` and
awaits `turn_pipeline.run` (`coke/turn/runner.py:650`, `coke/turn/runner.py:657`).

The render/notification async-pending machinery is out of scope:
`_record_pending_async` is called from the render-agent paths when
`agent_result.timed_out` (`coke/turn/runner.py:1164`, `coke/turn/runner.py:1188`,
`coke/turn/runner.py:1268`, `coke/turn/runner.py:1292`), and it writes
`pending_async_reply` plus `WAITING_TEXT` (`coke/turn/runner.py:1414`,
`coke/turn/runner.py:1434`, `coke/turn/runner.py:1439`). Do not redesign waiting
replies, render turns, notification turns, or `pending_async_reply`; only remove
the now-unused materializer parameter from that path because the staged-command
type disappears.

Also out of scope: reverting to an overloaded Agno-style tool loop. The planner
stays propositional, compile stays deterministic, Execute stays the only
domain-write boundary, and Express stays a bounded renderer with no domain tools.

The repository collaboration contract requires current runtime truth in canonical
docs and no compatibility shims unless a current spec names them
(`docs/design-docs/human-ai-working-contract.md:7`,
`docs/design-docs/human-ai-working-contract.md:44`). Coke-specific delivery rules
also prohibit legacy shims and duplicate retired workflow branches
(`AGENTS.md:113`). This refactor deletes the staging layer rather than keeping a
compatibility path.

## Problem

The current implementation violates the 2026-06-10 spec’s key guarantee. Express
can describe an optimistic `done/created` outcome even though the real write and
real validation have not happened yet.

The triggering bug is a concrete example. Personal reminder create enters
`ReminderActionHandler.resolve_and_stage` (`coke/turn/inbound/handlers/reminder.py:32`)
and `_create` stages an `execute_batch` command, then returns an optimistic
`ActionOutcome(category="done", status="created")` with a `staged_command_id`
(`coke/turn/inbound/handlers/reminder.py:88`,
`coke/turn/inbound/handlers/reminder.py:104`). That path does not call the real
`ReminderService.execute_batch` write boundary. The real past-time validation
lives in `ReminderService._create`: it calls `validate_trigger_time`
(`coke/domains/reminder/service.py:874`) and returns a `ReminderItemResult` with
`reason=time_state` and `time_state=time_state` when the time is not a valid
future time (`coke/domains/reminder/service.py:879`). `validate_trigger_time`
returns `needs_past_time_confirmation` when the trigger time is before `now`
(`coke/domains/reminder/service.py:731`, `coke/domains/reminder/service.py:748`).

Close then materializes before recording outbound messages. `commit_reply`
accepts `materialize_staged_command`, checks the turn, and calls
`_materialize_staged_commands` before it records outbound messages
(`coke/domains/conversation_runtime/service.py:207`,
`coke/domains/conversation_runtime/service.py:224`,
`coke/domains/conversation_runtime/service.py:229`). `_materialize_staged_commands`
iterates staged commands and calls the materializer
(`coke/domains/conversation_runtime/service.py:621`,
`coke/domains/conversation_runtime/service.py:633`).
`StagedCommandMaterializer.materialize` calls `execute_without_staging` and raises
when the tool result is not ok (`coke/turn/staged_commands.py:34`,
`coke/turn/staged_commands.py:38`, `coke/turn/staged_commands.py:40`).
`CloseCoordinator.commit` catches that exception and returns `committed=False`
(`coke/turn/inbound/close.py:79`, `coke/turn/inbound/close.py:89`). The pipeline
only delivers buffered staged-turn segments when close commits
(`coke/turn/inbound/pipeline.py:152`, `coke/turn/inbound/pipeline.py:159`), and
for the staged branch it returns no visible segments if close did not commit
(`coke/turn/inbound/pipeline.py:126`, `coke/turn/inbound/pipeline.py:167`).
Result: the turn completes with a failed disposition and no outbound reply.

This is not a reminder-only bug. Social scheduling already performs the real
service write in Execute and then stages a replay record: create calls
`detect_and_create_shared_reminder` or `create_shared_reminder` with
`commit_guard`, then stages a command and returns the staged id
(`coke/turn/inbound/handlers/social.py:69`,
`coke/turn/inbound/handlers/social.py:85`,
`coke/turn/inbound/handlers/social.py:99`). Friend, settings, and calendar
handlers follow the same write-then-stage pattern
(`coke/turn/inbound/handlers/friend.py:57`,
`coke/turn/inbound/handlers/friend.py:64`;
`coke/turn/inbound/handlers/settings.py:65`,
`coke/turn/inbound/handlers/settings.py:68`;
`coke/turn/inbound/handlers/calendar.py:61`,
`coke/turn/inbound/handlers/calendar.py:75`). The staged-command layer is
therefore two divergent truth sources: reminder defers truth until
materialization, while other domains write truth early and stage a replay
artifact.

## Decision

Adopt Option B in its **B2** form: execute-before-express, commit-at-close.
Execute calls the real domain service, which writes into the turn's shared
session but does **not** commit. Execute returns the real typed `ActionOutcome`
(the service computed it against real DB state). Express receives only that real
`settled_outcome`. Close commits the turn transaction (domain writes + outbound
rows + disposition + close-state) atomically at the existing close boundary, then
delivers. If the turn is superseded/cancelled before close, the shared session is
never committed and the domain writes roll back.

B2 vs naive eager-commit (B1): both produce the real outcome before Express (so
no false-success). B2 additionally keeps the write uncommitted until close, so it
preserves supersession-undo and makes write+disposition atomic (replay-safe).
Durability timing is unchanged from today — today's `materialize` also writes
into the shared session and only commits at the close boundary; B2 just moves the
service *call* from close-time to Execute-time while keeping the *commit* at
close. See "Transaction Boundary".

The new inbound shape is:

```text
Plan
  → PlanCompile
  → Execute(real service reads/writes into the shared session; NOT committed)
  → Express(render only real settled_outcome; recover from settled_outcome if invalid)
  → Close/Deliver(commit writes+outbound+disposition atomically; then deliver)
```

No downstream verifier is added. Express remains a bounded renderer with no tools:
the current Express system prompt says it has no tools, must describe only
`settled_outcome`, and must not claim state changes absent from that outcome
(`coke/turn/inbound/express.py:193`, `coke/turn/inbound/express.py:197`,
`coke/turn/inbound/express.py:214`). The fix is to make `settled_outcome` real.

## Transaction Boundary

This is the load-bearing decision; the implementation must follow it exactly.

The interactive runtime creates one `child_session` per turn and shares it across
all Postgres repositories; the only commit points are
`claim_boundary_committer=child_session.commit` and
`close_boundary_committer=child_session.commit`
(`coke/composition.py:1655`, `coke/composition.py:1677`). Domain `atomic()` is a
SAVEPOINT inside that shared session, not a real commit (e.g. social
`begin_nested`, `coke/domains/social_scheduling/repository.py:466`). Therefore a
domain write performed during Execute is **not durable** until a boundary
committer fires.

B2 uses this directly:

1. Execute calls the real service. The service validates, resolves, and writes
   into the shared session (savepoint), and returns the real typed result
   (`created` with a real id, `needs_past_time_confirmation`, `duplicate_active`,
   `blocked`, …). Nothing is committed yet.
2. Express renders the real `settled_outcome`.
3. Close (`commit_reply` / `commit_recovery_reply` / `commit_no_reply`) inserts
   outbound rows, saves disposition, advances close state, and the close boundary
   committer commits the **whole** session — domain writes, outbound, and
   disposition in one transaction.
4. Delivery happens only after that commit, from committed outbound rows.

Consequences the rest of the spec relies on:

- **Atomicity:** a turn either commits its domain write together with its
  disposition, or commits neither. There is no "committed write without
  disposition" state. This is what makes replay safe (see "Idempotency And
  Replay").
- **Supersession-undo preserved:** if a newer inbound cancels the turn before the
  close boundary commits, the session is discarded and the Execute writes roll
  back. The destructive-op residual window of naive eager-commit does not exist
  here (see "Supersession").
- **Freshness gate is the close commit:** `commit_reply` runs
  `_ensure_turn_can_close` before the boundary commit
  (`coke/domains/conversation_runtime/service.py:563-601`), so no write becomes
  durable for a superseded/stale turn even if a handler forgot a per-write guard.
  Per-write `guard_state_change` calls remain valuable only as an early-abort
  optimization (don't spend an LLM/IO on a turn already known stale).

Implementation requirement: every mutating domain service used by an inbound
handler must write through the injected (shared-session) repository and must NOT
perform its own autonomous `session.commit()`. Any service that commits on its
own would break atomicity and supersession-undo; audit each one during
implementation (settings and calendar are the suspects — see Idempotency/Freshness
findings).

## Detailed Component Design

### Plan

Plan remains unchanged. It proposes language-level actions, not resolved IDs or
final prose. The current planner prompt already says params are keyword/natural
references, never IDs or precise extracted times (`coke/turn/inbound/plan.py:26`,
`coke/turn/inbound/plan.py:29`). It also says reminder and social detectors own
precise time extraction later in Execute (`coke/turn/inbound/plan.py:32`). Keep
this boundary.

Prompt edit required: add a planner instruction that ambiguous clock ranges such
as “8-9” must be preserved as natural `time_phrase`, not normalized by Plan. Plan
should not choose morning/evening; it should route the action and pass the raw
phrase to Execute.

### PlanCompile

PlanCompile remains deterministic. It validates known domains, operations, and
required params (`coke/turn/inbound/plan_compile.py:17`,
`coke/turn/inbound/plan_compile.py:24`, `coke/turn/inbound/plan_compile.py:40`).
It must not gain time-confirmation logic or past-time repair. Missing structural
params remain `needs_input`; semantically risky times are domain Execute outcomes.

### Execute Contract

Rename `ActionHandler.resolve_and_stage` to `ActionHandler.execute`. The current
protocol name and call site are staging-specific (`coke/turn/inbound/execute.py:15`,
`coke/turn/inbound/execute.py:85`). The new signature (keep the current sync/async
shape of the executor; add the two kwargs) is:

```python
class ActionHandler(Protocol):
    def execute(
        self,
        compiled_action: CompiledAction,
        guard: FreshnessGuard,
        *,
        action_index: int,
        turn_id: str,
    ) -> ActionOutcome: ...
```

`ActionExecutor.execute` enumerates actions and passes `action_index` plus
`turn_id`; it is also the single place that derives the stable per-action
idempotency identity (`turn_id` + ordered `action_index` + domain + operation) and
threads it to mutating handlers, replacing the replay protection staging used to
provide. The executor already drives ordered actions
(`coke/turn/inbound/execute.py:38`, `coke/turn/inbound/execute.py:44`); extend
that loop instead of adding a second path. `FreshnessGuard` keeps
`guard_state_change` (`coke/turn/freshness.py:17`) and loses `stage_command`
(`coke/turn/freshness.py:20`).

Freshness under B2 is enforced by the close-boundary commit (the session does not
commit for a superseded turn; see "Transaction Boundary"). Per-write
`guard.guard_state_change()` / `commit_guard=guard.guard_state_change` is an
early-abort optimization, not the durability gate. Where a service already takes
`commit_guard` (social: `_run_commit_guard` immediately before persistence,
`coke/domains/social_scheduling/service.py:425`), keep threading it. Services that
do NOT take a `commit_guard` today (settings, calendar import — see Idempotency
And Freshness) need it only for early abort; not adding it is acceptable provided
they write through the shared session and never self-commit. Adding it everywhere
is the preferred consistency outcome but is not a correctness blocker under B2.

`ActionOutcome` loses `staged_command_id`. Today the field exists in the contract
(`coke/turn/inbound/contracts.py:62`, `coke/turn/inbound/contracts.py:67`) and
Express serializes it (`coke/turn/inbound/express.py:158`,
`coke/turn/inbound/express.py:165`). Under B, `ActionOutcome` is
`{category, status, data}` only, where `data` is the real service result. Any
idempotency key is internal execution context, not an Express-visible field.

Trusted context injection remains in Execute so planner-supplied values cannot
override `account_id`, channel, timezone, or current time
(`coke/turn/inbound/execute.py:74-85`).

### Reminder Handler

Reminder create must call `ReminderService.execute_batch` during Execute. The
handler already builds `ReminderBatchItem` with `turn_id=_turn_id(guard)` and
`item_index` (`coke/turn/inbound/handlers/reminder.py:353`,
`coke/turn/inbound/handlers/reminder.py:356`). Replace `_stage_execute_batch` with
a real call:

```python
guard.guard_state_change()
batch = reminder_service.execute_batch(
    owner_account_id=owner,
    items=[item],
    commit_guard=guard.guard_state_change,
)
return _batch_outcome_from_real_results(batch)
```

The service supports deterministic item idempotency through
`ReminderBatchItem.turn_id` and `item_index` (`coke/domains/reminder/models.py:87`,
`coke/domains/reminder/models.py:101`). Its outbox idempotency key is
`reminder:{operation}:{item.turn_id}:{item.item_index}` when both fields exist
(`coke/domains/reminder/service.py:1029`, `coke/domains/reminder/service.py:1038`),
and it short-circuits replay when that outbox event already exists
(`coke/domains/reminder/service.py:918`, `coke/domains/reminder/service.py:929`).
This gives reminder create at-most-once behavior without staged commands.

The original bug becomes a normal typed outcome: if the detected `trigger_time` is
genuinely before now, `ReminderService._create` returns
`ReminderItemResult(state="needs-follow-up", reason="needs_past_time_confirmation",
time_state="needs_past_time_confirmation")` (`coke/domains/reminder/service.py:874`,
`coke/domains/reminder/service.py:879`). The handler maps that to
`ActionOutcome(category="needs_confirmation", status="needs_past_time_confirmation",
data=...)`, matching the existing social handler mapping for this status
(`coke/turn/inbound/handlers/social.py:416`,
`coke/turn/inbound/handlers/social.py:477`).

Delete optimistic reminder result fabrication. `_stage_execute_batch` explicitly
defers duplicate detection to the close materializer
(`coke/turn/inbound/handlers/reminder.py:470`,
`coke/turn/inbound/handlers/reminder.py:477`), and `_optimistic_batch_data`
fabricates `state="succeeded"`, `reminder_id=None`, `reason=None`, and
`time_state=None` (`coke/turn/inbound/handlers/reminder.py:497`,
`coke/turn/inbound/handlers/reminder.py:515`). Both are invalid under B.

Reminder `batch_create` and keyword mutation (update/delete/complete) must also
call the service for real and return service-derived outcomes; their staged paths
(`coke/turn/inbound/handlers/reminder.py:284-324`) are deleted. Note: the working
tree already added a duration-required guard (`_missing_duration_outcome`) before
staging in `_create`/`_batch_create`; preserve that pre-write validation and run
it before the real `execute_batch` call.

### Social, Friend, Settings, Calendar

Social scheduling already writes during Execute: create passes
`commit_guard=_commit_guard(guard)` to the service before staging
(`coke/turn/inbound/handlers/social.py:69`,
`coke/turn/inbound/handlers/social.py:93`), cancel passes the guard to
`cancel_shared_reminder` (`coke/turn/inbound/handlers/social.py:140`,
`coke/turn/inbound/handlers/social.py:144`), and update passes the guard to
`update_shared_reminder` (`coke/turn/inbound/handlers/social.py:212`,
`coke/turn/inbound/handlers/social.py:219`). Remove the replay staging blocks and
return the already-real outcome. The social model should also drop
`staged_pending_close` and `staged_command_id`, because the status currently
includes `staged_pending_close` (`coke/domains/social_scheduling/models.py:13`)
and the outcome carries `staged_command_id`
(`coke/domains/social_scheduling/models.py:151`,
`coke/domains/social_scheduling/models.py:155`). Also remove the
`staged_pending_close` mapping in the output protocol
(`coke/turn/output_protocol.py:23`).

Friend handlers call real social service operations before staging
(`coke/turn/inbound/handlers/friend.py:57`,
`coke/turn/inbound/handlers/friend.py:100`,
`coke/turn/inbound/handlers/friend.py:163`). Settings handlers call the real
settings service before staging (`coke/turn/inbound/handlers/settings.py:65`,
`coke/turn/inbound/handlers/settings.py:100`,
`coke/turn/inbound/handlers/settings.py:140`). Calendar import calls the real
import service before staging (`coke/turn/inbound/handlers/calendar.py:61`,
`coke/turn/inbound/handlers/calendar.py:70`). In each handler, delete the
`_stage_*` helper and the `staged_command_id` assignment; keep the real service
call and outcome mapping.

### Express

Express input is still `SettledOutcome`, but the payload no longer includes
`staged_command_id` (`coke/turn/inbound/express.py:158`,
`coke/turn/inbound/express.py:165`). Keep the existing instructions that product
state comes only from `settled_outcome` (`coke/turn/inbound/express.py:228`,
`coke/turn/inbound/express.py:230`) and that `needs_input` / `needs_confirmation`
must ask only for the missing or risky thing (`coke/turn/inbound/express.py:209`,
`coke/turn/inbound/express.py:211`).

Express failure must not be silent. `_segments_from_content` currently raises
`ExpressOutputError` for invalid output, no-reply, missing/empty/too-many segments
(`coke/turn/inbound/express.py:241-260`). Under B, if Execute has returned a
`settled_outcome` and Express fails, the runner must record and deliver a grounded
recovery reply based on that real outcome.

Recovery carrier (review blocker): `settled_outcome` is local to
`TurnPipeline.run` (`coke/turn/inbound/pipeline.py:114`), Express raises while
rendering (`coke/turn/inbound/express.py:241`), and the runner only awaits
`turn_pipeline.run` (`coke/turn/runner.py:657`) — it has no handle on the real
outcome. Therefore recovery must be produced **inside the pipeline**, which owns
both `settled_outcome` and the `CloseCoordinator`. On `ExpressOutputError`,
`TurnPipeline.run` builds grounded recovery segments from `settled_outcome` and
closes via `commit_recovery_reply` (same transaction → the Execute writes commit
together with the recovery reply). Do not raise the error up to the runner to
recover; the runner cannot ground it.

Reuse the existing recovery wording. `_grounded_recovery_text` currently grounds
from staged commands, tool events, or input (`coke/turn/runner.py:2178`,
`coke/turn/runner.py:2185`); add/repoint a `settled_outcome`-grounded variant
callable from the pipeline. The runner's `_record_recovery_reply`
(`coke/turn/runner.py:1487`) remains the model for commit+deliver+lifecycle, but
the inbound pipeline path triggers recovery itself. The text must reflect
reality: created means "I created it, but the normal reply failed";
`needs_past_time_confirmation` means ask for confirmation; blocked/partial means
state the actual blocked/partial result. Do not add a verifier layer.

### Close

Close no longer materializes. `commit_reply` and `commit_no_reply` lose
`materialize_staged_command` (`coke/domains/conversation_runtime/service.py:207`,
`coke/domains/conversation_runtime/service.py:258`). Delete
`_materialize_staged_commands` (`coke/domains/conversation_runtime/service.py:621`).
`commit_reply` should validate segments, ensure close freshness, insert outbound
messages, save disposition, and call `_save_close_state` in that order. The
current implementation already records outbound messages after the materialization
call (`coke/domains/conversation_runtime/service.py:229`,
`coke/domains/conversation_runtime/service.py:247`,
`coke/domains/conversation_runtime/service.py:254`); remove only the
materialization step. `_save_close_state` remains the close-state authority
because it advances `last_closed_inbound_seq` to `turn.input_to_seq`, saves the
turn completed, and saves the conversation
(`coke/domains/conversation_runtime/service.py:603`,
`coke/domains/conversation_runtime/service.py:614`,
`coke/domains/conversation_runtime/service.py:619`).

`commit_recovery_reply` also loses staged-command supersession. It currently loops
over `repository.staged_commands_for_turn` and marks staged commands superseded
before writing recovery messages (`coke/domains/conversation_runtime/service.py:298`,
`coke/domains/conversation_runtime/service.py:304`). With no staged table,
recovery just writes recovery outbound rows, saves disposition `recovered`, and
advances close state.

`CloseRequest`/`CloseResult` drop `selected_staged_command_ids` and the
`CloseCoordinator` no longer receives or calls a materializer
(`coke/turn/inbound/close.py:44-99`). Close failure no longer means domain
materialization failure; it means close-state, persistence, delivery setup, or
supersession failure. Delete the materialization-failure rewrite
(`coke/turn/inbound/close.py:172`).

### Pipeline

Remove the `staged_command_ids` branch. Today `TurnPipeline.run` computes staged
command ids from `settled_outcome` (`coke/turn/inbound/pipeline.py:117`), buffers
Express for staged turns (`coke/turn/inbound/pipeline.py:126`), passes selected
staged ids to close (`coke/turn/inbound/pipeline.py:139`,
`coke/turn/inbound/pipeline.py:146`), and only delivers staged-turn segments after
a committed close (`coke/turn/inbound/pipeline.py:152`,
`coke/turn/inbound/pipeline.py:159`). Delete `_staged_command_ids`
(`coke/turn/inbound/pipeline.py:226`) and make all reply-needed turns run the same
flow:

1. Plan.
2. PlanCompile.
3. Execute real actions (writes into the shared session, uncommitted).
4. If `reply_necessity == intentional_no_reply`, Close `commit_no_reply`.
5. Otherwise Express `settled_outcome`, buffering segments.
   - On `ExpressOutputError`: build grounded recovery from `settled_outcome` and
     Close `commit_recovery_reply` instead (recovery happens here, in the
     pipeline, because only the pipeline holds `settled_outcome`).
6. Close `commit_reply` with the buffered segments (commits writes + outbound +
   disposition atomically).
7. Deliver committed outbound rows exactly once.

Streaming policy (review blocker — must be buffer-then-deliver): under B2 nothing
is durable until the close boundary commit, so NO segment may be delivered to the
provider before `commit_reply` commits. The current path delivers provider
messages before commit (`coke/turn/inbound/pipeline.py:130`,
`coke/turn/inbound/pipeline.py:135`) and `_TurnPipelineRunnerDelivery.deliver`
sends even when no outbound row exists (`coke/turn/runner.py:360`,
`coke/turn/runner.py:372`); delivering pre-commit would surface a reply for a
write that may still roll back on supersession, and could double-send (streamed +
row).

The uniform rule:

1. Express may render with `render_streaming` internally, but segments are
   **buffered**, not delivered.
2. `commit_reply` inserts the buffered segments as outbound rows and commits the
   close boundary (writes + outbound + disposition).
3. Delivery runs exactly once, after commit, from committed outbound rows.

No prose classification, no mutation/read branch — every reply-required turn
buffers then delivers. This trades pre-close streamed latency for correctness;
durable per-segment streaming (write each segment as a committed row as it is
produced) is possible future work but out of scope here. The implementation must
not invent an uncommitted delivery store.

### Runner

Remove `staged_command_materializer` from `TurnRunner.__init__`; it is currently
accepted and stored (`coke/turn/runner.py:406`, `coke/turn/runner.py:427`). Delete
`_materialize_staged_command` (`coke/turn/runner.py:1667`). Remove materializer
arguments from the render-agent close calls while keeping render/notification
semantics: `_record_pending_async` passes the materializer to
`mark_pending_async_reply` (`coke/turn/runner.py:1434`,
`coke/turn/runner.py:1437`), `_record_validated_output` passes it to
`commit_no_reply` and `commit_reply` (`coke/turn/runner.py:1576`,
`coke/turn/runner.py:1580`, `coke/turn/runner.py:1597`,
`coke/turn/runner.py:1601`). Those calls continue to close or mark pending exactly
as before, just without materialization.

Recovery ownership is the pipeline's, not the runner's (the runner lacks
`settled_outcome`). `_run_inbound_pipeline_async` currently marks failed when
`close_result.committed` is false and the error is not a `ConversationRuntimeError`
(`coke/turn/runner.py:663`, `coke/turn/runner.py:672`). Under B2, Express failures
are handled inside `TurnPipeline.run` (it produces a `recovered` close), so the
pipeline returns a committed close with a recovery reply; the runner just reports
that disposition. The runner's `mark_failed` path remains only for genuine
infrastructure/close failures (e.g. supersession at the close commit), not for
Express rendering errors. A superseded close (newer inbound won the race at the
commit) correctly yields no committed write and a superseded/interrupted turn.

## Deletions Table

| Symbol / surface | Current location | Replacement |
| --- | --- | --- |
| `staged_command` table in base migration | `migrations/versions/20260531_0001_pre_reply_input_windows.py:70` | New Alembic revision drops `staged_command`. |
| `schema.staged_command` | `coke/schema.py:270` | Remove from schema; no table replacement. |
| `StagedCommand` model | `coke/domains/conversation_runtime/models.py:100` | Delete; `ActionOutcome.data` carries real service facts. |
| Repository staged-command protocol | `coke/domains/conversation_runtime/repository.py:92` | Delete `save_staged_command` and `staged_commands_for_turn`. |
| In-memory staged maps and methods | `coke/domains/conversation_runtime/repository.py:135`, `:391`, `:413` | Delete. |
| Postgres staged methods and mappers | `coke/domains/conversation_runtime/repository.py:897`, `:934`, `:1249`, `:1265` | Delete. |
| `ConversationRuntimeService.stage_command` | `coke/domains/conversation_runtime/service.py:397` | Delete; handlers call domain services directly. |
| `ConversationRuntimeService._materialize_staged_commands` | `coke/domains/conversation_runtime/service.py:621` | Delete; close has no materialization step. |
| `materialize_staged_command` params | `coke/domains/conversation_runtime/service.py:207`, `:258`, `:336` | Remove params; keep close/pending behavior. |
| `MaterializedCommand` / `StagedCommandMaterializer` | `coke/turn/staged_commands.py:10`, `:16` | Delete `coke/turn/staged_commands.py`. |
| `FreshnessGuard.stage_command` | `coke/turn/freshness.py:20` | Keep only `guard_state_change`. |
| `_FreshStagedCommandMaterializer` | `coke/composition.py:1323` | Delete composition wrapper. |
| Materializer construction and wiring | `coke/composition.py:1528`, `:1556`, `:1587` | Compose pipeline/runner without materializer. |
| `ActionHandler.resolve_and_stage` | `coke/turn/inbound/execute.py:15`, `:85` | Rename to `execute`; call real services. |
| `ActionOutcome.staged_command_id` | `coke/turn/inbound/contracts.py:62`, `:67` | Delete field. |
| `MaterializationPlan` | `coke/turn/inbound/contracts.py:97` | Delete contract. |
| `selected_staged_command_ids` close concept | `coke/turn/inbound/close.py:37`, `:44`, `:57`, `:62` | Delete; CloseRequest carries plan/outcome/segments only. |
| Close materialization failure rewrite | `coke/turn/inbound/close.py:172` | Delete; Execute outcomes are already real. |
| Pipeline staged-command branch | `coke/turn/inbound/pipeline.py:117`, `:126`, `:146`, `:226` | Single execute → express → close → deliver flow. |
| Reminder optimistic staging helpers | `coke/turn/inbound/handlers/reminder.py:470`, `:497`, `:518` | Real `ReminderService.execute_batch` call during Execute. |
| Reminder optimistic outcomes | `coke/turn/inbound/handlers/reminder.py:104`, `:155`, `:308` | Map real `ReminderItemResult`s. |
| Social staging replay helpers + `staged_pending_close` | `coke/turn/inbound/handlers/social.py:99`, `:159`, `:226`, `:649`; `coke/domains/social_scheduling/models.py:13`; `coke/turn/output_protocol.py:23` | Return real social service outcome only. |
| Friend staging helpers | `coke/turn/inbound/handlers/friend.py:64`, `:108`, `:171`, `:278` | Return real social/friend service outcome only. |
| Settings staging helpers | `coke/turn/inbound/handlers/settings.py:68`, `:104`, `:144`, `:179` | Return real settings outcome only. |
| Calendar staging helpers | `coke/turn/inbound/handlers/calendar.py:75`, `:124` | Return real import outcome only. |
| Dual `execute` / `execute_without_staging` adapter API | `coke/composition.py:590`, `:614`, `:797`, `:843`, `:1089`, `:1114`, `:1160`, `:1188`, `:1232`, `:1263` | One `execute` method per adapter; no staging mode. |
| `_staged_command_result` | `coke/composition.py:2165` | Delete. |
| Staged write validators | `coke/composition.py:1907-1908`, `:1997-2158` | Delete; freshness is at real service write boundaries. |
| Staged recovery grounding | `coke/turn/runner.py:2185`, `:2195` | Ground recovery from real `settled_outcome`. |
| Staged-command JSON util + test | `coke/turn/inbound/staging.py` (`json_safe`), `tests/unit/coke/turn/inbound/test_staging.py` | Remove `json_safe` imports/usages from handlers; delete/retarget the module and test (keep `json_safe` only if still used for non-staging payloads — verify). |
| Runner `staged_command_id` parsing | `coke/turn/runner.py:1972` | Delete; no staged ids exist. |
| Runner social-stage detection | `coke/turn/runner.py` `_has_current_turn_social_scheduling_create_stage` (~`:1348`, `:1388`) | Delete; social writes are real in Execute. |
| Agno agent staged-pending-close surfaces | `coke/llm/agno_interaction_agent.py:489`, `:1389` (prompt text + model-visible pruning of `staged_pending_close`) | Remove staged-pending-close prompt/pruning. Verify whether this agent is still on any live inbound path post "v2 only inbound"; if dead for inbound, scope deletion accordingly but do not touch render/notification `pending_async`. |
| Tool-adapter staging guard detection | `coke/composition.py:1911` (`_guard_can_stage`) and staged write validators at `:2001`, `:2043`, `:2120`, `:2136`, `:2151` | Delete; one real `execute` adapter, freshness at the close commit. |
| 2026-06-10 staged contracts | `docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:302`, `:308`, `:316` | Mark amended/superseded by this spec. |

Citation corrections from review (use these line anchors; verify against current
tree as line numbers drift): reminder staged create at
`coke/turn/inbound/handlers/reminder.py:106-111`, `_stage_execute_batch` at
`:484-491`, optimistic fabricated data at `:515-523`; reminder idempotency at
`coke/domains/reminder/models.py:102-103`, key at
`coke/domains/reminder/service.py:1047-1049`, replay short-circuit at `:927-938`;
social `_run_commit_guard` at `coke/domains/social_scheduling/service.py:425-426`.

## Idempotency And Replay

Turn replay remains the first line of defense. The `turn` table has unique
`trigger_id` (`coke/schema.py:250`, `coke/schema.py:262`). `start_turn` returns
`TurnStartResult(replayed=True)` when a turn with the trigger id already exists
(`coke/domains/conversation_runtime/service.py:153`, `:160`, `:168`), and the
runner returns the previous disposition for replayed turns
(`coke/turn/runner.py:557`, `:1676`, `:1687`, `:1703`).

Inbound dedup remains independent. `record_inbound` writes an outbox idempotency
key `inbound:{causal_inbound_event_id}` (`coke/domains/conversation_runtime/service.py:113`,
`:126`), and the Postgres repository maps unique outbox idempotency conflicts to
existing rows (`coke/domains/conversation_runtime/repository.py:744`, `:749`). The
migration also created a unique inbound message sequence constraint
(`migrations/versions/20260531_0001_pre_reply_input_windows.py:65`).

B2 atomicity closes most of the replay surface that worried the review.
Because Execute writes commit in the SAME transaction as the disposition (see
"Transaction Boundary"), there is never a "committed domain write without a
disposition" state:

- Worker redelivers the trigger AND the prior turn committed its close: the prior
  turn has a terminal disposition; `start_turn`/`_replayed_result` returns it and
  Execute does not run again. No double-write.
- Worker redelivers AND the prior turn crashed before the close commit: nothing
  the prior attempt wrote was committed (session discarded). Re-execution is the
  first durable execution and produces the correct outcome. No double-write.

Replay-helper precision (review B4): `_replayed_result` short-circuits on ANY
existing disposition, including the non-terminal `pending_async_reply`
(`coke/domains/conversation_runtime/models.py:18-21`,
`coke/turn/runner.py:1684-1703`). That does not weaken the argument because
`pending_async_reply` is **unreachable on the inbound interactive path**: it is
written only by the render/notification `_record_pending_async`
(`coke/turn/runner.py:1164`, `:1188`, `:1268`, `:1292`, `:1434`), which the v2
inbound pipeline (`_run_inbound_pipeline_async` → `turn_pipeline.run`) never
calls. So for an inbound B2 turn the only `_replayed_result` short-circuit
dispositions are terminal (`replied`/`recovered`/`no_reply`/`superseded`/`failed`)
and the only non-short-circuit case is "no disposition" (crashed before close →
nothing committed). If a future change ever routes inbound turns through the
async-pending path, this replay argument must be revisited, because a
`pending_async_reply` turn could have committed Execute writes (via the close
boundary) without a terminal disposition — but that path is explicitly out of
scope here and must not be introduced for inbound without re-deriving B2 replay
safety.

The review's concrete "non-idempotent replay" cases —
social create → `duplicate_active`
(`coke/turn/inbound/handlers/social.py:403`), social update → `needs_update_fields`
(`coke/domains/social_scheduling/service.py:620`), cancel → `already_cancelled` →
`not_possible` (`coke/domains/social_scheduling/service.py:532`,
`coke/turn/inbound/handlers/social.py:153`), remove-friend → not found
(`coke/domains/social_scheduling/service.py:293`) — only arise if the FIRST
attempt's write was durable before the replay. Under B2 that requires the first
attempt to have committed close, which means it also recorded a disposition, which
means `_replayed_result` short-circuits the replay before Execute. So these
mis-outcomes do not occur on legitimate worker redelivery.

Two real residual obligations remain and are in scope:

1. **No autonomous commits.** Every mutating service must write through the
   injected shared-session repository and must NOT call `session.commit()` itself.
   If any service self-commits, its write becomes durable mid-Execute and breaks
   the atomicity argument above (re-enabling the double-write cases). Audit each:
   reminder, social_scheduling, settings, calendar_import. Calendar import is the
   prime suspect because it creates a `calendar_import_run` row per call
   (`coke/domains/calendar_import/service.py:311`) and creates reminders
   internally (`coke/domains/calendar_import/service.py:403`); confirm both go
   through the shared session and commit only at close.

2. **Side effects that escape the DB transaction.** The reminder scheduler reads
   committed rows (fine) but the reminder *outbox* event must stay deduped so a
   re-executed turn does not emit a duplicate scheduler event; this is already
   keyed `reminder:{operation}:{turn_id}:{item_index}`
   (`coke/domains/reminder/service.py:1047-1049`) and short-circuits on an
   existing event (`coke/domains/reminder/service.py:927-938`). Keep passing
   stable `turn_id`+`item_index` from the handler. External provider sends are
   post-commit via the outbound delivery/outbox with their own
   `delivery_attempt` idempotency, unaffected by this refactor.

`ActionExecutor` is the single place that derives and threads stable per-action
identity (`turn_id` + ordered `action_index`) to handlers that need it for
escaping side effects (today only reminder). Do not use `staged_command` as replay
protection; do not add per-operation idempotency keys where B2 atomicity already
covers the case.

## Supersession

The per-conversation Redis lock is held around the whole inbound pipeline:
`run_inbound_turn_async` acquires it before `_run_inbound_pipeline_async` and
releases it afterward (`coke/turn/runner.py:577`, `:604`), and a later inbound's
pipeline waits for that lock (`coke/turn/runner.py:1407`). So turn N+1 cannot
Execute while turn N holds the lock. A newer inbound also (a) marks active turns
superseded at record time (`coke/domains/conversation_runtime/service.py:141`,
`:716`) and (b) causes the supervisor to cancel the in-flight task with
`INTERRUPTED_BY_NEWER_INBOUND_CANCEL_REASON`
(`coke/worker/interactive_supervisor.py:71`, `:83`) and the provider run (`:91`);
the runner recognizes that cancellation (`coke/turn/runner.py:39`, `:61`, `:605`)
and records the interrupted turn as superseded (`coke/turn/runner.py:1657`,
`:1660`).

Under B2 there is no destructive-op residual window. Because Execute writes are
uncommitted until the close-boundary commit, the supersession outcomes are clean:

- Newer inbound arrives before turn N reaches its close commit → N is cancelled /
  its close `_ensure_turn_can_close` rejects the stale window → N's shared session
  is never committed → **N's domain writes roll back**. The "cancel then 别取消"
  case is safe: the cancel never became durable.
- Newer inbound arrives after N's close commit → N already replied with the real
  outcome; N+1 is an ordinary follow-up turn observing committed state.

This is strictly better than the naive eager-commit variant and than legacy
(which committed in the tool call). Do not rebuild optimistic staging; B2 already
gives supersession-undo for free via the existing transaction boundary. The only
true non-undoable side effects are those that escape the DB transaction (external
provider sends), which happen post-commit and therefore only for turns that did
commit.

## Prompt Changes

Planner prompt: add an instruction after the existing detector-ownership line
(`coke/turn/inbound/plan.py:32`): “For ambiguous clock phrases or ranges such as
‘8-9’, keep the phrase verbatim in `time_phrase`. Do not resolve AM/PM or dates in
Plan.”

Reminder detector prompt: edit `SiliconFlowReminderDetector.extract` system text.
It already says `now` is authoritative and relative expressions must be computed
from local now (`coke/llm/reminder_detector.py:48`, `:52`), and it currently says
not to “rewrite past/incomplete times” (`coke/llm/reminder_detector.py:68`, `:70`).
Add concrete guidance: “When the user gives an ambiguous hour or range without
AM/PM, choose the plausible near-future local time relative to authoritative now.
If the morning reading is already past and the evening reading is plausible, prefer
evening. Example: at 14:52 local, ‘今天8-9运动’ means today 20:00-21:00, not
08:00-09:00. Only return a past time when the user clearly meant the past.” Do not
add downstream confirmation machinery for “8-9”; genuinely past times still
surface as `needs_past_time_confirmation` from Execute.

Social detector use goes through the same detector extraction path in the social
handler for update time phrases (`coke/turn/inbound/handlers/social.py:707`,
`:722`), so this detector prompt change benefits personal and shared reminders.

This is the primary product fix for the reported case, per the directive to fix
understanding in the prompt rather than via more structural machinery.

## Migration Plan

Create a new Alembic revision, e.g.
`migrations/versions/20260612_0001_drop_staged_command.py`.

Upgrade:
1. Drain inbound workers.
2. Treat remaining staged rows as abandoned old-turn state (staged commands are
   transient close artifacts): `select count(*) from staged_command where
   status = 'staged';` is informational only.
3. `op.drop_table("staged_command")`.

Downgrade: recreate the previous table shape from the original migration
(`migrations/versions/20260531_0001_pre_reply_input_windows.py:70`, `:98`) for
local rollback only, or mark downgrade unsupported if the project’s clean-rebuild
migration policy allows destructive migrations. Choose one policy and document it
in the migration comments.

Update schema tests that name `staged_command`
(`tests/unit/coke/test_clean_schema_contract.py:64`, `:563`, `:916`;
`tests/unit/coke/conversation_runtime/test_schema_contract.py:55`).

## Test Plan

Unit tests:
1. `tests/unit/coke/turn/inbound/test_contracts.py`: remove
   `ActionOutcome.staged_command_id` and `MaterializationPlan` assertions
   (`:40`, `:74`).
2. `tests/unit/coke/turn/inbound/test_execute.py`: switch fake handlers to
   `execute`; current fakes expose `resolve_and_stage` and assert staged ids
   (`:18`, `:48`).
3. Rewrite reminder handler tests so create calls fake `execute_batch` and maps
   real item results; current tests assert staged behavior
   (`tests/unit/coke/turn/inbound/test_reminder_handler.py:237`, `:349`, `:724`).
   Add the deciding regression: “今天8-9给我建立一个运动的日程” with `now=14:52`
   produces a real Execute outcome; a genuinely past detected time →
   `needs_confirmation/needs_past_time_confirmation` and a delivered reply, never a
   silent failed turn. Preserve the existing duration-required tests.
4. Update social/friend/settings/calendar handler tests to assert no staged id and
   exactly one real service write (`test_social_handler.py:359`,
   `test_friend_handler.py:219`, `test_settings_handler.py:123`,
   `test_calendar_handler.py:146`).
5. Update close and pipeline tests to drop selected staged ids and materialization
   callbacks (`test_close.py:80`, `:226`; `test_pipeline.py:269`, `:559`).
6. Add Express failure recovery tests: after Execute returns `done/created`, force
   `ExpressOutputError`; assert `commit_recovery_reply`, `recovered` disposition,
   close-state advancement, recovery text grounded in the real outcome, no
   zero-outbound failed disposition.
7. B2 supersession/rollback test: a destructive fake handler writes during Execute;
   make Express await; submit a newer inbound so the turn is cancelled / its close
   is rejected before the boundary commit. Assert the older turn is
   superseded/interrupted, **the domain write did NOT become durable** (session
   rolled back), no outbound was delivered for it, and the newer turn proceeds.
   Exercises supervisor cancellation (`coke/worker/interactive_supervisor.py:83`),
   runner interruption recording (`coke/turn/runner.py:1657`), and the
   close-boundary commit gate.
8. B2 atomicity/replay test: a turn that crashes after Execute writes but before
   the close commit leaves no committed write and no disposition; a re-delivered
   turn re-executes cleanly and produces exactly one durable write. A turn that
   committed close is replayed via `_replayed_result` without re-executing.
9. Autonomous-commit guard test: assert each mutating service writes through the
   shared session and only the close-boundary committer commits (no service-level
   `session.commit`), so an uncommitted-then-rolled-back turn leaves no rows. Cover
   reminder, social, settings, calendar import (incl. the internal
   `calendar_import_run` + reminder writes).
10. Express-recovery-in-pipeline test: `ExpressOutputError` after a real Execute
    outcome routes to pipeline recovery, commits writes + recovery reply together,
    delivers, and never produces a zero-outbound failed disposition.
11. Update the additional staged-behavior tests the first inventory missed:
    `tests/unit/coke/conversation_runtime/test_conversation_runtime_service.py:311`,
    `:607`, `:640`; `tests/unit/coke/worker/test_waiting_reply.py:105`, `:151`;
    `tests/unit/coke/test_social_scheduling_tool_adapter.py:399`, `:433`, `:457`;
    `tests/unit/coke/test_tool_adapter_staging_guards.py:20`;
    `tests/unit/coke/llm/test_interaction_agent.py:1039`;
    `tests/unit/coke/turn/test_output_protocol.py:216`, `:246`, `:272`;
    `tests/unit/coke/turn/inbound/test_express.py:148`, `:250`;
    `tests/unit/coke/smoke/test_v6_wechat_smoke.py:107`, `:158`;
    `tests/unit/coke/worker/test_media_resolution.py:116`.

Integration and repo checks:
1. Focused unit suites for inbound contracts, execute, close, pipeline, handlers,
   conversation runtime, and schema.
2. `.venv/bin/python -m pytest tests/unit/coke -v`.
3. `zsh scripts/suggest-verification --base HEAD~1` and
   `zsh scripts/review-trigger --base HEAD~1`.
4. The suggested surface verification (expect backend/runtime plus repo-OS).

## Smoke Plan

1. `v6-wechat-smoke`: real inbound mutating reminder create → visible reply, real
   DB write, no staged rows/table dependency.
2. `coke-agent-smoke`: first contact, reminders, friendship, shared reminders,
   reminder fire.
3. Original-bug smoke: at a local time after 14:00, send “今天8-9给我建立一个运动
   的日程”. Expected: detector chooses the plausible near-future evening reading;
   Execute creates a real reminder; Express replies visibly. Controlled variant
   with a genuinely past reading → visible `needs_past_time_confirmation`, no
   silent failure.
4. Express-failure smoke: inject invalid Express output after a successful Execute;
   expect a recovered reply reflecting the real outcome.

Update smoke/probe scripts that currently assume staged rows or materialized ops so
they assert real domain rows/outcomes instead of `schema.staged_command`:
`scripts/smoke/v6_wechat_smoke.py:229`, `scripts/smoke/v6_cases.py:13`,
`scripts/turn_pipeline_probe.py:70`.

## Docs To Update

1. `docs/ARCHITECTURE.md`: replace the statement that the worker owns “domain
   command staging” (`:22`) and that Execute stages while Close materializes
   (`:70`, `:74`); update the close-boundary section that says staged commands
   materialize before close (`:144`, `:152`). Preserve render/waiting reply docs
   because `pending_async_reply` remains non-closing (`:156`, `:159`).
2. Mark the 2026-06-10 spec amended/superseded for staging, `MaterializationPlan`,
   and mutating streaming policy
   (`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:293`,
   `:316`).
3. Update `docs/product-specs/FEATURE_TREE.md` only if public route/API
   discoverability changes (it should not for this internal refactor).
4. Create/update an issue record for the silent-failure incident with the fix
   commit and final verification, per `AGENTS.md:83`, `:95`.

## Rollout And Deploy

Deploy as a single runtime migration because code without the table and old code
with the dropped table are incompatible. Sequence:

1. Stop/drain interactive workers.
2. Deploy database migration dropping `staged_command`.
3. Deploy backend code that no longer references staged commands.
4. Restart workers.
5. Run smoke plan.
6. Watch for `turn_pipeline_close_failed`, `invalid Express output`,
   `needs_past_time_confirmation`, duplicate domain rows, and zero-outbound failed
   inbound turns.

No compatibility mode (`AGENTS.md:113`,
`docs/design-docs/human-ai-working-contract.md:44`).

## Risks And Rejected Alternatives

Resolved by B2 (was the main A-vs-B concern): destructive-op supersession. Because
Execute writes commit only at the close boundary, a turn cancelled before close
rolls back its writes; "cancel then 别取消" is safe. There is no eager-commit
residual window.

Primary remaining risk: a service that performs an autonomous `session.commit()`
would make its write durable mid-Execute and re-open the double-write /
no-undo holes. Mitigation: the audit in "Idempotency And Replay" + the
autonomous-commit guard test. This is the single most important thing to verify
during implementation.

Secondary risk: side effects that escape the DB transaction (external provider
sends) only fire post-commit, so they only happen for turns that did commit; the
reminder outbox dedup key covers scheduler events.

Replay double-write is closed by B2 atomicity (write commits with disposition), so
re-delivery either short-circuits on the prior disposition or re-executes from a
clean rolled-back state — provided no service self-commits (see primary risk).

Rejected: rebuild staging with better materializer error handling. Keeps two truth
sources; does not restore structural no-false-success.

Rejected: keep staging only for destructive operations. Same two-truth-source
defect.

Rejected: downstream confirmation machinery for ambiguous “8-9”. The fix is
planner/detector prompt behavior plus real Execute outcomes; genuinely past times
remain `needs_past_time_confirmation`.

Rejected: a new verifier layer after Express. The 2026-06-10 decision chose
structural no-false-success through typed outcomes and Express discipline
(`docs/superpowers/specs/2026-06-10-turn-path-plan-execute-express-design.md:276`,
`:285`). This spec restores the premise by making Execute real.

## Implementation Task List

0. [ ] Foundation — confirm and lock the B2 transaction boundary: all inbound
   handlers' domain writes go through the shared-session repositories and only the
   close-boundary committer commits. Audit every mutating service (reminder,
   social_scheduling, settings, calendar_import incl. internal reminder + import-run
   writes) for any autonomous `session.commit()`; remove/redirect them. Add the
   autonomous-commit guard test. Nothing else is safe until this holds.
1. [ ] Add the drop-`staged_command` Alembic migration and update `coke/schema.py`.
2. [ ] Delete `StagedCommand` model, repository protocol/methods/mappers, and
   staged-command schema tests.
3. [ ] Remove `ConversationRuntimeService.stage_command`,
   `_materialize_staged_commands`, and all `materialize_staged_command` parameters.
4. [ ] Delete `coke/turn/staged_commands.py`, `_FreshStagedCommandMaterializer`,
   composition wiring, and runner materializer wiring.
5. [ ] Change `ActionHandler.resolve_and_stage` to
   `execute(compiled_action, guard, *, action_index, turn_id)`, update
   `ActionExecutor` to derive/thread per-action idempotency identity.
6. [ ] Remove `ActionOutcome.staged_command_id` and `MaterializationPlan`; update
   Express payload serialization.
7. [ ] Refactor reminder handler to call `ReminderService.execute_batch` in Execute
   and map real `ReminderItemResult`s (incl. `needs_past_time_confirmation`),
   preserving the duration-required guard.
8. [ ] Refactor social, friend, settings, calendar handlers to remove post-write
   staging and return real outcomes only; drop `staged_pending_close`.
9. [ ] Collapse adapter dual APIs to one real `execute` method; delete
   `_staged_command_result`, `_guard_can_stage`, and staged write validators.
10. [ ] Delete `coke/turn/inbound/staging.py` (`json_safe`) usages/module + its
    test; remove runner `staged_command_id` parsing (`:1972`),
    `_has_current_turn_social_scheduling_create_stage`, and the agno
    `staged_pending_close` prompt/pruning surfaces (preserve render/notification
    `pending_async`).
11. [ ] Refactor CloseCoordinator and pipeline to a single no-materialization close
    path with the buffer-then-deliver-after-commit streaming policy.
12. [ ] Add grounded settled-outcome recovery INSIDE `TurnPipeline.run` for Express
    failures (the runner has no `settled_outcome` carrier); repoint
    `_grounded_recovery_text` to a settled-outcome variant.
13. [ ] Update planner and reminder-detector prompts for ambiguous clock phrases and
    near-future resolution.
14. [ ] Keep reminder outbox idempotency (`turn_id`+`item_index`) threaded from the
    handler via `ActionExecutor`; do NOT add per-operation keys where B2 atomicity
    already covers replay (see Idempotency).
15. [ ] Rewrite/extend unit tests for contracts, execute, close, pipeline, handlers,
    schema, replay, Express-recovery-in-pipeline, B2 rollback-on-supersession,
    autonomous-commit guard, plus the full missed-test inventory and the
    smoke/probe scripts.
16. [ ] Add the original “今天8-9” regression test (real reply, never silent).
17. [ ] Update `docs/ARCHITECTURE.md`, amend the 2026-06-10 spec, and update issue
    records.
18. [ ] Run focused unit tests, full backend unit tests,
    `zsh scripts/suggest-verification --base HEAD~1`,
    `zsh scripts/review-trigger --base HEAD~1`, and the suggested surfaces.
19. [ ] Run `v6-wechat-smoke`, `coke-agent-smoke`, the real “今天8-9” smoke, and the
    Express-failure recovery smoke before rollout closeout.
