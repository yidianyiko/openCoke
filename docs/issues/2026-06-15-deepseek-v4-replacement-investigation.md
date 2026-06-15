---
kind: verification_report
status: resolved
surface:
  - clean-rebuild-backend
  - worker-runtime
created_at: 2026-06-15
updated_at: 2026-06-15
---

# 2026-06-15 DeepSeek V4 Replacement Investigation

## What Happened

While GLM-5.2 remained unavailable to the current Z.AI API key, we evaluated
whether official DeepSeek V4 could replace the current GLM-5.1 turn-path text
models. The investigation focused on the user's open questions:

- whether DeepSeek failures were caused by not enabling thinking mode;
- whether planner or interaction failures were prompt issues;
- whether the current Coke turn design is tuned around GLM behavior;
- whether any DeepSeek role should replace GLM-5.1 now.

## Official API Baseline

DeepSeek official docs list `https://api.deepseek.com` as the OpenAI-compatible
base URL and expose `deepseek-v4-flash` and `deepseek-v4-pro`. The same docs say
both models support JSON Output and Tool Calls, and that thinking mode is
enabled by default unless `{"thinking":{"type":"disabled"}}` is sent.

Thinking mode supports tool calls, but the docs also call out a compatibility
risk: when thinking mode performs a tool call, `reasoning_content` must be
preserved in later request history. Agno's current OpenAI message formatter
stores provider reasoning content internally, but does not include a
`reasoning_content` field when formatting the next OpenAI request.

## Evidence

- Full GLM-5.1 vs DeepSeek V4 bake-off:
  `artifacts/evidence/deepseek-model-bakeoff/20260615T014612-deepseek-v4-vs-glm51.json`
- DeepSeek planner thinking/prompt compatibility:
  `artifacts/evidence/deepseek-model-bakeoff/20260614T165753Z-deepseek-thinking-compat.json`
- DeepSeek/GLM interaction tool repeat baseline:
  `artifacts/evidence/deepseek-model-bakeoff/20260614T171200Z-interaction-repeat-baseline.json`
- Detector/Express switch guard:
  `artifacts/evidence/deepseek-model-bakeoff/20260614T172905Z-detector-express-switch-guard.json`

All calls used real provider APIs and the current Coke prompt/client paths, not
mocked model outputs.

## Findings

### Planner

The original full comparison favored current GLM-5.1 over DeepSeek on planner
correctness:

| Model | Planner pass | Parse OK | Mean latency | P95 latency |
|---|---:|---:|---:|---:|
| GLM-5.1 thinking-off | 28/34 | 34/34 | 2.852s | 5.267s |
| DeepSeek V4 Flash thinking-off | 27/34 | 33/34 | 1.383s | 1.867s |
| DeepSeek V4 Pro thinking-off | 24/34 | 34/34 | 1.263s | 1.878s |

The follow-up direct DeepSeek API test showed that enabling thinking improves
planner correctness for DeepSeek, but does not beat the GLM baseline and adds
latency:

| Model | Mode | Planner pass | Parse OK | Mean latency | P95 latency |
|---|---|---:|---:|---:|---:|
| DeepSeek V4 Flash | thinking-off | 17/34 | 34/34 | 1.772s | 3.456s |
| DeepSeek V4 Flash | thinking high | 27/34 | 34/34 | 3.367s | 5.852s |
| DeepSeek V4 Pro | thinking-off | 21/34 | 34/34 | 1.165s | 1.484s |
| DeepSeek V4 Pro | thinking high | 25/34 | 34/34 | 5.057s | 9.862s |

DeepSeek planner failures are partly prompt-sensitive. A targeted prompt-plus
experiment added narrow clarifications for reply necessity, language
preservation, batch create, calendar import, and settings preferences. It
improved the failure subset, especially Pro thinking high, but still did not
clear all cases. The recurring misses were not GLM-only syntax; they were
behavioral differences such as adding extra params, translating natural
references, treating style updates as plain replies, or using
`intentional_no_reply` after state-changing actions.

### Interaction Agent

The original interaction tool repeat showed GLM-5.1 was stable and DeepSeek was
not:

| Model | Interaction tool pass | Parse OK | Mean latency | P95 latency |
|---|---:|---:|---:|---:|
| GLM-5.1 thinking-off | 4/4 | 4/4 | 8.406s | 12.354s |
| DeepSeek V4 Flash thinking-off | 1/4 | 1/4 | 6.719s | 7.820s |
| DeepSeek V4 Pro thinking-off | 0/4 | 1/4 | 4.431s | 5.599s |

The follow-up broader interaction repeat used current `AgnoInteractionAgent`
against four real tool-intent shapes: reminder create, reminder list, settings
update, and friend link. GLM-5.1 remained the only fully passing configuration:

| Config | Pass | Parse OK | Mean latency | P95 latency |
|---|---:|---:|---:|---:|
| GLM-5.1 thinking-off | 8/8 | 8/8 | 8.577s | 8.803s |
| DeepSeek V4 Flash thinking-off | 6/8 | 8/8 | 3.158s | 4.394s |
| DeepSeek V4 Flash thinking high | 6/8 | 7/8 | 3.942s | 4.351s |
| DeepSeek V4 Pro thinking-off | 2/8 | 2/8 | 4.192s | 6.637s |
| DeepSeek V4 Pro thinking high | 6/8 | 8/8 | 4.301s | 5.117s |

The decisive failure was settings updates: DeepSeek often replied "好的" without
calling `settings_tool`, despite the current system instructions requiring a
tool call for assistant preference changes. That is unsafe for production
because it produces false success without mutating state. Pro thinking-off also
frequently returned null final output after tool calls.

### Thinking Mode

Thinking mode is not the whole answer.

- For planner, thinking high improved DeepSeek output but did not surpass the
  current GLM-5.1 baseline, and Pro thinking high had a much worse latency tail.
- For interaction, thinking high improved Pro compared with Pro thinking-off,
  but still failed settings-update cases. Flash was similar with and without
  thinking in the broader repeat.
- Thinking max on targeted planner cases was too slow for the user reply path
  and still produced parse or correctness failures.

The historical GLM evidence still matters: GLM-5.1 thinking-on previously
caused reasoning leakage, JSON corruption, and 60-85s production turn latency.
Keeping GLM-5.1 thinking disabled remains deliberate.

## Decision

Do not replace the full turn-path GLM-5.1 stack with DeepSeek V4 now. After the
follow-up production-shaped guard, switch only `detector` and `express` to
DeepSeek V4 Flash.

The switch guard ran 10 detector cases and 5 Express cases through both GLM-5.1
and DeepSeek V4 Flash using the current Coke prompt/client paths:

| Role | Model | Pass | Mean latency | P95 latency |
|---|---|---:|---:|---:|
| Detector | GLM-5.1 | 10/10 | 2.185s | 2.736s |
| Detector | DeepSeek V4 Flash | 10/10 | 0.947s | 1.077s |
| Express | GLM-5.1 | 5/5 | 6.071s | 7.376s |
| Express | DeepSeek V4 Flash | 5/5 | 1.911s | 1.960s |

DeepSeek V4 Flash had no DeepSeek-specific failures in either role.

Current stance by role:

- `interaction`: keep GLM-5.1 thinking-off. DeepSeek can be faster, but it is
  not safe because it still misses required state-changing tool calls.
- `planner`: keep GLM-5.1 thinking-off for now. DeepSeek Flash thinking high is
  close, but not better; DeepSeek Pro thinking high is slower and still less
  accurate.
- `detector`: switch to DeepSeek V4 Flash. It matched GLM correctness on the
  production-shaped guard and was faster.
- `express`: switch to DeepSeek V4 Flash. Express has no tools or direct state
  mutation, returned valid reply segments for all guard cases, and was faster.

## Follow-up

If we revisit DeepSeek for `planner` or `interaction`, the next valid path is
not a global model swap. It is a new adapter/config experiment with:

- a DeepSeek-specific planner prompt and stricter schema constraints;
- explicit regression cases for settings updates and other state-changing false
  successes;
- a decision on whether Agno must preserve `reasoning_content` in stored
  history before enabling DeepSeek thinking mode in production;
- a role-specific corpus that beats GLM-5.1 on correctness and false-success
  risk, not only latency.

## Follow-up Research: Planner and Interaction Replacement

Additional research on 2026-06-15 reran the replacement question against the
current workspace corpus and real provider APIs. Evidence:

- `artifacts/evidence/deepseek-model-bakeoff/20260615T020140Z-planner-interaction-replacement-research.json`
- `artifacts/evidence/deepseek-model-bakeoff/20260615T021332Z-interaction-tool-choice-direct.json`

Planner results changed materially when the prompt was made DeepSeek-specific:

| Config | Pass | Parse OK | Mean latency | P95 latency |
|---|---:|---:|---:|---:|
| GLM-5.1 current prompt, thinking-off | 24/36 | 36/36 | 3.630s | 7.629s |
| DeepSeek V4 Flash current prompt, thinking-off | 9/36 | 36/36 | 1.262s | 1.641s |
| DeepSeek V4 Flash prompt-plus, thinking-off | 29/36 | 36/36 | 1.261s | 1.667s |
| DeepSeek V4 Flash prompt-plus, thinking high | 31/36 | 36/36 | 2.867s | 6.478s |
| DeepSeek V4 Pro prompt-plus, thinking-off | 29/36 | 36/36 | 1.353s | 1.775s |

The planner conclusion is now narrower than the original issue decision:
DeepSeek should not be dropped into the current planner prompt, but
`deepseek-v4-flash` with a dedicated planner prompt is a credible next
replacement candidate. The remaining misses are concentrated around shared
reminder creation/cancellation in Chinese, availability date granularity,
timezone wording, and a few raw-text/extra-param differences. Some failures also
expose current corpus/product-contract tension, especially `set_timezone`
expecting natural text while the planner prompt requires an IANA timezone.

Interaction still should not be swapped through the current Agno Agent path.
The current Agno path produced:

| Config | Pass | Parse OK | Mean latency | P95 latency |
|---|---:|---:|---:|---:|
| GLM-5.1 auto tools, thinking-off | 8/8 | 8/8 | 10.360s | 17.161s |
| DeepSeek V4 Flash auto tools, thinking-off | 6/8 | 7/8 | 4.252s | 7.173s |

The two DeepSeek misses were both `settings_update`: one blank/non-parse output
and one false-success reply with no `settings_tool` call. A separate direct
DeepSeek API test proved the provider can do the required settings tool flow
when the first model turn uses `tool_choice=required` or a named
`settings_tool`, and the second model turn uses `tool_choice=none` plus JSON
output. Flash non-thinking completed that two-step flow in 1.65-1.97s; Pro
non-thinking completed it in 2.76s. Flash thinking with `tool_choice=required`
returned HTTP 400: `Thinking mode does not support this tool_choice`.

That means the blocker is not DeepSeek API availability. The blocker is the
current Interaction integration shape:

- Agno-level static `tool_choice=required` did not settle promptly and was
  interrupted; it is not a safe one-line fix because the final reply turn must
  stop calling tools.
- DeepSeek sometimes emits tool arguments with a nested JSON string for
  `command`. Coke already has normalization that can parse string payloads, but
  the current `command: dict | None` tool annotation lets Agno/Pydantic reject
  those calls before Coke normalization runs.
- Thinking mode is unsuitable for the current Interaction tool loop unless the
  adapter also preserves `reasoning_content` across tool-call turns and avoids
  unsupported `tool_choice` combinations.

Replacement recommendation after this research:

- `planner`: proceed with a branch that adds a provider-specific planner prompt
  and validates it against a refreshed planner corpus. The best candidate is
  `deepseek-v4-flash` prompt-plus. Default should stay non-thinking unless the
  remaining 2 extra passes from thinking high are worth the higher tail latency.
- `interaction`: do not replace the current Agno tool-loop agent directly.
  Viable next designs are either a direct two-step DeepSeek tool adapter with
  first-turn tool choice and final-turn `tool_choice=none`, or moving more
  state-changing work through Planner/Execute and leaving Interaction/Express to
  render trusted results. Both require code changes and a false-success
  regression suite before production use.
