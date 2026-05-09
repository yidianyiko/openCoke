# ADR 0003: Consolidate Execution Plans Under `docs/superpowers/plans/`

- Status: Accepted
- Date: 2026-05-09

## Context

ADR 0001 introduced `docs/exec-plans/` as the canonical home for new
multi-step execution plans, intentionally keeping `docs/superpowers/plans/`
as dated history. In practice, three sources of truth diverged:

- `AGENTS.md` (and several design docs) stated "new execution plans go in
  `docs/exec-plans/`."
- The `superpowers:writing-plans` skill defaulted to
  `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`.
- The actual recent practice for runtime/agent work landed every plan in
  `docs/superpowers/plans/`. By 2026-05-08, the most recent plans
  (e.g. `2026-05-08-team-runtime-contract-repair.md`) lived there, while
  `docs/exec-plans/` had not received a new entry since 2026-04-29.

ADR 0001 itself acknowledged the dual-home arrangement was temporary
("The repository temporarily carries both new canonical directories and
older `docs/superpowers` history; that is intentional"). The continued
divergence between rules and practice was actively harmful: agents
following AGENTS.md picked the wrong directory, agents following the
skill picked the right one, and reviewers had to read both places when
auditing.

## Decision

Consolidate execution plans into a single canonical directory:
`docs/superpowers/plans/`.

- All 21 plans plus `README.md` and `_template.md` were `git mv`'d from
  `docs/exec-plans/` to `docs/superpowers/plans/` (no filename
  collisions). The `docs/exec-plans/` directory was deleted.
- `AGENTS.md`, `README.md`, the repo-OS design docs,
  `docs/fitness/coke-verification-matrix.md`, `docs/fitness/surfaces.yaml`,
  ADR 0001, and ADR 0002 were updated to reflect the new location.
- `tests/unit/test_repo_os_structure.py` was updated: it no longer
  asserts `docs/exec-plans/` exists, and its rule-text assertions check
  the new "Put new execution plans in `docs/superpowers/plans/`" wording.
- `docs/superpowers/plans/` is no longer described as "dated history."
  It is the single canonical home for execution plans, both active and
  archived. Individual file freshness must still be verified per file.

`docs/superpowers/specs/` continues to be the canonical home for design
specs and was unaffected by this migration.

## Consequences

- One canonical home per artifact kind: AGENTS.md, the writing-plans
  skill default, and actual practice now agree.
- Reviewers and agents stop reading two directories to find a plan.
- ADR 0001's directory list (which named `docs/exec-plans/`) is now
  partially superseded; ADR 0001 retains its historical record of why the
  control layer exists.
- `superpowers/` is now a mixed canonical location, not a history-only
  archive. Per-file freshness checks (against current `main`,
  `docs/ARCHITECTURE.md`, and the touched code) are now the load-bearing
  freshness signal, not the directory name.
- Future migrations of dated specs/plans to a separate archive remain
  possible but are out of scope here; they would require a new ADR.
