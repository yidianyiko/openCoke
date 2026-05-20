import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "design-docs" / "channel-field-inventory.md"
SHARED_TS = ROOT / "gateway" / "packages" / "shared" / "src" / "types" / "channel.ts"
PROVIDER_TS = (
    ROOT
    / "gateway"
    / "packages"
    / "api"
    / "src"
    / "channel"
    / "provider-config-schema.ts"
)

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
    allowed_text_refs = {"config-bearing admin channel create/update bodies"}
    for name, classification in rows:
        if "backend-only" in classification and name not in allowed_text_refs:
            assert name not in shared, (
                f"backend-only `{name}` leaks into shared channel module {SHARED_TS}"
            )
