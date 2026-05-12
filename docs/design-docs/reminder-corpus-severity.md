# Reminder Corpus Severity Tiers

This document defines how cases in
`scripts/reminder_normal_path_expectations.json` are graded for CI
enforcement. Severity is a property of the *case*, not of the *current
LLM*: a case is "critical" because a wrong answer breaks user trust,
regardless of whether the current model gets it right.

## Tiers

### `critical` (target: 100% pass)

A wrong answer creates user-visible damage:

- Wrong-time reminders fired at the wrong half of the day (12 h AM/PM
  inversion)
- Reminders silently dropped from a multi-clause request
- A delete/cancel intent treated as create (or vice versa)
- A clear date+time CRUD request answered with clarify (the user gave
  enough information and we asked them to repeat it)

### `important` (target: >=95% pass)

The case is user-facing and matters, but a wrong answer is recoverable:

- An over-clarification on an ambiguous bare clock
- A wrong title where the time is still correct
- A wrong RRULE that still fires once on the right occurrence

### `nice` (target: >=80% pass)

Edge-case language phenomena and corpus stability work:

- Specific Chinese phrasings (晚 X 点 vs 晚上 X 点)
- Noisy filler before time references
- Multi-clause inputs with redundant context

## Process for new failures

When a new corpus case fails:

1. Decide its severity using this standard.
2. If `critical` or `important`: file as an issue, plan the fix.
3. If `nice`: add to corpus at `severity: nice`, accept it as a known
   limitation unless three or more nice cases share a structural cause.
4. Never reclassify a failing case down just to make CI green.

## Migration

The initial labeling on 2026-05-12 is approximate. Re-label any case
whose severity is wrong when you next read it.
