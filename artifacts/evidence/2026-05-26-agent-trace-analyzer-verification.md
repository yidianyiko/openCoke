# Agent Trace Analyzer Verification

Date: 2026-05-26

Scope:

- `scripts/agent_turn_trace_analyzer.py`
- `scripts/analyze_agent_turn_traces.py`
- `tests/unit/test_agent_turn_trace_analyzer.py`
- `docs/design-docs/agent-trace-feedback-loop.md`
- `docs/superpowers/specs/2026-05-26-agent-trace-analyzer-design.md`
- `docs/superpowers/plans/2026-05-26-agent-trace-analyzer.md`

## Commands

Focused analyzer tests:

```text
.venv/bin/python -m pytest tests/unit/test_agent_turn_trace_analyzer.py -q
3 passed in 0.23s
```

Synthetic CLI smoke:

```text
.venv/bin/python scripts/analyze_agent_turn_traces.py /tmp/coke-agent-trace.<id>.jsonl
schema_version: agent_trace_analysis.v1
record_count: 1
route_counts: reminder_domain=1
selected_tool_counts: create_reminder=1
unused_exposed_tool_counts: cancel_reminder=1
positive_loop: observe -> analyze -> choose -> change -> verify -> compare -> record
```

Diff-aware routing:

```text
zsh scripts/suggest-verification --base HEAD~2
changed_surfaces: repo-os-docs
suggested_command: zsh scripts/verify-surface repo-os-docs
```

Review trigger:

```text
zsh scripts/review-trigger --base HEAD~2
human_review_required: yes
- sensitive_repo_os_change
- oversized_change
```

The review trigger is expected for this change because it adds repo-OS docs,
spec, and plan material. It did not report a functional test failure.

Suggested surface verification:

```text
zsh scripts/verify-surface repo-os-docs
check passed
```

Whitespace check:

```text
git diff --check HEAD~2..HEAD
passed with no output
```

## Result

The analyzer path is verified at unit-test, CLI-smoke, and repo-OS structure
levels. The remaining gate is human review for sensitive repo-OS documentation
and diff size.
