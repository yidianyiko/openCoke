# Golden Rules

These rules govern day-to-day repository work in `coke`.

## Documentation Rules

1. Keep one canonical home per kind of knowledge.
2. Keep `AGENTS.md` as a routing layer, not a knowledge dump.
3. Put repository-level workflow rules in `docs/design-docs/` or `docs/adr/`,
   not only in chat or one-off plans.
4. Keep product/runtime docs in their domain homes:
   - `docs/roadmap.md`
   - `docs/architecture.md`
   - `docs/deploy.md`
   - `docs/clawscale_bridge.md`
5. `docs/superpowers/specs/` and `docs/superpowers/plans/` are the canonical
   homes for design specs and execution plans (active and dated). Verify any
   individual file's freshness against current code before relying on it.

## Delivery Rules

1. Multi-step, risky, cross-cutting, or multi-session work should have an
   execution plan in `docs/superpowers/plans/`.
2. If a workflow rule changes, update the canonical docs in the same change.
3. If a code migration changes runtime behavior, architecture boundaries,
   protocol shape, deployment flow, or surface ownership, update the
   corresponding canonical docs in the same change. Do not leave stale docs
   behind as "historical context" unless they are explicitly marked dated or
   superseded.
4. Prefer the smallest implementation that improves repeatability or reduces
   operator ambiguity.
5. Use isolated git worktrees when concurrent implementation is real.

## Validation Rules

1. Do not claim work is complete without fresh verification evidence.
2. Run `scripts/check` whenever repository structure, routing, templates, or
   workflow docs change.
3. Run the relevant unit, integration, E2E, or deployment smoke checks for the
   runtime surface you touched.
4. State remaining risks or unverified areas explicitly.

## Agent Readability Rules

1. Put the important rule near the top of the file.
2. Use stable file paths and direct section names.
3. Make task, plan, and verification artifacts easy to locate.
4. Prefer short, focused docs over sprawling catch-all notes.
