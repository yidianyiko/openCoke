# Shared Channel Package Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split channel shared types so frontend code can import only frontend-safe channel enums/DTOs while provider config schemas and config-bearing channel write shapes live behind backend-only Channel modules.

**Architecture:** Keep `@clawscale/shared` limited to frontend-safe channel contracts. Move provider config/form schemas and any config-bearing admin channel types into backend-only modules under `gateway/packages/api/src/channel/`. Consume shared channel enums through the workspace package name (`@clawscale/shared`), not by reaching into `../shared/src`, and add a repo-OS guardrail that rejects `gateway/packages/web` imports of backend-only channel paths or `CHANNEL_CONFIG_SCHEMA`.

**Tech Stack:** TypeScript, pnpm, Vitest, Python guardrail tests, zsh repo-OS checks.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Verify current imports with `rg -n "@clawscale/shared|shared/src/types/channel|CHANNEL_CONFIG_SCHEMA" gateway/packages` before execution.

## Scope

Included:

- Keep only frontend-safe channel enums and read-only DTOs in `gateway/packages/shared/src/types/channel.ts`.
- Move provider config schema constants, config field types, and config-bearing channel write shapes to backend-only Channel modules.
- Update API/admin imports to use backend-only modules and shared package imports.
- Add a guardrail test and script behavior that blocks frontend imports from backend-only channel internals.

Excluded:

- Field-by-field channel DTO inventory beyond the moved provider config schema.
- Runtime behavior changes to provider dispatch.
- HTTP extraction of Channel service.

## File Map

- `gateway/packages/shared/src/types/channel.ts`: keep only frontend-safe channel enums/read DTOs; remove `ChannelConfigField`, `CHANNEL_CONFIG_SCHEMA`, and any config-bearing `Channel`/write payload shapes.
- `gateway/packages/api/src/channel/provider-config-schema.ts`: new backend-only provider config schema and `ChannelConfigField`.
- `gateway/packages/api/src/channel/provider-config-schema.test.ts`: tests proving schema exports include existing providers.
- `gateway/packages/api/package.json`: add explicit workspace dependency on `@clawscale/shared` if the API package does not already declare it.
- `gateway/packages/api/src/routes/admin-shared-channels.ts`: update imports if it uses shared config schema.
- `scripts/guardrails.py`: add import-boundary helper for frontend/backend channel paths.
- `tests/unit/test_guardrail_scripts.py`: add failing import-boundary tests.
- `docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`: mark hard prerequisite status only after code and guardrail land.

## Work Breakdown

### Task 0: Preflight Frontend Usage Of Removed Shared Types

**Files:**
- Read: `gateway/packages/web`, `gateway/packages/api`

- [x] **Step 1: Verify no web code currently imports the types being removed**

The plan removes `Channel`, `CreateChannelPayload`, `UpdateChannelPayload`, `ChannelConfigField`, and `CHANNEL_CONFIG_SCHEMA` from the shared package. Before deleting them, prove that `gateway/packages/web` does not depend on them:

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary
rg -n "from '@clawscale/shared'.*\\b(Channel|CreateChannelPayload|UpdateChannelPayload|ChannelConfigField|CHANNEL_CONFIG_SCHEMA)\\b" \
  gateway/packages/web \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/preflight-web.txt
rg -n "\\b(Channel|CreateChannelPayload|UpdateChannelPayload|ChannelConfigField|CHANNEL_CONFIG_SCHEMA)\\b" \
  gateway/packages/web \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/preflight-web-broad.txt
```

Expected: the import-targeted scan returns no matches. If the broad scan finds local declarations that re-export or rename, document them in the evidence file and migrate them in this plan before deletion. **Do not delete a shared symbol without first verifying or fixing every web reference.**

- [x] **Step 2: Catalog every API caller of the moved schema**

```bash
rg -n "CHANNEL_CONFIG_SCHEMA|ChannelConfigField" gateway/packages/api/src \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/preflight-api-callers.txt
```

Expected: every match is a file whose import will be updated in Task 2.

### Task 1: Move Provider Config Schema Out Of Shared Types

**Files:**
- Modify: `gateway/packages/shared/src/types/channel.ts`
- Create: `gateway/packages/api/src/channel/provider-config-schema.ts`
- Test: `gateway/packages/api/src/channel/provider-config-schema.test.ts`

- [x] **Step 1: Write backend schema test**

Create `gateway/packages/api/src/channel/provider-config-schema.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { CHANNEL_CONFIG_SCHEMA } from './provider-config-schema.js';

describe('provider config schema boundary', () => {
  it('keeps provider config schema in the backend-only channel module', () => {
    expect(CHANNEL_CONFIG_SCHEMA.whatsapp_business.fields.map((field) => field.key)).toEqual([
      'phoneNumberId',
      'accessToken',
      'verifyToken',
    ]);
    expect(CHANNEL_CONFIG_SCHEMA.wechat_ecloud.fields.map((field) => field.key)).toEqual([
      'appId',
      'token',
      'baseUrl',
    ]);
    expect(CHANNEL_CONFIG_SCHEMA.linq.fields.map((field) => field.key)).toEqual([
      'fromNumber',
    ]);
  });
});
```

- [x] **Step 2: Move `ChannelConfigField` and `CHANNEL_CONFIG_SCHEMA`**

Create `gateway/packages/api/src/channel/provider-config-schema.ts` with the exact `ChannelConfigField` interface and `CHANNEL_CONFIG_SCHEMA` constant currently in `gateway/packages/shared/src/types/channel.ts`. Import `ChannelType` from `@clawscale/shared`, and add `@clawscale/shared` to `gateway/packages/api/package.json` as a workspace dependency if it is not already declared.

Expected: backend-only module owns provider config schema.

- [x] **Step 3: Trim shared channel types**

Remove `ChannelConfigField`, `CHANNEL_CONFIG_SCHEMA`, `Channel`, `CreateChannelPayload`, and `UpdateChannelPayload` from `gateway/packages/shared/src/types/channel.ts`.

Expected: shared file exports only frontend-safe channel enums/read DTOs and no config-bearing shape remains frontend-importable.

- [x] **Step 4: Run focused API test**

Run:

```bash
pnpm --dir gateway/packages/shared build
pnpm --dir gateway/packages/api build
pnpm --dir gateway/packages/api test provider-config-schema
```

Expected: shared and API builds pass, and the new backend-only schema test passes.

### Task 2: Update API Imports

**Files:**
- Modify: `gateway/packages/api/src/routes/admin-shared-channels.ts`
- Search: `gateway/packages/api/src`

- [x] **Step 1: Find all schema consumers**

Run:

```bash
rg -n "CHANNEL_CONFIG_SCHEMA|ChannelConfigField" gateway/packages/api/src gateway/packages/web
```

Expected before migration: matches outside the new backend-only module identify files to update. `gateway/packages/web` must have no matches.

- [x] **Step 2: Update API imports**

For any API file importing provider schema from shared types, replace it with:

```ts
import { CHANNEL_CONFIG_SCHEMA, type ChannelConfigField } from '../channel/provider-config-schema.js';
```

Use the correct relative path from the edited file.

- [x] **Step 3: Verify no frontend schema import exists**

Run:

```bash
rg -n "CHANNEL_CONFIG_SCHEMA|ChannelConfigField|provider-config-schema" gateway/packages/web
```

Expected: no matches.

### Task 3: Add Import Boundary Guardrail

**Files:**
- Modify: `scripts/guardrails.py`
- Modify: `tests/unit/test_guardrail_scripts.py`
- Modify: `scripts/check`

- [x] **Step 1: Add comprehensive guardrail tests (positive and negative)**

Add to `tests/unit/test_guardrail_scripts.py`. The tests must prove both that the guardrail catches real import violations AND that it does not false-positive on text that merely mentions the symbol:

```python
def test_check_import_boundaries_rejects_backend_path_import():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } "
            "from '../../api/src/channel/provider-config-schema';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("imports backend-only channel internals" in e for e in errors)


def test_check_import_boundaries_rejects_named_import_via_alias():
    from scripts import guardrails

    files = {
        "gateway/packages/web/lib/bad-alias.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } from '@coke/api-channel';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert any("CHANNEL_CONFIG_SCHEMA" in e for e in errors)


def test_check_import_boundaries_allows_user_visible_copy():
    from scripts import guardrails

    files = {
        "gateway/packages/web/app/help.tsx": (
            "export function Help() {\n"
            "  // Explanation of CHANNEL_CONFIG_SCHEMA appears in admin help text.\n"
            "  return <p>Configure your channel under settings.</p>;\n"
            "}\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert errors == []


def test_check_import_boundaries_ignores_non_web_files():
    from scripts import guardrails

    files = {
        "gateway/packages/api/src/routes/x.ts": (
            "import { CHANNEL_CONFIG_SCHEMA } "
            "from '../channel/provider-config-schema';\n"
        )
    }
    errors = guardrails.check_import_boundaries(list(files), read_text=files.__getitem__)
    assert errors == []
```

Expected before implementation: every test fails because `check_import_boundaries` does not exist.

- [x] **Step 2: Implement guardrail helper**

Add to `scripts/guardrails.py`. The detector must match real import statements (not just bare text), so a comment, a string literal in user-visible copy, or a CHANGELOG entry does not false-positive. We still keep a literal-path needle for the backend-only module path because that is unambiguous:

```python
import re

_IMPORT_LINE_RE = re.compile(
    r"""
    ^[ \t]*
    (?:import\b|export\s+(?:\*|\{)|require\s*\()
    [^;\n]*?
    ['"]([^'"\n]+)['"]
    """,
    re.MULTILINE | re.VERBOSE,
)


def check_import_boundaries(
    files: list[str],
    read_text=lambda path: (ROOT / path).read_text(encoding="utf-8"),
) -> list[str]:
    errors: list[str] = []
    forbidden_path_fragments = (
        "api/src/channel/provider-config-schema",
        "gateway/packages/api/src/channel/",
    )
    forbidden_named_symbols = ("CHANNEL_CONFIG_SCHEMA", "ChannelConfigField")
    for file_path in files:
        normalized = file_path.strip().lstrip("./")
        if not normalized.startswith("gateway/packages/web/"):
            continue
        if not normalized.endswith((".ts", ".tsx", ".mts")):
            continue
        text = read_text(normalized)
        # 1. Any import statement that targets a backend-only path is forbidden.
        for match in _IMPORT_LINE_RE.finditer(text):
            target = match.group(1)
            if any(fragment in target for fragment in forbidden_path_fragments):
                errors.append(
                    f"{normalized} imports backend-only channel internals: {target}"
                )
        # 2. Importing the symbol by name (named import / re-export) is forbidden,
        #    even via an aliased path.
        for symbol in forbidden_named_symbols:
            named_import = re.compile(
                rf"^[ \t]*(?:import|export)\b[^;]*\b{re.escape(symbol)}\b[^;]*from\b",
                re.MULTILINE,
            )
            if named_import.search(text):
                errors.append(
                    f"{normalized} imports backend-only channel symbol: {symbol}"
                )
    return errors
```

This intentionally allows the words to appear in JSX copy or comments but rejects any actual import. Add a focused test that proves a comment does NOT trip the guardrail.

- [x] **Step 3: Wire guardrail into `scripts/check`**

Add a small Python invocation to `scripts/check` after doc structure checks:

```zsh
if ! "$python_cmd" scripts/guardrails.py check-import-boundaries; then
  missing=1
fi
```

Also add a `check-import-boundaries` subcommand in `scripts/guardrails.py` that collects tracked `gateway/packages/web` files and prints `OK import boundaries` or each error before returning non-zero.

- [x] **Step 4: Verify guardrail behavior**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_guardrail_scripts.py -v
zsh scripts/check
```

Expected: focused guardrail tests and repo check pass.

### Task 4: Verify Gateway Builds And Bundle Has No Backend Leakage

**Files:**
- Read: changed gateway package files
- Create: `scripts/e2e/shared-channel-package-boundary.sh`

- [x] **Step 1: Run package tests with evidence emission**

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary
pnpm --dir gateway/packages/api test \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/api-test.log
pnpm --dir gateway/packages/web test \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/web-test.log
```

Expected: API and web tests pass; evidence logs are written for review.

- [x] **Step 2: Run surface verification**

```bash
zsh scripts/verify-surface gateway-api gateway-web repo-os \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/verify-surface.log
```

Expected: all commands pass.

- [x] **Step 3: E2E bundle scan — provider secrets must not appear in the web bundle**

Create `scripts/e2e/shared-channel-package-boundary.sh` (executable) that:

1. Runs `pnpm --dir gateway/packages/web build` (or the package's production build command).
2. Searches the produced bundle output for known backend-only sentinels and reports each hit:
   - `CHANNEL_CONFIG_SCHEMA`
   - `provider-config-schema`
   - `whatsapp_business`/`wechat_ecloud`/`linq` configuration *field key arrays* (e.g., `phoneNumberId,accessToken,verifyToken`)
3. Writes results to `artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary/bundle-scan.txt`.
4. Exits non-zero if any sentinel is found.

The script must emit structured `[BEGIN]`/`[STEP <name>]`/`[OK <name>]`/`[FAIL <name> <reason>]` log lines so a CI run produces an obvious failure trail.

Expected: the bundle does not contain backend-only schema content, proving the package split is effective at the bundle layer (not just at import-time).
