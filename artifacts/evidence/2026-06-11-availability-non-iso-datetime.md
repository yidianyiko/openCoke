# Availability Non-ISO Datetime Handler Fix

## Summary

Fixed the v2 social scheduling availability handler so non-ISO
`local_start` or `local_end` values from the planner are treated as missing
time input instead of raising `ValueError` and leaving an interactive turn to
retry.

## Product Surface

- `coke/turn/v2/handlers/social.py`
- `tests/unit/coke/turn/v2/test_social_handler.py`

No smoke runner or smoke case files were changed.

## Verification

- `.venv/bin/python -m pytest tests/unit/coke/turn/v2/test_social_handler.py::test_availability_query_non_iso_datetime_needs_time_without_service_call -q`
  - RED before fix: 2 failures with `ValueError: Invalid isoformat string: '今天'`
  - GREEN after fix: 2 passed
- `.venv/bin/python -m pytest tests/unit/coke/turn/v2/test_social_handler.py -q`
  - 11 passed
- `.venv/bin/python -m pytest tests/unit/coke/turn/v2 -q`
  - 128 passed
- `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
  - 1045 passed
  - check passed

## Guardrails

- `zsh scripts/suggest-verification --base HEAD`
  - changed surfaces: `clean-rebuild-backend repo-os-docs`
  - suggested command: `zsh scripts/verify-surface clean-rebuild-backend repo-os-docs`
- `zsh scripts/review-trigger --base HEAD`
  - human_review_required: no
  - risk_triggers: no
