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

Production defaults are now set (not eval-selected) so the feature ships
non-empty, per explicit product decision on 2026-06-01:

- VLM (image -> text): `Qwen/Qwen3-VL-32B-Instruct`
- ASR (voice fallback): `FunAudioLLM/SenseVoiceSmall`

Both were verified live against the SiliconFlow `/v1/models` catalog using the
actual `coke/llm/media_text.py` client request shapes on 2026-06-01:
`Qwen3-VL-32B-Instruct` returned a correct caption via `/chat/completions`, and
`SenseVoiceSmall` returned HTTP 200 on `/audio/transcriptions`. Defaults live in
`coke/llm/config.py` (`DEFAULT_VISION_TEXT_MODEL`, `DEFAULT_ASR_MODEL`) and are
overridable via `COKE_VISION_TEXT_MODEL` / `COKE_ASR_MODEL`.

The subset-eval path remains the mechanism to *tune* the selection later. The
harness enforces 30-50 cases per manifest; the representative media corpus is
still not in the repo, so eval-based reselection stays pending until captured
media evidence is added under `artifacts/evidence/wechat-personal-media/`. The
current defaults are a verified-working baseline, not an eval-optimized choice.
