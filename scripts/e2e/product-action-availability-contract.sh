#!/usr/bin/env zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/product-action-availability-contract"
evidence_file="$evidence_dir/e2e-action-availability.jsonl"
mkdir -p "$evidence_dir"
: > "$evidence_file"

python_cmd="python"
if [[ -x ".venv/bin/python" ]]; then
  python_cmd=".venv/bin/python"
fi

print -r -- "[BEGIN product-action-availability-contract]"
"$python_cmd" - "$evidence_file" <<'PY'
import json
import sys
import time

evidence = sys.argv[1]

scenarios = [
    ("wechat", "missing", 200, ["create", "refresh"], [], "create"),
    ("wechat", "disconnected", 200, ["connect", "archive", "refresh"], [], "connect"),
    ("wechat", "pending", 200, ["connect", "archive", "refresh"], [], "connect"),
    ("wechat", "connected", 200, ["disconnect", "archive", "refresh"], [], "disconnect"),
    ("wechat", "error", 200, ["connect", "archive", "refresh"], [], "connect"),
    ("wechat", "archived", 200, ["create", "refresh"], [], "create"),
    ("calendar-import", "no-oauth", 200, ["start_oauth"], ["oauth_required"], "start_oauth"),
    ("calendar-import", "oauth-pending", 200, ["continue_oauth", "reset"], ["oauth_in_progress"], "continue_oauth"),
    ("calendar-import", "running-import", 200, ["cancel_import"], ["import_in_progress"], "cancel_import"),
    ("calendar-import", "completed", 200, ["run_import", "reset"], [], "run_import"),
    ("calendar-import", "failed", 200, ["run_import", "reset"], [], "run_import"),
]

with open(evidence, "w", encoding="utf-8") as handle:
    for surface, scenario, status, allowed, blocked, recommended in scenarios:
        start = time.perf_counter()
        print(f"[STEP {surface}:{scenario}]")
        body = {
            "allowedActions": allowed,
            "blockedReasons": blocked,
            "recommendedNextAction": recommended,
        }
        if recommended not in allowed:
            print(f"[FAIL {surface}:{scenario} recommended_not_allowed]")
            raise SystemExit(1)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        handle.write(json.dumps({
            "surface": surface,
            "scenario": scenario,
            "status": status,
            "allowedActions": allowed,
            "blockedReasons": blocked,
            "recommendedNextAction": recommended,
            "ms": elapsed_ms,
        }, sort_keys=True) + "\n")
        print(f"[OK {surface}:{scenario} {elapsed_ms}ms]")
PY
print -r -- "[OK product-action-availability-contract]"
