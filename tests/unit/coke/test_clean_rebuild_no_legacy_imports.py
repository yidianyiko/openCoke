from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCANNED_TREES = (ROOT / "coke", ROOT / "migrations", ROOT / "tests/unit/coke")
FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(from|import)\s+"
    r"(pymongo|dao|connector|agent|entity|framework|util|memo_runtime|gateway)\b"
)


def test_clean_rebuild_sources_do_not_import_legacy_runtime() -> None:
    violations: list[str] = []
    for tree in SCANNED_TREES:
        for path in sorted(tree.rglob("*.py")):
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if FORBIDDEN_IMPORT_RE.match(line):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}"
                    )

    assert violations == []
