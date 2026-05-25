---
title: Remove friendship missed natural delete wording
status: resolved
kind: incident
affected_surfaces:
  - agent_runtime
  - scheduling_domain
---

# Remove friendship missed natural delete wording

## What happened

Batch `20260525t043543Z` reached an active Alice/Bob friendship. Alice then
sent `Alice 把 Bob 从我的好友里删了。`

The user-visible reply was the generic fallback:

`我没接住你刚才的意思。你可以换个说法再说一次吗？`

Postgres still showed `friendships.status = active`, and the pending shared
reminder request stayed `pending_invitee_confirmation`.

## Why it mattered

The gateway `remove_friendship` name-resolution fix was live, but the agent
runtime never routed this natural Chinese delete wording to the scheduling
domain. Users can explicitly ask to delete a friend and get no write.

## Root cause

`_infer_scheduling_intent_from_message` checked list-friends wording before
remove-friendship wording. The phrase contained `我的好友`, so it was classified
as `list_friends`. The remove rule also did not include common `删了` / `删掉`
wording.

## Fix

The remove-friendship inference now runs before list-friends inference and
recognizes delete wording when the message also references a friend.

Fix commit: this commit.

## Verification

- `.venv/bin/python -m pytest tests/unit/agent/test_agent_runtime_construction.py::test_scheduling_intent_inference_treats_delete_friend_wording_as_remove_friendship -q`
- Fresh live batch `20260525t044322Z` after `pm2 restart coke-agent`:
  Alice's `把 Bob 从我的好友里删了。` returned `已移除好友关系。`.
  Postgres showed `friendships.status = removed`.
  The pending shared reminder moved to `invalidated`, which matches current
  gateway service tests for removed-friendship cleanup.
