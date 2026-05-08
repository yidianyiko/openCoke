# Coke Release Checklist

Use this checklist before merging or deploying a release-worthy Coke change.

## Repository State

- [ ] Working tree reviewed; unrelated dirty files are excluded from the
      release commit.
- [ ] Branch and commit source are confirmed.
- [ ] Relevant ADR, architecture, product-spec, issue, or release docs are
      updated in the same change.

## Verification

- [ ] `zsh scripts/suggest-verification --base HEAD~1`
- [ ] `zsh scripts/review-trigger --base HEAD~1`
- [ ] `zsh scripts/verify-surface <surface>` for every affected surface.
- [ ] Runtime/eval/smoke evidence recorded under `artifacts/evidence/` when
      behavior beyond repo structure is claimed.
- [ ] `docs/issues/` record created or updated for non-trivial failures,
      incidents, or rollback-sensitive changes.

## Deployment

- [ ] `bash scripts/test-deploy-compose-to-gcp.sh` when deployment files or
      rollout behavior changed.
- [ ] `./scripts/deploy-compose-to-gcp.sh --restart` run from the intended
      checkout when deploying production.
- [ ] Post-deploy smoke follows `docs/deploy.md` and the affected surface's
      verification matrix entry.

## Closeout

- [ ] Commit message uses one concern.
- [ ] Evidence path and remaining risk are included in the handoff.
- [ ] Any resolved local issue record is updated with the fix commit and final
      verification.
