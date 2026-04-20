# Reminder Tool-Call Benchmark Design

## Goal

Compare reminder creation accuracy and tool-call behavior across three SiliconFlow-hosted models:

- `Pro/MiniMaxAI/MiniMax-M2.5`
- `Pro/zai-org/GLM-5.1`
- `Pro/moonshotai/Kimi-K2.5`

The benchmark should separate:

1. Orchestrator gate accuracy (`need_reminder_detect`)
2. Reminder tool-call accuracy (`reminder_tool` call / create behavior)

## Scope

This benchmark only measures reminder-related decision quality. It does not grade full conversational quality, wording, empathy, or long-horizon memory.

## Approach

Use the existing Agno runtime and current prompts. Switch only the configured model ID between runs. For each case:

1. Build a deterministic sample `session_state`
2. Run `OrchestratorAgent` to score gate accuracy
3. Run `ReminderDetectAgent` to score tool-call accuracy
4. Capture whether `reminder_tool` was called, whether a reminder/task was created, and whether the result had a trigger time

## Dataset

Use a small labeled benchmark set with both positive and negative cases:

- Explicit timed reminders
- Explicit no-time task capture
- Vague reminder requests that should not create
- Invalid reminder requests that should not create
- Ordinary planning / summarization / template requests that should never trigger reminder tools

Each case carries gold labels for:

- `expect_gate`
- `expect_tool_call`
- `expect_create`
- `expect_has_time`

## Output

Produce:

- Per-model summary metrics:
  - gate accuracy
  - tool-call precision / recall / F1
  - create accuracy
  - timed-create accuracy
  - false-positive rate on negative cases
- Case-by-case JSON artifact for later inspection
- A markdown table summarizing results

## Non-Goals

- No business-logic changes to reminder behavior
- No production deployment
- No model fine-tuning or prompt rewriting in this step
