#!/usr/bin/env zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/route-contract-ownership-registry"
evidence_file="$evidence_dir/e2e-perturbations.jsonl"
mkdir -p "$evidence_dir"
: > "$evidence_file"

registry="docs/fitness/ownership-registry.yaml"
tmp="$(mktemp)"
cp "$registry" "$tmp"
trap 'rm -f "$tmp"' EXIT
python_cmd="python"
if [[ -x ".venv/bin/python" ]]; then
  python_cmd=".venv/bin/python"
fi

json_escape() {
  print -r -- "$1" | "$python_cmd" -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))'
}

run_case() {
  local scenario="$1"
  local expected="$2"
  shift 2

  cp "$registry" "$tmp"
  "$@" "$tmp"

  print -r -- "[STEP $scenario]"
  set +e
  output="$("$python_cmd" scripts/guardrails.py check-ownership-registry --registry "$tmp" 2>&1)"
  code=$?
  set -e

  if [[ "$code" -eq 0 || "$output" != *"$expected"* ]]; then
    print -r -- "{\"scenario\":$(json_escape "$scenario"),\"exit_code\":$code,\"matched_error\":false}" >> "$evidence_file"
    print -r -- "[FAIL $scenario expected_error_not_matched]"
    print -r -- "$output"
    exit 1
  fi

  print -r -- "{\"scenario\":$(json_escape "$scenario"),\"exit_code\":$code,\"matched_error\":true}" >> "$evidence_file"
  print -r -- "[OK $scenario]"
}

invalid_owner() {
  "$python_cmd" - "$1" <<'PY'
from pathlib import Path
import yaml
path = Path(__import__("sys").argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8"))
data["routes"][0]["owner"] = "made-up"
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
}

missing_file() {
  "$python_cmd" - "$1" <<'PY'
from pathlib import Path
import yaml
path = Path(__import__("sys").argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8"))
data["routes"].append({
    "path": "gateway/packages/api/src/routes/does-not-exist.ts",
    "owner": "platform",
})
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
}

unregistered_route() {
  "$python_cmd" - "$1" <<'PY'
from pathlib import Path
import yaml
path = Path(__import__("sys").argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8"))
target = "gateway/packages/api/src/routes/customer-subscription-routes.ts"
data["routes"] = [route for route in data["routes"] if route.get("path") != target]
path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
PY
}

print -r -- "[BEGIN route-contract-ownership-registry]"
run_case invalid-owner "invalid owner made-up" invalid_owner
run_case missing-file "missing file" missing_file
run_case unregistered-route "missing route entry" unregistered_route
print -r -- "[OK route-contract-ownership-registry]"
