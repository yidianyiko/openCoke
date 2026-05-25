---
title: Pure greeting returned generic empty fallback
kind: active_issue
date: 2026-05-25
status: resolved
resolved: 2026-05-25
affected_surfaces:
  - agent/runner/output_delivery.py
  - tests/unit/agent/test_agent_handler.py
evidence:
  - artifacts/evidence/shared-reminder-agent-smoke/shared-reminder-agent-smoke-20260525t040259Z.json
---

# Pure greeting returned generic empty fallback

## What Happened

During `cancel_outgoing_friend_request` setup batch `20260525t040259Z`, Bob's
plain greeting `你好，我是 Bob，我刚登录。` returned the generic "换个说法"
fallback.

## Why It Matters

When the model returns blank content for a plain greeting, the runtime can still
give a safe direct introduction. A generic misunderstanding response is a poor
first-turn user experience.

## Root Cause

The deterministic greeting fallback only covered greetings that also asked for
capability information. It did not cover plain login greetings.

## Fix

The fallback now answers plain greetings directly when the input does not also
contain action terms for reminders, friendship, shared reminders, or scheduling
writes.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_handler.py -q`
- `git diff --check`
