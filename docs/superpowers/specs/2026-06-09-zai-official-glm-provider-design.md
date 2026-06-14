# Z.AI Official GLM Provider Design

## Status

Approved for implementation on 2026-06-09.

## Goal

Move Coke's three text GLM roles from SiliconFlow-hosted GLM to official Z.AI
GLM, while keeping image and voice fallback media models on SiliconFlow.

## Current Problem

The runtime currently uses one `SiliconFlowLLMConfig` for all model access:

- Semantic interpreter.
- Interaction agent.
- Reminder detector.
- Image-to-text model.
- ASR fallback model.

That single config forces one `base_url` and one API key across text GLM and
media models. It cannot switch text GLM to official Z.AI without also pointing
Qwen3-VL-32B-Instruct and SenseVoiceSmall at Z.AI, where those media models are
not hosted.

## Provider Facts

Official Z.AI docs verified during design:

- OpenAI-compatible base URL: `https://api.z.ai/api/paas/v4/`.
- GLM-5.1 model id: `glm-5.1`.
- GLM-5.1 thinking is enabled by default.
- Thinking is disabled with `thinking: {"type": "disabled"}`.

The current SiliconFlow media facts remain unchanged:

- ASR fallback: `FunAudioLLM/SenseVoiceSmall`.
- Image text: `Qwen/Qwen3-VL-32B-Instruct`.
- SiliconFlow OpenAI-compatible base URL: `https://api.siliconflow.cn/v1`.

## Design

Split model configuration by provider responsibility.

`ZAILLMConfig` owns the three text GLM roles:

- `api_key` from `ZAI_API_KEY`.
- `base_url` from `ZAI_BASE_URL`, defaulting to
  `https://api.z.ai/api/paas/v4/`.
- `interaction_model`, `interpreter_model`, and `detector_model`, each
  defaulting to `glm-5.1`.
- `interaction_timeout_s`.
- Agno database settings.
- `create_*_model()` methods that build Agno `OpenAILike` models with
  `extra_body={"thinking": {"type": "disabled"}}`.

`SiliconFlowMediaConfig` owns media-only model access:

- `api_key` from `SiliconFlow_API_KEY`.
- `base_url` from `SILICONFLOW_BASE_URL`, defaulting to
  `https://api.siliconflow.cn/v1`.
- `asr_model`, `vision_text_model`, and `media_model_timeout_s`.

`Settings` exposes both provider groups. Production real-LLM startup requires
`ZAI_API_KEY`; `SiliconFlow_API_KEY` is required only when a media model is
configured. Fake LLM mode keeps bypassing real model keys.

`_llm_from_settings()` composes text components from `ZAILLMConfig` and media
resolver clients from `SiliconFlowMediaConfig`. Text GLM no longer reuses the
SiliconFlow key or base URL.

The deployment script writes `ZAI_API_KEY` into the clean env and preserves
`SiliconFlow_API_KEY` for media. It must not require SiliconFlow as the primary
LLM provider.

## Non-Goals

- Do not change prompts, output protocol, or model quality behavior beyond the
  provider switch and Z.AI thinking-disable request shape.
- Do not move Qwen3-VL-32B-Instruct or SenseVoiceSmall to Z.AI.
- Do not remove media support.
- Do not edit local secret values in `.env`.

## Verification

Use TDD for the config migration:

- Unit tests for Z.AI text config defaults, overrides, required key, and
  OpenAILike request shape.
- Unit tests for SiliconFlow media config defaults and required key.
- Settings tests for `ZAI_API_KEY` production enforcement and media key
  preservation.
- Runtime wiring test proving text and media can be configured independently.
- Deploy contract test proving deploy env requires and writes `ZAI_API_KEY`.
- Diff-aware verification routing after the targeted tests pass.
