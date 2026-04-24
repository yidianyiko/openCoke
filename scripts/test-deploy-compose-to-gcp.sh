#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_SCRIPT="$REPO_ROOT/scripts/deploy-compose-to-gcp.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  if [[ "$haystack" != *"$needle"* ]]; then
    fail "expected to find [$needle] in [$haystack]"
  fi
}

assert_equals() {
  local actual="$1"
  local expected="$2"
  if [[ "$actual" != "$expected" ]]; then
    fail "expected [$expected], got [$actual]"
  fi
}

make_fake_repo() {
  local root="$1"
  mkdir -p \
    "$root/scripts" \
    "$root/gateway/packages/web/app/dashboard" \
    "$root/gateway/packages/web/app/(customer)/auth/login" \
    "$root/gateway/packages/web/app/(customer)/auth/register" \
    "$root/gateway/packages/web/app/(customer)/channels/wechat-personal" \
    "$root/gateway/packages/web/app/(customer)/account/subscription" \
    "$root/gateway/packages/web/components" \
    "$root/gateway/packages/web/app/(admin)/admin/shared-channels/detail" \
    "$root/gateway/packages/api/src/routes"
  cp "$SOURCE_SCRIPT" "$root/scripts/deploy-compose-to-gcp.sh"
  chmod +x "$root/scripts/deploy-compose-to-gcp.sh"
  cat >"$root/gateway/packages/web/app/page.tsx" <<'EOF'
export default function HomePage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/components/coke-homepage.tsx" <<'EOF'
export function CokeHomepage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/dashboard/page.tsx" <<'EOF'
export default function DashboardPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/(customer)/auth/login/page.tsx" <<'EOF'
export default function CustomerLoginPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/(customer)/auth/register/page.tsx" <<'EOF'
export default function CustomerRegisterPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx" <<'EOF'
export default function CustomerWechatPersonalPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/(customer)/account/subscription/page.tsx" <<'EOF'
export default function CustomerSubscriptionPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/web/app/(admin)/admin/shared-channels/detail/page.tsx" <<'EOF'
export default function SharedChannelDetailPage() {
  return null;
}
EOF
  cat >"$root/gateway/packages/api/src/index.ts" <<'EOF'
export {};
EOF
  cat >"$root/gateway/packages/api/src/routes/customer-auth-routes.ts" <<'EOF'
export {};
EOF
  cat >"$root/gateway/packages/api/src/routes/customer-channel-routes.ts" <<'EOF'
export {};
EOF
  cat >"$root/gateway/packages/api/src/routes/customer-subscription-routes.ts" <<'EOF'
export {};
EOF
}

make_stub_bin() {
  local root="$1"
  mkdir -p "$root/stubs"

  cat >"$root/stubs/git" <<'EOF'
#!/bin/bash
set -euo pipefail

  if [[ "$#" -ge 5 && "$1" == "-C" && "$3" == "ls-tree" && "$4" == "HEAD" && "$5" == "gateway" ]]; then
    echo "160000 commit ${EXPECTED_GATEWAY_COMMIT}	gateway"
    exit 0
  fi

  if [[ "$#" -ge 3 && "$1" == "ls-tree" && "$2" == "HEAD" && "$3" == "gateway" ]]; then
    echo "160000 commit ${EXPECTED_GATEWAY_COMMIT}	gateway"
    exit 0
  fi

if [[ "$#" -ge 4 && "$1" == "-C" && "$3" == "rev-parse" && "$4" == "HEAD" ]]; then
  echo "${ACTUAL_GATEWAY_COMMIT}"
  exit 0
fi

echo "unexpected git invocation: $*" >&2
exit 1
EOF
  chmod +x "$root/stubs/git"

  cat >"$root/stubs/ssh" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'ssh %s\n' "$*" >>"${CALLS_LOG}"
if [[ "$*" == *"app/dashboard/layout.tsx"* ]]; then
  echo "stale dashboard layout verification path" >&2
  exit 1
fi
exit 0
EOF
  chmod +x "$root/stubs/ssh"

  cat >"$root/stubs/rsync" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'rsync %s\n' "$*" >>"${CALLS_LOG}"
exit 0
EOF
  chmod +x "$root/stubs/rsync"

  cat >"$root/stubs/curl" <<'EOF'
#!/bin/bash
set -euo pipefail
printf 'curl %s\n' "$*" >>"${CALLS_LOG}"

if [[ "$*" == *"-w '%{http_code}'"* || "$*" == *'-w %{http_code}'* ]]; then
  if [[ "$*" == *"/auth/login"* ]]; then
    printf '200'
    exit 0
  fi

  if [[ "$*" == *"/auth/register"* ]]; then
    printf '200'
    exit 0
  fi

  if [[ "$*" == *"/login"* ]]; then
    printf '404'
    exit 0
  fi

  if [[ "$*" == *"/coke/login"* ]]; then
    printf '404'
    exit 0
  fi

  if [[ "$*" == *"/api/coke/auth/login"* ]]; then
    printf '404'
    exit 0
  fi
fi

cat <<'OUT'
Kap AI
Plan meetings, reminders, and the next move in one thread.
__COKE_LOCALE__
<img src="/kap-koala-hero.png" alt="Kap koala mascot" />
<a href="/channels/wechat-personal">WeChat channel</a>
<a href="/account/subscription">Subscription</a>
OUT
EOF
  chmod +x "$root/stubs/curl"
}

run_mismatch_case() {
  local root
  root="$(mktemp -d)"
  trap 'rm -rf "$root"' RETURN

  make_fake_repo "$root"
  make_stub_bin "$root"

  export EXPECTED_GATEWAY_COMMIT="expected-gateway-commit"
  export ACTUAL_GATEWAY_COMMIT="stale-gateway-commit"
  export CALLS_LOG="$root/calls.log"
  : >"$CALLS_LOG"

  if PATH="$root/stubs:$PATH" "$root/scripts/deploy-compose-to-gcp.sh" --dry-run >"$root/stdout.log" 2>"$root/stderr.log"; then
    fail "expected mismatch case to fail"
  fi

  if [[ -s "$CALLS_LOG" ]]; then
    fail "mismatch case should fail before ssh/rsync calls"
  fi
}

run_two_phase_sync_case() {
  local root
  root="$(mktemp -d)"
  trap 'rm -rf "$root"' RETURN

  make_fake_repo "$root"
  make_stub_bin "$root"

  export EXPECTED_GATEWAY_COMMIT="fresh-gateway-commit"
  export ACTUAL_GATEWAY_COMMIT="fresh-gateway-commit"
  export CALLS_LOG="$root/calls.log"
  : >"$CALLS_LOG"

  PATH="$root/stubs:$PATH" PUBLIC_BASE_URL="https://coke.ydyk123.top" \
    "$root/scripts/deploy-compose-to-gcp.sh" --restart >"$root/stdout.log" 2>"$root/stderr.log"

  local rsync_count
  rsync_count="$(grep -c '^rsync ' "$CALLS_LOG" || true)"
  assert_equals "$rsync_count" "2"

  local call_log
  call_log="$(cat "$CALLS_LOG")"
  assert_contains "$call_log" "--exclude=gateway/"
  assert_contains "$call_log" "gateway/"
  assert_contains "$call_log" "auth/login/page.tsx"
  assert_contains "$call_log" "auth/register/page.tsx"
  assert_contains "$call_log" "channels/wechat-personal/page.tsx"
  assert_contains "$call_log" "account/subscription/page.tsx"
  assert_contains "$call_log" "customer-auth-routes.ts"
  assert_contains "$call_log" "customer-channel-routes.ts"
  assert_contains "$call_log" "customer-subscription-routes.ts"
  assert_contains "$call_log" "curl "
  assert_contains "$call_log" "/auth/login"
  assert_contains "$call_log" "/auth/register"
  assert_contains "$call_log" "/login"
  assert_contains "$call_log" "/coke/login"
  assert_contains "$call_log" "/api/coke/auth/login"
}

run_mismatch_case
run_two_phase_sync_case

echo "PASS: deploy-compose-to-gcp regression checks"
