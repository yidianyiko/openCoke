---
title: Agent runtime ignored assistant message text when Agno output content was empty
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/agno_agent/runtime/agent_runtime.py
  - tests/unit/agent/test_agent_runtime_output_rules.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t033651Z.json
---

# Agent runtime ignored assistant message text when Agno output content was empty

## What Happened

V2 smoke iteration 2 started `reject_friend` with batch `20260525t033651Z`.
Alice's greeting returned the hardcoded empty fallback even though
`agent_sessions` showed the model produced a fenced `MultiModalResponses`
assistant message with usable visible text.

## Why It Matters

The user can receive a fallback while the model actually produced a valid reply.
This makes normal greeting and onboarding turns look broken and can poison later
conversation turns in the same smoke batch.

## Root Cause

`run_agent_runtime` only read `run_output.content`. In this live Agno result,
`run_output.content` was empty while the final assistant text lived in
`run_output.messages[-1].content`.

## Fix

When `run_output.content` is empty, the runtime now scans the returned message
history from the end and uses the latest non-empty assistant message before
parsing multimodal envelopes.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_output_rules.py -q`
- `git diff --check`
