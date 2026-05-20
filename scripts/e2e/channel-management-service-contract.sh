#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

evidence_dir="artifacts/evidence/2026-05-19-frontend-platform-channel-boundary/channel-management-service-contract"
jsonl_file="$evidence_dir/e2e-routes.jsonl"
test_log="$evidence_dir/e2e-vitest.log"

mkdir -p "$evidence_dir"
: > "$jsonl_file"
: > "$test_log"

now_ms() {
  date +%s%3N
}

emit() {
  printf '%s\n' "$*"
}

fail() {
  emit "[FAIL $1 $2]"
  exit 1
}

write_jsonl() {
  local action="$1"
  local scenario="$2"
  local expected_status="$3"
  local expected_error="$4"
  local note="$5"

  printf '{"action":"%s","scenario":"%s","expected_status":"%s","expected_error":%s,"source":"static_matrix","note":"%s","ms":0}\n' \
    "$action" \
    "$scenario" \
    "$expected_status" \
    "$expected_error" \
    "$note" >> "$jsonl_file"
}

emit "[BEGIN channel-management-service-contract]"

# @clawscale/api currently has no dev:test server script. This contract check
# therefore runs the in-process Vitest route/service coverage and emits a static
# scenario matrix as JSONL evidence instead of live HTTP request observations.
emit "[STEP vitest-contracts]"
start="$(now_ms)"
if pnpm --dir gateway/packages/api test customer-channel-service customer-channel-routes 2>&1 | tee "$test_log"; then
  elapsed="$(( $(now_ms) - start ))"
  emit "[OK vitest-contracts ${elapsed}ms]"
else
  fail "vitest-contracts" "test_failed"
fi

emit "[STEP scenario-matrix]"
write_jsonl "status" "missing_bearer_token" "401" '"unauthorized"' "route_auth_middleware"
write_jsonl "status" "invalid_or_expired_token" "401" '"invalid_or_expired_token"' "route_auth_middleware"
write_jsonl "status" "account_not_found" "404" '"account_not_found"' "route_auth_middleware_or_service"
write_jsonl "status" "claim_inactive" "403" '"claim_inactive"' "route_auth_middleware"
write_jsonl "create" "account_suspended" "403" '"account_suspended"' "service_access_gate"
write_jsonl "connect" "account_suspended" "403" '"account_suspended"' "service_access_gate"
write_jsonl "create" "email_not_verified" "403" '"email_not_verified"' "service_access_gate"
write_jsonl "connect" "email_not_verified" "403" '"email_not_verified"' "service_access_gate"
write_jsonl "connect" "subscription_required" "402" '"subscription_required"' "service_access_gate"
write_jsonl "create" "subscription_required" "not_402" 'null' "preserves_existing_create_behavior"
write_jsonl "delete" "subscription_required" "not_402" 'null' "cleanup_not_subscription_blocked"
write_jsonl "status" "subscription_required" "not_402" 'null' "read_only_not_subscription_blocked"
write_jsonl "disconnect" "active_account" "200_or_route_specific_error" 'null' "delegates_through_service_boundary"
emit "[OK scenario-matrix 0ms]"

emit "[OK channel-management-service-contract]"
