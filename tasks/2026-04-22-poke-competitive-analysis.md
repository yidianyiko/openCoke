# Task: Poke Competitive Analysis

- Status: Complete
- Owner: Codex
- Date: 2026-04-22

## Goal

Assess Poke's current product shape and likely near-term direction, then compare
those facts against Coke's current Phase 1 state and planned Phase 2 direction.

## Scope

- In scope:
  - Public Poke positioning, channels, capabilities, platform surface, and
    productization signals
  - Coke's current product and roadmap state from canonical repository docs
  - Direct comparison focused on supervision/accountability, channels,
    extensibility, and future roadmap pressure
- Out of scope:
  - Private/internal Poke metrics beyond credible public reporting
  - Build-or-buy recommendations at implementation detail level
  - Any code or product changes in this repository

## Touched Surfaces

- repo-os

## Acceptance Criteria

- Summarize what Poke is shipping as of 2026-04-22 using primary/public sources.
- Infer Poke's likely next moves from release notes, docs, product surfaces, and
  public reporting, while clearly labeling inference vs. fact.
- Compare Poke to Coke using repository-canonical roadmap and architecture docs,
  not chat memory.
- Identify the areas where Poke is a direct threat, where it is adjacent only,
  and where Coke can still differentiate.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS structure test passes after adding this task file.
- Command: `zsh scripts/check`
- Expected evidence: repository structure and routing checks pass.

## Notes

### Coke Baseline

- `docs/roadmap.md` says Coke is still primarily in Phase 1: a personal
  supervision companion with reminders, proactive follow-up, and personal
  WeChat delivery.
- The same roadmap says Phase 2 is not started as a dedicated product phase yet;
  the intended direction is a TOB supervision solution for operators in
  learning institutions.
- `docs/architecture.md` and
  `docs/superpowers/specs/2026-04-20-deferred-actions-apscheduler-design.md`
  show reminder and proactive follow-up are already core runtime primitives.

### Poke Facts

- Poke's official docs position it as an AI assistant that lives in messaging
  channels and handles email, calendar, reminders, web search, and third-party
  integrations.
- Poke has clearly expanded beyond a single assistant UX into a platform shape:
  Recipes, direct MCP integrations, and an API that lets external tools send
  messages into the assistant.
- Poke also productizes vertical consumer entry points such as fitness and
  accountability pages instead of exposing only a generic assistant homepage.

### Comparison Summary

- Poke is ahead on consumer packaging, ecosystem surface, and multi-use-case
  breadth.
- Coke is still more opinionated around supervision/accountability and has a
  clearer potential path into operator-led TOB workflows if Phase 2 execution
  starts soon.
- If Coke stays in Phase 1 consumer mode, Poke's trajectory makes it the
  stronger default "assistant in messages" product.

### Updated Architecture Judgment

Do not interpret this analysis as a recommendation to bind Coke's agent core to
a "supervision specialist" identity. Supervision, reminders, follow-up,
progress tracking, and operator workflows should be treated as capabilities
that can be layered onto the agent runtime, not as the runtime's permanent
personality or product identity.

Coke already partially follows this direction:

- `deferred_action` is a runtime primitive, not a supervision-only concept.
- visible reminders and proactive follow-up already live in tool/service/runtime
  boundaries rather than only in prompt text.
- the remaining coupling is mostly at the policy and presentation layer:
  default character prompt, follow-up planning prompt, and chat-context handling.

The near-term architectural move is therefore boundary clarification, not a
large rename or a generic plugin platform. Keep `deferred_action` as a generic
primitive. Treat personal supervision and future learning-institution workflows
as capability compositions over that primitive.

### Follow-Ups

- Document which current behavior belongs to agent core, which belongs to the
  `deferred_action` primitive, and which belongs to the current default
  supervision character/profile.
- Keep reminder and follow-up implementation names stable unless a real
  cross-capability conflict appears.
- Defer a capability registry or manifest until there are at least two concrete
  capability packs that need shared loading, configuration, or enablement.
- When Phase 2 learning-institution work starts, model it as a composition of
  organization, member, progress, exception, and intervention capabilities
  rather than as a new hard-coded agent identity.
