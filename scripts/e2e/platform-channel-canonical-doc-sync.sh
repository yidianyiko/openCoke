#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

BOUNDARY_SPEC = "docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md"
EVIDENCE_DIR = Path(
    "artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/"
    "platform-channel-canonical-doc-sync"
)
LINK_CHECK_JSON = EVIDENCE_DIR / "link-check.json"
LINK_CHECK_JSONL = EVIDENCE_DIR / "link-check.jsonl"

DOCS = [
    Path("docs/ARCHITECTURE.md"),
    Path("docs/design-docs/interface-contract.md"),
    Path("docs/product-specs/FEATURE_TREE.md"),
    Path("docs/design-docs/coke-working-contract.md"),
]

OWNER_LABELS = {
    "/api/customer/reminders": "Reminder System",
    "/api/customer/channels/wechat-personal": "Channel semantics",
    "/api/customer/google-calendar-import": "Calendar Import System",
    "/api/customer/calendar-import-handoffs": "Calendar Import System",
}

STALE_SHORTCUTS = [
    "gateway-owned",
    "Bridge-owned product",
    "automatically owned by Platform",
    "not automatically owned",
    "handles user auth, bind flow",
    "bind and account lifecycle endpoints implemented by the bridge app",
    "owns shared-channel admin/config state",
    "owns provider webhook verification and normalization",
    "owns shared-customer provisioning and delivery-route binding",
    "owns provider-specific outbound delivery through `/api/outbound`",
]

results = []


def emit(line: str) -> None:
    print(line, flush=True)


def write_evidence() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    LINK_CHECK_JSON.write_text(
        json.dumps({"results": results}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    LINK_CHECK_JSONL.write_text(
        "".join(json.dumps(result, sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )


def fail(doc: str, reason: str) -> None:
    emit(f"[FAIL {doc} {reason}]")
    write_evidence()
    sys.exit(1)


def check_doc(doc: Path) -> None:
    emit(f"[STEP {doc}]")
    text = doc.read_text(encoding="utf-8")
    required_refs = [BOUNDARY_SPEC, "Ownership"]
    found_refs = [ref for ref in required_refs if ref in text]
    missing_refs = [ref for ref in required_refs if ref not in text]
    results.append(
        {
            "doc": str(doc),
            "missing_refs": missing_refs,
            "found_refs": found_refs,
        }
    )
    if missing_refs:
        fail(str(doc), "missing " + ", ".join(missing_refs))
    emit(f"[OK {doc}]")


def check_owner_labels() -> None:
    doc = Path("docs/design-docs/interface-contract.md")
    emit(f"[STEP {doc} owner-labels]")
    text = doc.read_text(encoding="utf-8")
    missing = []
    for route, owner in OWNER_LABELS.items():
        pattern = rf"^- `{re.escape(route)}` .*{re.escape(owner)}"
        if not re.search(pattern, text, flags=re.MULTILINE):
            missing.append(f"{route} -> {owner}")
    results.append(
        {
            "doc": str(doc),
            "missing_refs": missing,
            "found_refs": [f"{route} -> {owner}" for route, owner in OWNER_LABELS.items() if f"{route} -> {owner}" not in missing],
        }
    )
    if missing:
        fail(str(doc), "missing owner labels: " + "; ".join(missing))
    emit(f"[OK {doc} owner-labels]")


def check_bridge_claim() -> None:
    emit("[STEP stale-ownership-shortcuts]")
    stale_hits = []
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for shortcut in STALE_SHORTCUTS:
            if shortcut in text:
                stale_hits.append(f"{doc}: {shortcut}")
    results.append(
        {
            "doc": "canonical-docs",
            "missing_refs": stale_hits,
            "found_refs": ["no stale bridge auth/bind or ownership shortcut claims"] if not stale_hits else [],
        }
    )
    if stale_hits:
        fail("canonical-docs", "stale ownership shortcut remains: " + "; ".join(stale_hits))
    emit("[OK stale-ownership-shortcuts]")


emit("[BEGIN platform-channel-canonical-doc-sync]")
for doc in DOCS:
    check_doc(doc)
check_owner_labels()
check_bridge_claim()
write_evidence()
emit("[OK platform-channel-canonical-doc-sync]")
PY
