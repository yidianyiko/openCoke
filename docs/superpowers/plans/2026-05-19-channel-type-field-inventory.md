# Channel Type Field Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inventory the remaining shared channel types after the package split and classify each field/type as frontend-safe DTO, backend-only provider config, or backend-only admin/write contract.

**Architecture:** Keep classification in a reviewable docs table after the shared split removes config-bearing channel shapes from `@clawscale/shared`. Inventory the frontend-safe shared exports and the backend-only provider schema side by side so later drift is obvious in review. Do not add new abstractions unless the inventory shows repeated drift.

**Tech Stack:** Markdown docs, TypeScript type exports, Vitest, repo-OS docs checks.

---

**Plan Status:** completed
**Status Date:** 2026-05-20
**Freshness Check:** Execute after `2026-05-19-shared-channel-package-boundary.md` lands.

## Scope

Included:

- Classify the frontend-safe exports that remain in `gateway/packages/shared/src/types/channel.ts`.
- Classify backend-only provider schema fields from `gateway/packages/api/src/channel/provider-config-schema.ts`.
- Document that config-bearing admin/write shapes are backend-only even if they remain route-local instead of becoming shared types.

Excluded:

- Provider schema redesign.
- Runtime channel lifecycle behavior changes.
- Route ownership registry.

## File Map

- `docs/design-docs/channel-field-inventory.md`: new field inventory table.
- `docs/design-docs/index.md`: add link to inventory.
- `gateway/packages/shared/src/types/channel.ts`: add short comment pointing to inventory.
- `gateway/packages/api/src/channel/provider-config-schema.ts`: add short comment pointing to inventory.
- `gateway/packages/api/src/channel/provider-config-schema.test.ts`: keep backend-only field expectations aligned with the inventory.

## Work Breakdown

### Task 1: Create Channel Field Inventory Doc

**Files:**
- Create: `docs/design-docs/channel-field-inventory.md`
- Modify: `docs/design-docs/index.md`

- [x] **Step 1: Create inventory doc**

Create `docs/design-docs/channel-field-inventory.md`:

```markdown
# Channel Field Inventory

This document classifies channel fields after the Frontend / Platform /
Channel boundary split. The detailed ownership rule lives in
`docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md`.

## Classification

| Field or type | Classification | Owner | Allowed importers | Notes |
| --- | --- | --- | --- | --- |
| `ChannelType` | frontend-safe DTO | Channel System | web, api | Public channel kind identifier. |
| `ChannelStatus` | frontend-safe DTO | Channel System | web, api | Displayable status only; action truth comes from backend contracts. |
| `ChannelConfigField` | backend-only provider schema field | Channel System | api only | Lives in `provider-config-schema.ts`; may describe secrets or provider-only knobs. |
| `CHANNEL_CONFIG_SCHEMA` | backend-only provider schema | Channel System | api only | Lives in backend-only Channel module. |
| config-bearing admin channel create/update bodies | backend-only admin/write contract | Channel System | api/admin only | Keep out of `@clawscale/shared`; define locally in backend modules or route validators. |
```

## Rule

No provider secret, webhook token, app token, access token, or provider-specific
credential field may be imported by `gateway/packages/web`.
```

- [x] **Step 2: Link inventory from design docs index**

Add `docs/design-docs/channel-field-inventory.md` to `docs/design-docs/index.md`.

### Task 2: Add Code Comments At Boundary Files

**Files:**
- Modify: `gateway/packages/shared/src/types/channel.ts`
- Modify: `gateway/packages/api/src/channel/provider-config-schema.ts`

- [x] **Step 1: Add shared DTO comment**

Add near the top of `channel.ts`:

```ts
// Frontend-safe channel enums/read DTOs only. Provider config schemas live in
// gateway/packages/api/src/channel/provider-config-schema.ts; see
// docs/design-docs/channel-field-inventory.md for field classification.
```

- [x] **Step 2: Add backend schema comment**

Add near the top of `provider-config-schema.ts`:

```ts
// Backend-only provider configuration schema. Do not import from
// gateway/packages/web; see docs/design-docs/channel-field-inventory.md.
```

### Task 3: Verify Inventory Consistency

**Files:**
- Read: inventory and channel type files
- Create: `tests/unit/test_channel_field_inventory.py`

- [x] **Step 1: Add automated inventory consistency test**

Manual inventories rot. Add `tests/unit/test_channel_field_inventory.py` that parses the inventory markdown table and verifies each row's classification matches the actual file contents:

```python
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "design-docs" / "channel-field-inventory.md"
SHARED_TS = ROOT / "gateway" / "packages" / "shared" / "src" / "types" / "channel.ts"
PROVIDER_TS = ROOT / "gateway" / "packages" / "api" / "src" / "channel" / "provider-config-schema.ts"

ROW_RE = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)


def _parse_rows():
    text = INVENTORY.read_text(encoding="utf-8")
    table_match = re.search(r"## Classification\s*\n(.*?)(?:\n##|\Z)", text, re.DOTALL)
    assert table_match, "Inventory must contain a Classification section"
    return [
        (name.strip(), classification.strip())
        for name, classification in ROW_RE.findall(table_match.group(1))
        if name.strip() not in {"Field or type", "---"}
    ]


def test_frontend_safe_rows_exist_in_shared_ts():
    rows = _parse_rows()
    shared = SHARED_TS.read_text(encoding="utf-8")
    for name, classification in rows:
        if "frontend-safe" in classification:
            assert name in shared, f"frontend-safe `{name}` not found in {SHARED_TS}"


def test_backend_only_provider_rows_exist_in_backend_ts():
    rows = _parse_rows()
    backend = PROVIDER_TS.read_text(encoding="utf-8")
    for name, classification in rows:
        if "backend-only provider schema" in classification:
            assert name in backend, f"backend-only `{name}` not found in {PROVIDER_TS}"


def test_backend_only_rows_are_not_in_shared_ts():
    rows = _parse_rows()
    shared = SHARED_TS.read_text(encoding="utf-8")
    for name, classification in rows:
        if "backend-only" in classification and name not in {
            "config-bearing admin channel create/update bodies",
        }:
            assert name not in shared, (
                f"backend-only `{name}` leaks into shared channel module {SHARED_TS}"
            )
```

This will fail if the inventory drifts from the actual exports in either direction.

- [x] **Step 2: Expand frontend secret-pattern scan**

Run a broader scan (still as a review aid, not a hard guardrail):

```bash
mkdir -p artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-type-field-inventory
rg -n "CHANNEL_CONFIG_SCHEMA|provider-config-schema|accessToken|webhookToken|verifyToken|botToken|signingSecret|refreshToken|apiSecret|clientSecret|privateKey" \
  gateway/packages/web \
  | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-type-field-inventory/frontend-secret-scan.txt
```

Expected: no matches identify *imports*; any matches in user-visible copy must be reviewed and noted in the evidence file.

- [x] **Step 3: Run docs, gateway, and python verification**

```bash
.venv/bin/python -m pytest tests/unit/test_channel_field_inventory.py -v \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-type-field-inventory/inventory-test.log
zsh scripts/check
zsh scripts/verify-surface repo-os-docs gateway-api gateway-web \
  2>&1 | tee artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-type-field-inventory/verify-surface.log
```

Expected: inventory test passes; docs and gateway checks pass.
