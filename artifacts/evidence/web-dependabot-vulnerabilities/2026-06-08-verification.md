# 2026-06-08 Web Dependabot Vulnerabilities Verification

## Scope

- Fix commit: `2201426d fix: update vulnerable web dependencies`
- Touched dependency files:
  - `web/package.json`
  - `web/pnpm-lock.yaml`
  - `web/pnpm-workspace.yaml`

## Root Cause

GitHub Dependabot reported 31 open npm alerts because it counts vulnerable
direct dependencies in both `web/package.json` and `web/pnpm-lock.yaml`.
Local PNPM audit deduplicated those into 16 advisories:

- `next@16.2.1`: Next.js advisories patched by `16.2.6` or earlier.
- `vitest@3.2.4`: critical Vitest UI advisory patched by `4.1.0`.
- `postcss@8.4.31`: transitive dependency pinned by Next, patched by
  `8.5.10`.

Python dependencies were not part of this alert set:

```bash
uvx pip-audit -r requirements.txt --format json
```

Result: no known vulnerabilities.

## Remediation

- `next`: `16.2.1` to `16.2.7`
- `eslint-config-next`: `16.2.1` to `16.2.7`
- `vitest`: `3.2.4` to `4.1.8`
- `eslint`: `10.4.1` to `9.39.4`, matching the peer range of the installed
  Next lint plugin graph.
- `web/pnpm-workspace.yaml`: added `overrides.postcss: 8.5.15`, the PNPM 11
  settings location that actually applies the override.

## Verification

```bash
cd web && pnpm audit --audit-level low --json
```

Result: zero vulnerabilities.

```bash
cd web && pnpm peers check
```

Result: no peer dependency issues.

```bash
cd web && pnpm why postcss
```

Result: one `postcss@8.5.15` version is shared by direct PostCSS, Tailwind,
Next, and Vite/Vitest.

```bash
zsh scripts/verify-surface clean-rebuild-web repo-os-docs
```

Result: passed. The verifier reran:

- `cd web && pnpm test`: 52 test files and 225 tests passed.
- `cd web && pnpm build`: Next.js 16.2.7 build completed.
- `zsh scripts/check`: passed.

## Notes

`pnpm lint` is not part of the suggested `clean-rebuild-web` surface and still
fails on existing `react-hooks/set-state-in-effect` findings in customer pages.
This dependency remediation did not weaken lint rules or refactor unrelated UI
code.
