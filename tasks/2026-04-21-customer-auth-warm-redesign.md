# Task: Customer Auth Warm Redesign Spec

- Status: Verified
- Owner: Codex
- Date: 2026-04-21

## Goal

Capture an implementation-ready spec that brings the customer auth pages onto
the warm editorial public-site design system without changing auth behavior.

## Scope

- In scope:
  - a written design spec for `/auth/login`, `/auth/register`,
    `/auth/forgot-password`, `/auth/reset-password`, `/auth/verify-email`, and
    `/auth/claim`
  - explicit styling-boundary rules for `gateway/packages/web`
  - implementation file map, test impact, and verification guidance
  - task-local handoff state for the redesign
- Out of scope:
  - implementing the redesign
  - changing auth APIs, redirects, or storage behavior
  - redesigning `(customer)/channels`, `(coke-user)/*`, or `(admin)/admin/login`
  - writing the follow-up execution plan in this task

## Touched Surfaces

- gateway-web
- repo-os

## Acceptance Criteria

- The repository contains a design spec under `docs/superpowers/specs/` that
  defines the approved auth redesign scope, shared shell strategy, file-level
  change list, styling boundaries, and verification gate.
- The spec states that the redesign is visual-only and preserves existing auth
  logic and route behavior.
- The spec makes the frontend-only boundary explicit enough that any API,
  routing, storage, or conditional-logic edits are clearly out of scope.
- A task file records the goal, scope, touched surfaces, and verification for
  this documentation work.

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Expected evidence: repo-OS structure checks pass with the new task/spec
  artifacts present.
- Command: `zsh scripts/check`
- Expected evidence: repository routing and documentation checks pass after the
  new task/spec files are added.

## Notes

- The user requested a spec only so another implementer can pick up the work.
- The follow-up execution plan should be written only after the user reviews
  and accepts the spec.
