# Coke Release Guide

This guide defines Coke's release and rollout workflow. It is deliberately
operational: Coke releases are deployment/runtime cutovers, not package
publishing events.

## Release Scope

Use this guide when changing:

- worker runtime behavior
- reminder or deferred-action execution
- bridge inbound/outbound behavior
- gateway API or web surfaces
- deployment scripts, compose files, or runtime configuration
- repo-OS rules that affect how agents verify or hand off work

## Preflight

1. Confirm the working tree and branch:

   ```bash
   git status --short
   git branch --show-current
   ```

2. Run diff-aware routing:

   ```bash
   zsh scripts/suggest-verification --base HEAD~1
   zsh scripts/review-trigger --base HEAD~1
   ```

3. Run the surfaces suggested by the routing output:

   ```bash
   zsh scripts/verify-surface <surface>
   ```

4. Record evidence in `artifacts/evidence/` when runtime, deployment, or
   cross-boundary behavior is claimed.

## Deployment

Use `docs/deploy.md` as the command-level deployment runbook. This guide does
not duplicate host-specific steps.

Baseline deploy command:

```bash
./scripts/deploy-compose-to-gcp.sh --restart
```

Deployment changes must also pass:

```bash
bash scripts/test-deploy-compose-to-gcp.sh
zsh scripts/check
```

## Smoke Verification

After deployment, verify the real path named by the change. Examples:

- worker/runtime change: PM2 process, worker logs, focused runtime or eval
  evidence
- bridge change: `/bridge/healthz`, inbound bridge path, outbound dispatch path
- gateway change: API health, affected route test, browser or HTTP smoke
- reminder change: CRUD/eval evidence plus user-visible acknowledgement text

Do not treat HTTP liveness as proof of behavior unless the change was only
liveness-related.

## Rollback

Rollback must name:

- the commit or image being restored
- the data migration state
- the command used to redeploy or restart
- the smoke check proving the rollback took effect

If a rollback depends on a one-off repair, record it in `docs/issues/` as a
runbook or incident record.

## Release Notes

For user-visible changes, include:

- summary of the user-visible change
- affected surfaces
- migration or configuration notes
- verification evidence path
- known unverified areas
