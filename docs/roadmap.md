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
- keep the pure ClawScale deployment path stable and repeatable

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
- legacy Ecloud/Evolution and Coke-owned direct channel runtimes have been
  removed from the repository
- ClawScale is now the only supported production channel entrypoint for Coke

### Platform priorities now

- stabilize personal `wechat_personal` async push in end-to-end environments
- keep the new personal-channel path as the default Phase 1 onboarding flow
- continue removing Coke-side legacy compatibility code and obsolete product concepts
- continue moving toward clearer ownership boundaries between Coke business
  state, bridge translation logic, and gateway/channel state

## TODO

### Phase 1 用户调研（优先级：最高）

背景：截至 2026-04-09，Coke 有约 10 名核心日常活跃用户（近 7 天活跃≥2 天），
24 名近 7 天内发过消息的用户。MAU 从 2025-12 的 195 持续下降至当前约 60。
所有 269 名注册用户均为真实付费用户（一次性 10-50 元），无测试账号。

任务：以创始人身份（非 Coke 身份）与核心用户沟通，用 Mom Test 方式提问：

1. 你上一次用 Coke 是什么时候？当时在干嘛？
2. 在用 Coke 之前，你怎么管这件事的？
3. 有没有哪次 Coke 提醒你了但你觉得烦？那次是什么情况？

目的：在推进 Phase 2 之前，确认 Phase 1 的留存衰减是产品问题还是运营缺位，
并从留下来的用户身上提取真正的产品价值点。

### 创始人 Dogfooding（优先级：最高，与迭代并行）

从 2026-04-09 起，创始人开始日常使用 Coke。不阻塞产品迭代进度。
目的：建立第一手产品体感，尤其关注作为"不爱聊天"的用户时哪些环节
让人不舒服。这些不适点可能正是 83% 用户流失的线索。

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
