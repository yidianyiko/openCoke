# Web Dependabot Vulnerabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Plan Status:** complete

**Goal:** Resolve all current GitHub Dependabot npm alerts for the tracked Coke web manifests.

**Architecture:** Keep the remediation in the web dependency graph. Update direct vulnerable packages to patched releases, use a PNPM 11 workspace override for Next's vulnerable transitive PostCSS pin, let `pnpm` rewrite `web/pnpm-lock.yaml`, then verify with local audit, web tests/build, and repo verification routing.

**Tech Stack:** PNPM 11, Next.js, Vitest, React, GitHub Dependabot alerts API, Coke repo verification scripts.

---

## File Structure

- Modify `web/package.json`: bump direct vulnerable packages to patched releases.
- Modify `web/pnpm-lock.yaml`: refresh locked transitive versions with PNPM.
- Modify `web/pnpm-workspace.yaml`: add the PNPM 11 `postcss` override.
- Create `docs/issues/2026-06-08-web-dependabot-vulnerabilities.md`: local tracker for the alert set and final evidence.
- Create `artifacts/evidence/web-dependabot-vulnerabilities/2026-06-08-verification.md`: final verification evidence.
- Modify this plan file as tasks are completed.

## Task 1: Reproduce And Classify Alerts

**Files:**
- Create: `docs/issues/2026-06-08-web-dependabot-vulnerabilities.md`
- Create: `docs/superpowers/plans/2026-06-08-web-dependabot-vulnerabilities.md`

- [x] **Step 1: Read GitHub Dependabot alerts**

Run:

```bash
gh api --paginate 'repos/yidianyiko/openCoke/dependabot/alerts?state=open' --jq '.[] | [.number, .dependency.package.ecosystem, .dependency.package.name, .security_advisory.severity, .security_vulnerability.vulnerable_version_range, (.security_vulnerability.first_patched_version.identifier // ""), .dependency.manifest_path] | @tsv'
```

Expected: 31 npm alerts for `next`, `vitest`, and transitive `postcss` in
`web/package.json` and `web/pnpm-lock.yaml`.

- [x] **Step 2: Run local web audit and verify RED**

Run:

```bash
cd web && pnpm audit --audit-level low --json
```

Expected: FAIL with 16 deduplicated advisories, including vulnerable
`next@16.2.1`, transitive `postcss@8.4.31`, and `vitest@3.2.4`.

- [x] **Step 3: Rule out Python dependency alerts**

Run:

```bash
uvx pip-audit -r requirements.txt --format json
```

Expected: no known Python vulnerabilities.

## Task 2: Update Web Vulnerable Dependencies

**Files:**
- Modify: `web/package.json`
- Modify: `web/pnpm-lock.yaml`
- Modify: `web/pnpm-workspace.yaml`

- [x] **Step 1: Update direct vulnerable web packages**

Run:

```bash
cd web && pnpm up next@16.2.7 eslint-config-next@16.2.7 vitest@4.1.8
```

Actual: `web/package.json` records patched direct package ranges and
`web/pnpm-lock.yaml` replaced the vulnerable `next@16.2.1` and
`vitest@3.2.4` graph entries.

- [x] **Step 2: Fix Next's transitive PostCSS pin**

Run:

```bash
cd web && pnpm install
```

Actual: with `overrides.postcss: 8.5.15` in `web/pnpm-workspace.yaml`,
`pnpm why postcss` reports one `postcss@8.5.15` version shared by direct
PostCSS, Tailwind, Next, and Vite/Vitest.

- [x] **Step 3: Fix ESLint peer graph**

Run:

```bash
cd web && pnpm add -D eslint@^9.39.4
```

Actual: `pnpm peers check` reports no peer dependency issues. ESLint 9 is the
latest supported major for the Next lint plugin graph currently installed.

- [x] **Step 4: Verify audit is green**

Run:

```bash
cd web && pnpm audit --audit-level low
```

Actual: no known vulnerabilities.

## Task 3: Runtime-Surface Verification

**Files:**
- Modify: `docs/issues/2026-06-08-web-dependabot-vulnerabilities.md`
- Modify: `docs/superpowers/plans/2026-06-08-web-dependabot-vulnerabilities.md`

- [x] **Step 1: Run web tests**

Run:

```bash
cd web && pnpm test
```

Actual: 52 test files and 225 tests passed under Vitest 4.1.8.

- [x] **Step 2: Run web build**

Run:

```bash
cd web && pnpm build
```

Actual: Next.js 16.2.7 build completed.

- [x] **Step 3: Run diff-aware repo verification routing**

Run:

```bash
zsh scripts/suggest-verification --base HEAD~1
zsh scripts/review-trigger --base HEAD~1
```

Expected: routing commands complete; any suggested command for touched
surfaces is either run or explicitly recorded as not run.

- [x] **Step 4: Run suggested surface verification**

Run:

```bash
zsh scripts/verify-surface clean-rebuild-web repo-os-docs
```

Actual: passed. The verifier reran `cd web && pnpm test`,
`cd web && pnpm build`, and `zsh scripts/check`.

- [x] **Step 5: Record GitHub processing limitation**

GitHub Dependabot alerts are default-branch alerts. They will only disappear
from the GitHub alert list after this branch is pushed and GitHub processes the
committed dependency graph. Immediate local evidence is `pnpm audit` with zero
vulnerabilities.

- [x] **Step 6: Commit remediation**

Run:

```bash
git add web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml
git commit -m "fix: update vulnerable web dependencies"
```

Actual: `2201426d fix: update vulnerable web dependencies`.

- [x] **Step 7: Commit closeout records**

Run:

```bash
git add docs/issues/2026-06-08-web-dependabot-vulnerabilities.md docs/superpowers/plans/2026-06-08-web-dependabot-vulnerabilities.md artifacts/evidence/web-dependabot-vulnerabilities/2026-06-08-verification.md
git commit -m "docs: record web dependency remediation evidence"
```

Actual: completed after final verification.
