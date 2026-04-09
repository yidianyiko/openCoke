# Roadmap

Last updated: 2026-04-09

This document is the primary product and platform direction view for this
repository.

Use this file when you want to understand:

- what Coke is trying to become as a product
- which phase the current codebase primarily serves
- which platform capabilities are supporting those product phases

Detailed design docs, implementation notes, and migration history remain under
`docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Product Track

### Phase 1: Personal Supervision Companion

Goal:

- build a personal supervision and companionship assistant for individual users
- help a single user confirm goals, maintain habits, execute tasks, and stay in
  motion through reminders, follow-up, and ongoing conversation

Core product shape:

- one user
- one assistant relationship
- personal reminders and proactive follow-up
- personal channel delivery, especially personal WeChat

Current status:

- this is the phase the repository has substantially completed
- the core runtime is already implemented: inbound queueing, conversation
  locking, `PrepareWorkflow`, `StreamingChatWorkflow`,
  `PostAnalyzeWorkflow`, reminders, future/proactive messages, and outbound
  delivery paths
- the current work around ClawScale personal WeChat, bridge auth, async push,
  and rollout validation is still serving Phase 1 delivery and stabilization

Near-term focus for Phase 1:

- finish rollout validation for personal `wechat_personal`
- keep reminder and proactive delivery stable across bridge, worker, and
  gateway restarts
- continue shrinking legacy Ecloud/shared-bind usage to compatibility-only paths

### Phase 2: TOB Supervision Solution

Goal:

- evolve from a single-user companion into a B2B supervision solution
- serve an organizational operator rather than only an end user
- first prove the model in a vertical scenario, then extract reusable TOB
  capabilities

Execution strategy:

- start with one vertical scenario
- use that scenario to validate the operational workflow, product value, and
  deployment model
- then distill the reusable parts into general TOB capabilities

First vertical scenario:

- learning institutions

First product shape:

- a single-sided product for managers, class teachers, coaches, or similar
  operator roles
- not a separate student-facing product in the first step

What this phase should enable in the learning-institution scenario:

- view learner progress, habits, completion status, and exceptions
- identify who is falling behind or breaking expected routines
- trigger supervision, reminders, follow-up, and intervention from the operator
  side

What this phase should leave behind as reusable capability:

- organization and member modeling
- progress and habit tracking abstractions
- reporting, alerting, and exception detection
- batch supervision and operator workflows
- reusable TOB configuration and delivery patterns

Status:

- not yet started as a dedicated product phase
- currently only implied by some of the existing personal-supervision
  primitives, not yet modeled as a true TOB system

### Phase 3: OpenClaw-Like Assistant Platform

Goal:

- move from a specific supervision product toward a more general assistant
  platform
- support broader assistant use cases, more flexible workflows, and a cleaner
  platform boundary similar in spirit to OpenClaw

Status:

- still in design
- this phase should remain intentionally high-level until the product and
  architecture are clearer

Current expectation:

- Phase 3 should build on capabilities proven in Phases 1 and 2
- it should not become the primary roadmap driver before the TOB direction is
  better defined

## Platform Track

The platform track exists to support the product phases above. It is not the
main storyline of the roadmap, but it determines how safely and how fast the
product can evolve.

### Current platform themes

- channel and gateway integration
- bridge runtime and translation boundaries
- identity and account provisioning
- async delivery for reminders and proactive messages
- queueing, locking, and worker reliability
- observability, rollout safety, and operator documentation

### Current platform reality

- ClawScale integration is implemented beyond the design stage
- the repository contains a working Coke bridge, Coke user auth, gateway-side
  unified user model, and a personal WeChat channel lifecycle exposed through
  `/user/wechat-channel` and `/coke/bind-wechat`
- legacy Ecloud WeChat and some runner-owned channel paths remain active
- the newer channel abstraction and ClawScale path exist, but they are not yet
  the only runtime entrypoint

### Platform priorities now

- stabilize personal `wechat_personal` async push in end-to-end environments
- keep the new personal-channel path as the default Phase 1 onboarding flow
- preserve legacy/shared compatibility only where needed for rollout safety
- continue moving toward clearer ownership boundaries between Coke business
  state, bridge translation logic, and gateway/channel state

## Phase Mapping

If you need a simple summary of where the codebase stands today:

- Phase 1 is the active product phase and is largely implemented
- the current engineering backlog is mostly Phase 1 stabilization and migration
  cleanup
- Phase 2 is the next product phase: a TOB supervision solution, starting with
  learning institutions and a manager-side product
- Phase 3 remains exploratory and should be treated as design-stage only

## Canonical References

- `docs/architecture.md`: runtime architecture wired in code today
- `docs/clawscale_bridge.md`: Coke user and personal WeChat rollout notes
- `docs/superpowers/specs/`: dated design decisions and target architectures
- `docs/superpowers/plans/`: implementation checklists, rollout tasks, and
  migration details
