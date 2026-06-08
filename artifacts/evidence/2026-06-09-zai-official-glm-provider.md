# Z.AI Official GLM Provider Verification

Date: 2026-06-09

## Scope

Changed text LLM provider configuration from a single SiliconFlow-owned config
to official Z.AI for the three GLM roles:

- Semantic interpreter.
- Interaction agent.
- Reminder detector.

Media model access remains SiliconFlow-only for:

- `FunAudioLLM/SenseVoiceSmall`.
- `Qwen/Qwen3-VL-32B-Instruct`.

## Red Test

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Result before implementation:

```text
ERROR tests/unit/coke/llm/test_config.py
ImportError: cannot import name 'ZAI_BASE_URL' from 'coke.llm.config'
```

## Targeted Verification

Command:

```bash
.venv/bin/python -m pytest tests/unit/coke/llm/test_config.py tests/unit/coke/test_backend_foundation.py tests/integration/coke/test_runtime_wiring.py tests/unit/coke/deploy/test_clean_compose_deploy_contract.py -v
```

Result after implementation:

```text
74 passed
```

## Diff-Aware Routing

Command:

```bash
zsh scripts/suggest-verification --base HEAD~1
```

Suggested command:

```bash
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Command:

```bash
zsh scripts/review-trigger --base HEAD~1
```

Result:

```text
human_review_required: no
risk_triggers: yes
```

The risk trigger was expected for runtime config/docs changes and missing
evidence before this file was added.

## Suggested Surface Verification

Command:

```bash
zsh scripts/verify-surface clean-rebuild-backend repo-os-docs
```

Result:

```text
clean-rebuild-backend: 843 passed
repo-os-docs: scripts/check passed
```
