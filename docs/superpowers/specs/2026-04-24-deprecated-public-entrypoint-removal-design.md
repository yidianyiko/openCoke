# Deprecated Public Entrypoint Removal Design

## Goal

Remove deprecated customer-visible entrypoints and their lingering references so the public Kap experience exposes only the supported paths.

## Problem Statement

The product has already moved users onto neutral public routes such as `/auth/*`, `/channels/*`, and `/account/*`.

Even so, the repository still carries scattered references to retired public entrypoints like:

- `/login`
- `/coke/login`
- `/api/coke/auth/login`

Those strings should no longer appear as usable entrypoints in product code, public-facing guidance, or maintenance scripts that describe the supported flow. Keeping them around creates avoidable confusion and makes the product surface look less settled than it is.

## Scope

### In Scope

- user-visible web links, redirects, helper text, and copy that still point to retired public entrypoints
- deploy and maintenance scripts that still describe retired entrypoints as part of the active public surface
- environment examples or public-facing operational docs that still instruct readers to use retired public entrypoints
- tests that should be updated to assert only supported entrypoints are rendered, while preserving explicit `404` regression checks for retired routes

### Out Of Scope

- active business API namespaces that still power supported flows
- internal module names, database names, or environment variable names that are not customer-visible entrypoints
- payment or subscription routes that are still part of the supported product contract
- route structure or business logic changes beyond removing deprecated public entrypoint references

## Design

### Supported Public Surface

The supported public entrypoints are:

- `/`
- `/auth/*`
- `/channels/*`
- `/account/*`
- `/global`

Product code should present only these entrypoints to users.

### Retired Public Surface

The following paths are treated as retired public entrypoints:

- `/login`
- `/coke/login`
- `/api/coke/auth/login`

This cleanup also applies to any equivalent public guidance that still points users toward the same retired compatibility surface.

### Removal Rules

- If a link, redirect, CTA, help hint, or example suggests a retired public entrypoint is usable, remove or rewrite it to a supported route.
- If a script or doc uses a retired public entrypoint as a normal success path, rewrite it to the supported route.
- If a test exists to prove a retired public entrypoint remains unavailable, keep it and make the intent explicit through the assertion rather than through product copy.

## File Targets

Expected surfaces to review and update:

- `gateway/packages/web/**/*`
- `scripts/deploy-compose-to-gcp.sh`
- relevant env examples and operational docs that still mention retired public entrypoints as active paths
- targeted tests covering public homepage, auth, channel, account, and deploy verification

## Acceptance Criteria

- no user-visible product link or redirect points to a retired public entrypoint
- no public-facing guidance describes retired public entrypoints as usable paths
- explicit regression checks still verify retired public entrypoints return `404`
- supported Kap entrypoints continue to work unchanged
- relevant web tests and build pass

## Testing Strategy

Verification should cover:

- targeted search to confirm retired public entrypoints are no longer referenced as active paths
- web tests for touched surfaces
- web build
- deploy/public verification checks that still assert retired paths return `404`
