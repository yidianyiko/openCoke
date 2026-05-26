# Prompt Rule Ownership

This document defines where prompt-like rules belong before they are added,
kept, moved, or deleted. It exists to keep prompts small without losing the
behavior that previous incidents forced into prompt text.

## Ownership Table

| Rule type | Owner | Keep in prompt? | Examples |
|---|---|---:|---|
| Role, tone, and user-visible voice | Character prompt | Yes | Coke is a health companion; concise WeChat style; refuse unrelated work briefly. |
| Natural-language intent routing | Interaction or detector prompt | Yes | Whether a sentence is a reminder request, a reminder query, a friend action, or ordinary discussion. |
| Ambiguity policy for user intent | Prompt plus eval | Yes | Ask when the friend name, reminder target, time, or action verb is ambiguous. |
| Output shape and JSON envelope | Runtime reply boundary or schema | Minimal | One parseable JSON object; text-only response shape. |
| Field validity and field combinations | Pydantic schema or typed result model | No | Required fields, allowed enum values, RRULE constraints, clarify reason restrictions. |
| Tool signatures and allowed arguments | Tool function signature and tool docstring | No | `scheduling_domain` accepts only `intent`; scheduling worker tools own their concrete arguments. |
| ID resolution, permissions, and friendship checks | Tool/runtime/backend contract | No | Resolve friend names server-side; fail closed on ambiguity; require active friendship for shared reminders. |
| Write-confirmation truth | DomainExecutionResult contract and runtime guards | No | Do not claim a write unless an executed operation reports a successful write effect. |
| Privacy and identifier leakage | Runtime guard plus tool contract | Usually no | Do not expose friend reminder titles, internal account IDs, or output targets. |
| Historical bug phrases and edge examples | Eval corpus or few-shot data | No, unless representative | Specific utterances from smoke failures, regression cases, and locale phrasing. |

## Migration Rule

Before moving a rule out of prompt text:

1. Identify the current behavior the rule protects.
2. Assign the rule to one owner in the table above.
3. Add or update a test, schema assertion, eval case, or smoke case that proves
   the owner now protects the behavior.
4. Only then delete or compress the prompt wording.

Do not move semantic routing rules directly into runtime heuristics unless the
product contract requires deterministic handling. If a rule depends on what the
user meant, it usually needs prompt guidance and behavior eval coverage.

## Current Pilot

The character prompt no longer names runtime tools or the exact
`ok=True`/`effect=write` write-confirmation condition. That deterministic
condition belongs to the DomainExecutionResult contract and runtime guards.
The character prompt keeps only the user-facing principle: future reminders,
shared reminders, friend collaboration, and supervision promises must be based
on confirmed system state.

The chat-response delegation boundary no longer owns scheduling-domain
parameter contracts, shared-reminder resolver details, friend-calendar default
date ranges, or fitness-class default duration. The outer prompt only chooses
the domain and high-level intent. Concrete scheduling tool arguments and
defaults belong to the scheduling worker prompt and tool signatures.
Friend-calendar privacy is enforced by the scheduling capability port before
facts reach the response model.
