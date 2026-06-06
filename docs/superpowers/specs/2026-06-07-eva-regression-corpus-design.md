---
status: approved-for-autonomous-implementation
created_at: 2026-06-07
scope:
  - Track J: Eva regression corpus
source_issue: docs/issues/2026-06-06-eva-chat-rca.md
---

# Eva Regression Corpus Design

## Context

Track J converts Eva's 2026-06-06 production failures into a focused regression
set on top of the integrated fixes for Tracks A through H. This work adds tests
and generated evidence only. It must not change the implemented render,
response-contract, recovery, delivery, onboarding, or friend-add fixes.

The production evidence names these binding cases:

- three reminder-fire turns where recent chat mentioned a different title or
  time than the durable reminder fact;
- a `zihao就是olivers` correction after an unmatched-friend blocker;
- an availability reply after shared-reminder context exists without leaking
  activity labels;
- a waiting-message provider failure followed by an eventual final reply;
- a shared-reminder creation reply that must not say `等他确认`, `邀约`, or soft
  success when no durable command materialized.

The corpus must assert two dimensions separately:

- user-visible text: final outbound prose must match trusted facts and must not
  leak known-bad wording;
- durable state: reminders, shared reminders, recoverable intents, input-window
  closure, waiting dispositions, and staged commands must change only at the
  fresh close boundary.

## Design Alternatives

### Recommended: Eva-shaped conversation/runtime corpus plus narrow guard tests

Add a dedicated `tests/unit/coke/turn/test_eva_regression_corpus.py` file that
uses the existing in-memory `ConversationRuntimeService`, `TurnRunner`,
`ReminderService`, `SocialSchedulingService`, `SocialSchedulingToolAdapter`, and
output protocol. The file will replay compact Eva-shaped turn sequences through
the same runtime seams as the integrated fixes:

- render-mode reminder fires hydrate durable reminder facts before agent output;
- correction turns consume `recoverable_scheduling_intent` only after a fresh
  materializing close;
- availability facts pass through the social-scheduling tool adapter and prompt
  path as privacy-safe windows;
- waiting sends keep the original turn active after delivery failure and allow
  later final reply completion;
- shared-reminder success claims require a trusted social-scheduling outcome and
  materialized command state.

This is the selected approach because it proves cross-turn behavior while
staying inside the repository's existing test architecture.

### Rejected: new standalone eval framework

A separate `tests/evals/` framework would satisfy the folder name in the issue,
but there is no existing eval harness in this worktree. Creating one would add
parallel infrastructure for one corpus and weaken the requirement to reuse
current runtime seams.

### Rejected: prompt-only or keyword-routing checks

Prompt text and phrase assertions alone cannot prove durable state. Production
already failed with prompt expectations present. Known-bad phrase checks remain
allowed only as regression assertions around visible text, never as production
routing logic.

## Architecture

### Corpus file

Create `tests/unit/coke/turn/test_eva_regression_corpus.py` as the single home
for Track J cases. The file will keep compact fakes local to the corpus instead
of importing helper fixtures from another test module. Local fakes are test
scaffolding, not runtime compatibility shims.

The corpus will exercise:

- `TurnRunner.run_render_turn()` for reminder-fire trusted-fact rendering;
- `TurnRunner.run_inbound_turn()` and `complete_async_reply()` for interactive
  correction, shared-reminder, availability, and waiting flows;
- `SocialSchedulingToolAdapter` for shared-reminder create and availability
  facts;
- `StagedCommandMaterializer` and in-memory repositories for durable-state
  assertions.

### Reminder-fire cases

The corpus will replay three production fact/render mismatches:

1. Durable fact `和eva约11:30的午饭`, recent chat mentions `11:40` and coffee.
2. Durable fact `和Olivers约下午两点喝咖啡`, recent chat mentions `下午3点`.
3. Durable fact `约olivers下午三点散步`, recent chat mentions coffee.

Each case will configure durable reminder/fire rows, run a render turn, feed the
agent the known-bad production-style prose twice, and assert the final visible
text falls back to the hydrated reminder fact. The test will also assert the
trusted domain result contains the exact durable title and local due time.

### Friend correction recovery

The corpus will create an open recoverable intent for the original unmatched
`zihao` scheduling request, then run a correction turn whose semantic decision
contains the typed `resolve_friend_reference_correction` action for
`zihao就是olivers`.

The positive branch asserts either recovered materialization or exactly one
constrained confirmation. The primary Eva case uses exactly one active friend
named `Olivers`, so it must materialize through the normal social-scheduling
tool and consume the artifact after a fresh close. The visible reply must not be
a generic availability refusal such as `我没法查看 olivers 的日程`.

### Availability privacy

The corpus will query availability after shared-reminder context exists. The
tool facts may expose only friend id, friend display name, and busy/free window
start/end/state. The visible reply must list busy/free windows only. It must not
include private activity labels such as `散步`, `咖啡`, or `你们约了散步`.

### Waiting failure and final reply

The corpus will run an inbound turn whose agent times out, force waiting
delivery to fail with `provider_network_error`, and then complete the async
reply. It will assert:

- the waiting attempt is recorded as a waiting message;
- the turn remains `pending_async_reply` after waiting delivery failure;
- `last_closed_inbound_seq` does not advance at waiting time;
- final async completion transitions the same turn to `replied`.

### No soft success without materialization

The corpus will run an Eva-shaped shared-reminder create turn that is superseded
before the close boundary. The agent returns production-bad soft-success prose
(`等他确认` or `邀约`), but no durable command may materialize. The expected
outcome is a non-successful close result: the stale turn is `superseded`, staged
commands are not materialized, no shared reminder exists, and no outbound soft
success is delivered as the accepted final reply.

If the integrated code accepts the soft-success reply while no durable command
materializes, Track J must stop and report that as an integrated-code defect.
The corpus will not add phrase-routing production logic to force green.

## Data Flow

1. Test setup records Eva-shaped inbound messages and durable reminders in
   in-memory repositories.
2. Each case invokes the existing runtime turn path, not a bespoke function.
3. Agent fakes return either fixed valid replies, production-bad replies, or
   timeout results.
4. The runtime validates structured output, stages/materializes commands at the
   close boundary, records outbound messages, and updates dispositions.
5. Tests assert visible outbound text separately from repository state.
6. Targeted pytest output is saved under
   `artifacts/evidence/2026-06-07-eva-regression-corpus/`.

## Error Handling

- A reminder-fire render without trusted durable facts must fail closed through
  the existing render guard.
- A correction without exactly one active friend must inject constrained
  confirmation facts and avoid materialization.
- Availability labels found in either tool facts or visible text fail the
  corpus.
- Waiting delivery exceptions are treated as observable waiting failure, not as
  final turn failure.
- Soft-success prose without materialized shared-reminder state is treated as a
  corpus failure and a potential integrated-code defect.

## Testing

Add the following tests:

- `test_eva_reminder_fire_uses_hydrated_fact_not_recent_wrong_chat`:
  parametrized over the three production reminder-fire mismatches.
- `test_eva_zihao_correction_recovers_shared_reminder_without_generic_refusal`:
  verifies visible recovery text and durable shared-reminder/materialized
  command/artifact state.
- `test_eva_availability_reply_has_windows_without_activity_labels`:
  verifies both privacy-safe tool facts and final visible reply.
- `test_eva_waiting_provider_failure_is_observable_and_final_reply_closes_turn`:
  verifies waiting failure evidence and later `replied` transition.
- `test_eva_superseded_shared_reminder_soft_success_does_not_materialize_or_send`:
  verifies stale soft-success output is not accepted as a durable success.

Verification commands:

```bash
.venv/bin/python -m pytest tests/unit/coke/turn/test_eva_regression_corpus.py -q
.venv/bin/python -m pytest tests/unit/coke -q
zsh scripts/suggest-verification --base main
zsh scripts/review-trigger --base main
```

The suggested surface from `scripts/suggest-verification --base main` will be
run. Targeted corpus/eval output will be copied to
`artifacts/evidence/2026-06-07-eva-regression-corpus/`.

## Out Of Scope

- no production-code changes unless the supervisor explicitly redirects after a
  reported defect;
- no new approval flows;
- no keyword or regex production routing;
- no prompt-only guarantees;
- no second user-facing prose producer;
- no new standalone eval framework.

## Spec Self-Review

- Placeholder scan: no unfinished placeholders remain.
- Internal consistency: all cases map to Track J and reuse current runtime
  seams.
- Scope check: this is a single regression-corpus task, not a new product
  behavior track.
- Ambiguity check: visible text and durable state assertions are separated for
  every case.
