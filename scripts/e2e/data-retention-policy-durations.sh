#!/usr/bin/env zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/data-retention-policy-durations"
coverage_file="$evidence_dir/coverage.json"
mkdir -p "$evidence_dir"

python_cmd="python"
if [[ -x ".venv/bin/python" ]]; then
  python_cmd=".venv/bin/python"
fi

print -r -- "[BEGIN data-retention-policy-durations]"
"$python_cmd" - "$coverage_file" <<'PY'
import json
import re
import sys
from pathlib import Path

coverage_file = Path(sys.argv[1])
spec = Path("docs/superpowers/specs/2026-05-19-frontend-platform-channel-boundary-design.md")
policy = Path("docs/design-docs/data-retention-policy.md")
spec_text = spec.read_text(encoding="utf-8")
policy_text = policy.read_text(encoding="utf-8")
names = sorted(set(re.findall(r"`([a-z][a-z_]+_retention)`", spec_text)))
rows = {}
for line in policy_text.splitlines():
    match = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|", line)
    if match:
        rows[match.group(1)] = {
            "duration": match.group(2).strip(),
            "owner": match.group(3).strip(),
            "evidence": match.group(4).strip(),
        }

coverage = []
for name in names:
    print(f"[STEP {name}]")
    row = rows.get(name)
    if not row or not row["duration"] or not row["owner"] or not row["evidence"]:
        print(f"[FAIL {name} missing_policy_row]")
        coverage_file.write_text(json.dumps({"policies": coverage}, indent=2) + "\n")
        raise SystemExit(1)
    print(
        f"policy={name} duration={row['duration']} owner={row['owner']} "
        f"evidence={row['evidence']}"
    )
    print(f"[OK {name}]")
    coverage.append({"policy": name, **row})

coverage_file.write_text(json.dumps({"policies": coverage}, indent=2, sort_keys=True) + "\n")
PY
print -r -- "[OK data-retention-policy-durations]"
