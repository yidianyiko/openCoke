# Chat Response SiliconFlow DeepSeek V4 Flash

## Goal

Route the interact/chat response agent away from the OpenAI `gpt-4o` override
and onto the same SiliconFlow-backed model configuration path used by the
other worker-runtime agents.

## Surfaces

- `worker-runtime`
- `deploy`

## Notes

- Local config now sets `llm.roles.chat_response` to SiliconFlow model
  `deepseek-ai/DeepSeek-V4-Flash`.
- Production deploy config also declares the `llm` block explicitly so the
  mounted `/app/conf/config.json` does not fall back to the model factory's
  default official DeepSeek provider.
