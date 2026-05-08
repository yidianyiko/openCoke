# Issues And Incident Records

This directory is the canonical home for local problem records in `coke`.

Use it before opening or updating an external issue when the failure is
non-trivial, runtime-facing, cross-surface, or likely to need future context.

## File Types

- `kind: active_issue` - current local tracker for one unresolved problem.
- `kind: incident` - production or runtime incident record.
- `kind: runbook` - operational repair instructions tied to a known failure.
- `kind: progress_note` - supporting investigation or migration state.
- `kind: verification_report` - evidence narrative that is easier to read as
  prose than raw generated artifacts.
- `kind: github_mirror` - local mirror of a GitHub issue. This is reference
  material, not the active source of truth.

## Rules

- Keep one canonical active local tracker per problem.
- Capture what happened, why it mattered, affected surfaces, current status,
  and verification evidence.
- Put generated logs, eval output, and large evidence under
  `artifacts/evidence/`; link to them from the issue record.
- If a local record mirrors GitHub, include `github_issue`, `github_state`,
  and `github_url`.
- When the problem is resolved, update the record with the fix commit and
  final verification.

## Hygiene

Review this directory at least every seven days. Track the last sweep in
`issue-gc-state.yaml`.
