---
kind: progress_note
status: active
date: 2026-06-01
topic: wechat personal media model selection
surfaces:
  - coke/llm/media_text.py
  - scripts/eval-media-model-subset
---

# WeChat Personal Media Model Selection

## Requirement

Select SiliconFlow ASR and VLM model IDs through representative subset evaluation before production configuration.

## Candidate Families

- ASR: SenseVoice family only.
- VLM: Qwen-VL family only.

## Evidence Command

```bash
SiliconFlow_API_KEY=$SiliconFlow_API_KEY scripts/eval-media-model-subset \
  --asr-model sensevoice-candidate \
  --vision-model qwen-vl-candidate \
  --asr-manifest artifacts/evidence/wechat-personal-media/asr-subset.jsonl \
  --vision-manifest artifacts/evidence/wechat-personal-media/vision-subset.jsonl
```

## Current Status

The harness enforces 30-50 cases per manifest. The representative media corpus is not present in the repository on 2026-06-01, so model IDs must remain environment-configured and unset by default until captured media evidence is added under `artifacts/evidence/wechat-personal-media/`.
