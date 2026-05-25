---
title: Empty greeting fallback needed a direct capability answer
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/runner/output_delivery.py
  - tests/unit/agent/test_agent_handler.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t034750Z.json
---

# Empty greeting fallback needed a direct capability answer

## What Happened

After the prompt was tightened, `reject_friend` batch `20260525t034750Z` still
showed Bob's simple login greeting returning the generic empty fallback. The
model emitted blank content with no tool call, so there was no assistant text to
recover.

## Why It Matters

For a simple greeting or capability question, the fallback path can safely
answer the product contract directly. Returning "换个说法" makes a normal first
turn look like a misunderstanding.

## Root Cause

The runtime fallback was generic for all empty outputs except a few reminder or
plan cases. It did not distinguish simple greeting/capability questions from
ambiguous user instructions.

## Fix

The fallback now gives a concise Coke capability answer for greeting plus
capability-question inputs, while leaving ambiguous schedule statements on the
neutral retry wording.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py -q`
- `git diff --check`
