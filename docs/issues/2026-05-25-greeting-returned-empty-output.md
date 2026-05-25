---
title: Greeting and capability question returned empty output
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/agno_agent/runtime/chat_response_instructions.py
  - tests/unit/agent/test_chat_response_instructions.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t034536Z.json
---

# Greeting and capability question returned empty output

## What Happened

During `reject_friend` batch `20260525t034536Z`, Alice's first greeting and
capability question returned the hardcoded empty fallback. `agent_sessions`
showed the assistant message content was blank, with no tool call and no
recoverable envelope.

## Why It Matters

The first turn sets up the rest of a smoke batch and the real user experience.
A blank model response on a simple greeting makes the agent appear broken even
though no backend action was required.

## Root Cause

The user-visible reply boundary required JSON shape but did not explicitly say
that greetings, capability questions, and onboarding turns must be answered
directly with non-empty content.

## Fix

The interaction instructions now require a concise non-empty direct reply for
greetings, capability questions, and first-chat onboarding, without calling
tools.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_chat_response_instructions.py -q`
- `git diff --check`
