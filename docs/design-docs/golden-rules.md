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
5. Preserve `docs/superpowers/` as dated design and implementation history
   until a dedicated migration replaces it.

## Delivery Rules

1. Every non-trivial task should have a task file in `tasks/`.
2. Multi-step, risky, cross-cutting, or multi-session work should also have an
   execution plan in `docs/exec-plans/`.
3. If a workflow rule changes, update the canonical docs in the same change.
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
