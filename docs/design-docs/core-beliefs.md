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
- active execution plans: `docs/exec-plans/`
- verification rules: `docs/fitness/`
- task-local work state: `tasks/`
- dated design and implementation history: `docs/superpowers/`
- product direction and runtime docs: `docs/roadmap.md`,
  `docs/architecture.md`, `docs/deploy.md`, `docs/clawscale_bridge.md`

## 3. Preserve Existing Signal, Then Add Structure

`docs/superpowers/specs/` and `docs/superpowers/plans/` already contain real
design and execution history. The right move is to route and contextualize
them, not to pretend they do not exist.

## 4. Methodology Must Be Visible To New Agents

Routing files should tell a new agent where to read, where to write, and what
counts as complete without requiring chat reconstruction.

## 5. Verification Must Be Stronger Than Confidence

"Looks right" is not a completion signal. Completion requires fresh evidence:
tests, checks, smoke commands, or reviewed outputs.

## 6. Task And Plan State Should Survive The Session

Non-trivial work should leave behind task-local state and, when needed, an
execution plan in repo-local files.

## 7. Keep Product Docs Separate From Repo-OS Docs

`docs/roadmap.md`, `docs/architecture.md`, and `docs/deploy.md` describe what
Coke is and how it runs. `docs/design-docs/`, `docs/adr/`, `docs/fitness/`,
`docs/exec-plans/`, and `tasks/` describe how work on the repository should be
run.

## 8. Start With Minimal Structure That Improves Real Work

The repository operating system should stay small and reviewable. Add the next
piece only when it reduces ambiguity, makes handoff easier, or strengthens
verification.
