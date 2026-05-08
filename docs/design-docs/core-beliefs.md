# Core Beliefs

These beliefs define how `coke` should store working knowledge as both a
product repository and a repository operating system.

## 1. The Repository Is The System Of Record

If an agent cannot find a rule, plan, or verification step in the repository,
it is operationally missing.

## 2. Durable Knowledge Needs A Canonical Home

Each kind of knowledge should have one default home:

- repository beliefs and rules: `docs/design-docs/`
- durable workflow decisions: `docs/adr/`
- design specs (active and dated): `docs/superpowers/specs/`
- execution plans (active and dated): `docs/superpowers/plans/`
- verification rules: `docs/fitness/`
- generated verification evidence: `artifacts/evidence/`
- product direction and runtime docs: `docs/roadmap.md`,
  `docs/architecture.md`, `docs/deploy.md`, `docs/clawscale_bridge.md`

## 3. Specs And Plans Live Together; Freshness Is Per-File

`docs/superpowers/specs/` and `docs/superpowers/plans/` are the single
canonical homes for design and execution artifacts. They contain a mix of
active and dated work. The right move is to verify each file's freshness
against current code before treating it as truth, not to scatter active
plans across multiple directories.

## 4. Methodology Must Be Visible To New Agents

Routing files should tell a new agent where to read, where to write, and what
counts as complete without requiring chat reconstruction.

## 5. Verification Must Be Stronger Than Confidence

"Looks right" is not a completion signal. Completion requires fresh evidence:
tests, checks, smoke commands, or reviewed outputs.

## 6. Plans And Evidence Should Survive The Session

Non-trivial work should leave behind a durable execution plan when needed and
fresh verification evidence when generated. Ephemeral task notes should not
accumulate as first-class repository history.

## 7. Keep Product Docs Separate From Repo-OS Docs

`docs/roadmap.md`, `docs/architecture.md`, and `docs/deploy.md` describe what
Coke is and how it runs. `docs/design-docs/`, `docs/adr/`, `docs/fitness/`,
`docs/superpowers/`, and `artifacts/evidence/` describe how work on the
repository should be run and verified.

## 8. Start With Minimal Structure That Improves Real Work

The repository operating system should stay small and reviewable. Add the next
piece only when it reduces ambiguity, makes handoff easier, or strengthens
verification.
