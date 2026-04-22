# Task: Design Google Calendar One-Time Import And WhatsApp Claim Entry

- Status: In Review
- Owner: Codex
- Date: 2026-04-22

## Goal

Write the approved design for a first-version Google Calendar import flow that
migrates a user's primary Google Calendar events into Coke reminders and
supports shared WhatsApp auto-provisioned users through an email-based claim
entry flow.

## Scope

- In scope:
  - Write the design spec in `docs/superpowers/specs/`
  - Capture the approved product boundaries for one-time import
  - Capture the approved claim flow for unclaimed shared WhatsApp users
  - Record the minimal persistence strategy and surface split
- Out of scope:
  - Implementing OAuth, import UI, or runtime import code
  - Writing the implementation plan
  - Designing bidirectional or periodic sync

## Touched Surfaces

- gateway-api
- gateway-web
- bridge
- worker-runtime
- repo-os

## Acceptance Criteria

- The spec states that Google Calendar import is a one-time migration, not a
  sync product
- The spec states that imported events become Coke-owned reminders
- The spec states that unclaimed shared WhatsApp users must claim by email
  before import
- The spec defines the gateway/runtime responsibility split
- The spec defines the minimum durable persistence needed for v1

## Verification

- Command: `pytest tests/unit/test_repo_os_structure.py -v`
- Command: `zsh scripts/check`

## Notes

- The approved user-facing claim path is:
  - WhatsApp sends a short-lived claim-entry link
  - user enters their email on the claim-entry page
  - system sends a claim email
  - user opens `/auth/claim` from that email and sets a password
  - future login uses email and password
- The approved import path is:
  - active claimed user authorizes Google
  - Coke reads `primary` calendar once
  - Coke creates local reminders
  - no ongoing Google connection is kept in v1
