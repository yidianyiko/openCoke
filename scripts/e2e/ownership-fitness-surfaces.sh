#!/usr/bin/env zsh
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/ownership-fitness-surfaces"
evidence_file="$evidence_dir/path-existence.jsonl"
mkdir -p "$evidence_dir"
: > "$evidence_file"
python_cmd="python"
if [[ -x ".venv/bin/python" ]]; then
  python_cmd=".venv/bin/python"
fi

print -r -- "[BEGIN ownership-fitness-surfaces]"
dry_run="$(zsh scripts/verify-surface --dry-run product-reminder product-memo product-calendar-import product-timezone)"

current_surface=""
missing_any=0
while IFS= read -r line; do
  if [[ "$line" =~ '^== .+ ==$' ]]; then
    current_surface="${line#== }"
    current_surface="${current_surface% ==}"
    print -r -- "[STEP $current_surface]"
    continue
  fi
  [[ -z "$line" || "$line" == zsh\ scripts/* ]] && continue

  missing=()
  for token in ${(z)line}; do
    clean="${token%\"}"
    clean="${clean#\"}"
    clean="${clean%\'}"
    clean="${clean#\'}"
    if [[ "$clean" == tests/*.py || "$clean" == memo-runtime/tests || "$clean" == gateway/packages/api/src/*.test.ts ]]; then
      if [[ "$clean" == */ ]]; then
        if [[ ! -d "$clean" || -z "$(find "$clean" -type f \( -name '*.py' -o -name '*.ts' \) -print -quit)" ]]; then
          missing+=("$clean")
        fi
      elif [[ "$clean" == memo-runtime/tests ]]; then
        if [[ ! -d "$clean" || -z "$(find "$clean" -type f -name '*.py' -print -quit)" ]]; then
          missing+=("$clean")
        fi
      elif [[ ! -e "$clean" ]]; then
        missing+=("$clean")
      fi
    fi
  done

  "$python_cmd" - "$current_surface" "$line" "${missing[@]}" >> "$evidence_file" <<'PY'
import json
import sys
surface, command, *missing = sys.argv[1:]
print(json.dumps({"surface": surface, "command": command, "missing_paths": missing}, sort_keys=True))
PY

  if (( ${#missing[@]} )); then
    print -r -- "[FAIL $current_surface ${missing[*]}]"
    missing_any=1
  else
    print -r -- "[OK $current_surface]"
  fi
done <<< "$dry_run"

if [[ "$missing_any" -ne 0 ]]; then
  exit 1
fi

suggest="$(zsh scripts/suggest-verification --files agent/reminder/runtime_contract.py --files agent/timezone_service.py)"
if [[ "$suggest" != *"product-reminder"* || "$suggest" != *"product-timezone"* ]]; then
  print -r -- "[FAIL suggest-verification missing_product_surface]"
  print -r -- "$suggest"
  exit 1
fi

print -r -- "[OK ownership-fitness-surfaces]"
