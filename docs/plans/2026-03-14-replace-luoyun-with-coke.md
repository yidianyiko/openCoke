# Replace Legacy Name With `coke` Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the stale legacy name with `coke` in the active Ecloud codepath without breaking voice message handling, startup scripts, or any alias-to-`wId` runtime mapping.

**Architecture:** Treat the legacy name as two different classes of reference: live runtime temp-path usage in the legacy Ecloud flow, and non-runtime leftovers in local demos or comments. Replace the live temp-path dependency with `coke` first, add regression tests around voice download/transcription flow, then clean up demo references and operational docs.

**Tech Stack:** Python 3.12, pytest, Flask/Gunicorn Ecloud service, shell startup scripts, ripgrep for verification.

### Task 1: Lock down current legacy temp-path usage with tests

**Files:**
- Modify: `tests/unit/connector/test_ecloud_adapter.py`
- Inspect: `connector/ecloud/ecloud_adapter.py`

**Step 1: Write the failing test**

Add a unit test that mocks:
- `connector.ecloud.ecloud_adapter.Ecloud_API.getMsgVoice`
- `agent.tool.image.download_image`
- `framework.tool.voice2text.aliyun_asr.voice_to_text`

Assert that voice message conversion:
- calls `download_image(...)` with a neutral temp directory such as `agent/temp/`
- returns the transcribed text and saved file path in metadata

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -k voice -v`
Expected: FAIL because the current code still hard-codes the old temp path.

**Step 3: Write minimal implementation**

Do not change behavior yet beyond the path target. Update `connector/ecloud/ecloud_adapter.py` so the downloaded voice file lands in a repo-neutral temp directory used by the application, not a character-specific directory name.

Recommended target:
- `agent/temp/` if the team wants to reuse an existing temp location
- otherwise introduce a constant like `ECLOUD_TEMP_DIR = "connector/ecloud/temp/"`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/connector/test_ecloud_adapter.py -k voice -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/connector/test_ecloud_adapter.py connector/ecloud/ecloud_adapter.py
git commit -m "test(ecloud): cover voice temp path handling"
```

### Task 2: Update startup and ignore rules to the new temp directory

**Files:**
- Modify: `.gitignore`
- Modify: `connector/ecloud/ecloud_start.sh`

**Step 1: Write the failing check**

Use search-based verification before editing:

Run: `rg -n "legacy/temp/" .gitignore connector/ecloud/ecloud_start.sh connector/ecloud/ecloud_adapter.py`
Expected: 3 matches before cleanup.

**Step 2: Write minimal implementation**

Change:
- `.gitignore` to ignore `coke/temp/` instead of the old temp path
- `connector/ecloud/ecloud_start.sh` to `mkdir -p` the new directory

Keep directory creation aligned with the path used in `connector/ecloud/ecloud_adapter.py`.

**Step 3: Run verification**

Run: `rg -n "legacy/temp/" .gitignore connector/ecloud/ecloud_start.sh connector/ecloud/ecloud_adapter.py`
Expected: no matches

Run: `bash -n connector/ecloud/ecloud_start.sh`
Expected: no syntax errors

**Step 4: Commit**

```bash
git add .gitignore connector/ecloud/ecloud_start.sh connector/ecloud/ecloud_adapter.py
git commit -m "refactor(ecloud): replace legacy temp directory with coke"
```

### Task 3: Clean up non-runtime demo references

**Files:**
- Modify: `connector/ecloud/ecloud_api.py`
- Modify: `framework/tool/voice2text/aliyun_asr.py`
- Modify: `framework/tool/text2image/liblib.py`

**Step 1: Write the failing check**

Run: `rg -n "legacy_name" connector/ecloud/ecloud_api.py framework/tool/voice2text/aliyun_asr.py framework/tool/text2image/liblib.py`
Expected: matches in `__main__` blocks, helper names, or comments.

**Step 2: Write minimal implementation**

Clean up only non-runtime leftovers:
- rename the old helper to a `coke`-specific helper name
- replace the hard-coded demo alias in `connector/ecloud/ecloud_api.py` with a config-driven alias or `coke`
- replace the hard-coded old temp path in `framework/tool/voice2text/aliyun_asr.py` demo code with `coke/temp/...`
- remove or neutralize comments that embed old repo paths

Do not change production request payload structure in this task.

**Step 3: Run verification**

Run: `python -m compileall connector/ecloud/ecloud_api.py framework/tool/voice2text/aliyun_asr.py framework/tool/text2image/liblib.py`
Expected: successful compilation

Run: `rg -n "legacy_name" connector/ecloud/ecloud_api.py framework/tool/voice2text/aliyun_asr.py framework/tool/text2image/liblib.py`
Expected: no matches, unless an intentional historical string remains in a test fixture

**Step 4: Commit**

```bash
git add connector/ecloud/ecloud_api.py framework/tool/voice2text/aliyun_asr.py framework/tool/text2image/liblib.py
git commit -m "chore: replace stale legacy demo references with coke"
```

### Task 4: Verify that alias-based Ecloud runtime still works

**Files:**
- Inspect: `conf/config.json`
- Inspect: `connector/ecloud/ecloud_input.py`
- Inspect: `connector/ecloud/ecloud_output.py`
- Inspect: `agent/runner/message_processor.py`

**Step 1: Run targeted tests**

Run:
- `pytest tests/unit/connector/test_ecloud_adapter.py -v`
- `pytest tests/unit/connector/test_stream_publish.py -v`
- `pytest tests/unit/connector/test_creem_webhook.py -v`
- `pytest tests/unit/connector/test_stripe_webhook.py -v`

Expected: PASS

**Step 2: Run static verification**

Run: `rg -n "default_character_alias|wId|target_user_alias" conf/config.json connector/ecloud agent/runner`
Expected: runtime alias handling still points to config-driven names like `qiaoyun` or current configured aliases, not the legacy name.

**Step 3: Run final repository sweep**

Run: `rg -n "legacy_name" .`
Expected: no matches, or only deliberately preserved historical fixtures with a documented reason

**Step 4: Commit**

```bash
git add -A
git commit -m "test(ecloud): verify coke naming replacement is safe"
```

### Task 5: Operational rollout

**Files:**
- Inspect: `docs/deploy.md`
- Inspect: `start.sh`
- Inspect: `ecosystem.config.json`

**Step 1: Pre-deploy check**

Confirm the new temp directory exists in all relevant start paths:
- local Ecloud start script
- top-level `start.sh`
- PM2 or process manager entrypoints if they rely on precreated directories

**Step 2: Deploy to a non-production environment**

Run the normal startup path and send:
- one text message
- one image message
- one voice message
- one group mention if group chat is enabled

Expected: text/image/voice/group flows still work, and voice files are written to the new temp directory.

**Step 3: Production rollout**

Deploy only after the non-production smoke test passes. Watch:
- `connector/ecloud/ecloud.log`
- application logs for `voice_to_text` failures
- filesystem permissions on the new temp directory

**Step 4: Cleanup**

After one stable release window, remove any empty leftover legacy-named directory on hosts if it still exists outside git.
