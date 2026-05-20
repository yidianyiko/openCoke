#!/usr/bin/env zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/system-owners-metadata"
evidence_file="$evidence_dir/e2e.jsonl"
mkdir -p "$evidence_dir"
: > "$evidence_file"
python_cmd="python"
if [[ -x ".venv/bin/python" ]]; then
  python_cmd=".venv/bin/python"
fi

owners=(
  agent/reminder/OWNERS.md
  memo-runtime/OWNERS.md
  connector/clawscale_bridge/OWNERS.md
  agent/agno_agent/OWNERS.md
  gateway/packages/api/src/channel/OWNERS.md
  gateway/packages/web/OWNERS.md
)

print -r -- "[BEGIN system-owners-metadata]"
for path in "${owners[@]}"; do
  print -r -- "[STEP $path]"
  "$python_cmd" - "$path" "$evidence_file" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
evidence = Path(sys.argv[2])
text = path.read_text(encoding="utf-8")
required = [
    "Owns:",
    "Allowed inbound callers:",
    "Verification surfaces:",
    "docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md",
]
missing = [section for section in required if section not in text]
system_match = re.search(r"^Ownership system:\s*(.+)$", text, re.MULTILINE)
system = system_match.group(1).strip() if system_match else ""

def count_bullets_after(label: str) -> int:
    marker = text.index(label)
    rest = text[marker + len(label):]
    next_section = re.search(r"\n[A-Z][A-Za-z ]+:\n", rest)
    if next_section:
        rest = rest[: next_section.start()]
    return len(re.findall(r"^- ", rest, re.MULTILINE))

result = {
    "path": str(path),
    "system": system,
    "sections_present": [section for section in required if section not in missing],
    "missing": missing,
    "allowed_inbound_callers": count_bullets_after("Allowed inbound callers:") if "Allowed inbound callers:" in text else 0,
    "verification_surfaces": count_bullets_after("Verification surfaces:") if "Verification surfaces:" in text else 0,
}
with evidence.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(result, sort_keys=True) + "\n")
print(f"Ownership system: {system}")
print(f"allowed_inbound_callers={result['allowed_inbound_callers']}")
print(f"verification_surfaces={result['verification_surfaces']}")
if missing:
    print("missing=" + ",".join(missing), file=sys.stderr)
    sys.exit(1)
PY
  print -r -- "[OK $path]"
done
print -r -- "[OK system-owners-metadata]"
