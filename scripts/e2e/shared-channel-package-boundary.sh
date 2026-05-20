#!/usr/bin/env zsh

set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/shared-channel-package-boundary"
evidence_file="$evidence_dir/bundle-scan.txt"
bundle_dir="gateway/packages/web/.next"

mkdir -p "$evidence_dir"
: > "$evidence_file"

log() {
  print -r -- "$*" | tee -a "$evidence_file"
}

fail() {
  log "[FAIL $1 $2]"
  exit 1
}

log "[BEGIN shared-channel-package-boundary]"

log "[STEP clean-build-output]"
rm -rf "$bundle_dir"
log "[OK clean-build-output]"

log "[STEP web-build]"
if pnpm --dir gateway/packages/web build 2>&1 | tee -a "$evidence_file"; then
  log "[OK web-build]"
else
  fail "web-build" "build_failed"
fi

if [[ ! -d "$bundle_dir" ]]; then
  fail "bundle-output" "missing_${bundle_dir}"
fi

log "[STEP bundle-scan]"
typeset -a sentinel_patterns=(
  "CHANNEL_CONFIG_SCHEMA"
  "provider-config-schema"
  "key['\"]?[[:space:]]*:[[:space:]]*['\"]phoneNumberId['\"][^[:cntrl:]]*key['\"]?[[:space:]]*:[[:space:]]*['\"]accessToken['\"][^[:cntrl:]]*key['\"]?[[:space:]]*:[[:space:]]*['\"]verifyToken['\"]"
  "key['\"]?[[:space:]]*:[[:space:]]*['\"]appId['\"][^[:cntrl:]]*key['\"]?[[:space:]]*:[[:space:]]*['\"]token['\"][^[:cntrl:]]*key['\"]?[[:space:]]*:[[:space:]]*['\"]baseUrl['\"]"
  "key['\"]?[[:space:]]*:[[:space:]]*['\"]fromNumber['\"]"
)

hits=0
for pattern in "${sentinel_patterns[@]}"; do
  if grep -RIE --exclude-dir=cache --exclude="*.map" "$pattern" "$bundle_dir" >> "$evidence_file"; then
    log "[FAIL bundle-scan sentinel=${pattern}]"
    hits=1
  fi
done

if [[ "$hits" -ne 0 ]]; then
  exit 1
fi

log "[OK bundle-scan]"
log "[OK shared-channel-package-boundary]"
