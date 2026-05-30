# Coke Verification Matrix

Use this matrix to choose the smallest useful verification set for the surfaces
you changed.

Default entrypoint:

```bash
zsh scripts/verify-surface <surface>
```

Use `--dry-run` when you want to inspect the command mapping without executing
it.

## Clean Rebuild Docs

Use when changing the canonical docs that define the clean-rebuild target:

- `docs/ARCHITECTURE.md`
- `docs/product-specs/FEATURE_TREE.md`
- `docs/roadmap.md`
- `docs/clawscale_bridge.md`
- `docs/deploy.md`
- `docs/design-docs/coke-working-contract.md`
- `docs/design-docs/interface-contract.md`
- `docs/design-docs/data-retention-policy.md`
- `docs/fitness/coke-verification-matrix.md`
- `docs/fitness/surfaces.yaml`
- `scripts/e2e/clean-rebuild-canonical-doc-sync.sh`

Commands:

```bash
bash scripts/e2e/clean-rebuild-canonical-doc-sync.sh
zsh scripts/check
```

## Clean Rebuild Backend

Use when changing Python domain, API, worker, scheduler, outbox, provider
adapter, schema, or migration contracts for the clean rebuild.

Commands:

```bash
.venv/bin/python -m pytest tests/unit/coke -v
```

## Clean Rebuild Web

Use when changing the thin top-level Next.js client over the Python API.

Commands:

```bash
cd web && pnpm test
cd web && pnpm build
```

If `web/node_modules` is absent and the task does not permit a network install,
record that the web verification was skipped for environment setup rather than
forcing a partial or unrelated check.

## Repo OS Docs

Use when changing:

- `AGENTS.md`, `CLAUDE.md`, `README.md`
- `docs/ARCHITECTURE.md` and compatibility symlink `docs/architecture.md`
- `docs/design-docs/`, `docs/adr/`, `docs/superpowers/`
- `docs/issues/`, `docs/product-specs/`
- `docs/fitness/README.md`
- `docs/fitness/coke-verification-matrix.md`
- `docs/release-guide.md`, `docs/RELEASE_CHECKLIST.md`
- `artifacts/evidence/`

Commands:

```bash
zsh scripts/check
```

## Repo OS Tooling

Use when changing:

- `docs/fitness/surfaces.yaml`
- `docs/fitness/ownership-registry.yaml`
- `scripts/check`
- `scripts/verify-surface`
- `scripts/suggest-verification`
- `scripts/review-trigger`
- `scripts/guardrails.py`

Commands:

```bash
.venv/bin/python -m pytest tests/unit/coke/test_clean_rebuild_no_legacy_imports.py -v
zsh scripts/check
```

## Deployment And Rollout

Use when changing:

- `Dockerfile`
- `docker-compose.prod.yml`
- `deploy/nginx/coke.conf`
- `deploy/systemd/coke-compose.service`
- deployment sections in `docs/deploy.md`

Commands:

```bash
zsh scripts/check
```

If the change affects live rollout behavior, also follow the smoke steps in
`docs/deploy.md` and record user-path evidence for the claim being made.

## Cross-Surface Changes

If a task spans multiple surfaces, combine the matching verification sets
instead of inventing a new vague one-liner.
