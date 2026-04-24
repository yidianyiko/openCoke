#!/bin/bash

set -euo pipefail

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-gcp-coke}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/whoami/coke}"
DRY_RUN=false
RESTART=false
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"

usage() {
    echo "Usage: $0 [--dry-run] [--restart] [--public-base-url <url>]"
}

shell_quote() {
    printf '%q' "$1"
}

log() {
    echo "[deploy] $*"
}

expected_gateway_commit() {
    git -C "$LOCAL_ROOT" ls-tree HEAD gateway | awk '{print $3}'
}

actual_gateway_commit() {
    git -C "$LOCAL_ROOT/gateway" rev-parse HEAD
}

verify_gateway_submodule_match() {
    if [[ ! -d "$LOCAL_ROOT/gateway" ]]; then
        echo "Local gateway checkout is missing: $LOCAL_ROOT/gateway" >&2
        exit 1
    fi

    local expected actual
    expected="$(expected_gateway_commit)"
    actual="$(actual_gateway_commit)"

    if [[ -z "$expected" || -z "$actual" ]]; then
        echo "Unable to determine gateway submodule commit state." >&2
        exit 1
    fi

    if [[ "$expected" != "$actual" ]]; then
        echo "Gateway submodule mismatch." >&2
        echo "  Root repo expects: $expected" >&2
        echo "  Local gateway has: $actual" >&2
        echo "Update the local gateway checkout before deploying." >&2
        exit 1
    fi
}

remote_env_public_base_url() {
    ssh "$REMOTE_HOST" "if [ -f '$(shell_quote "$REMOTE_ROOT/.env")' ]; then grep -E '^DOMAIN_CLIENT=' '$(shell_quote "$REMOTE_ROOT/.env")' | tail -n 1 | cut -d= -f2-; fi" \
        | tr -d '\r'
}

update_remote_public_env() {
    if [[ -z "$PUBLIC_BASE_URL" ]]; then
        return
    fi

    local quoted_root quoted_env quoted_public
    quoted_root="$(shell_quote "$REMOTE_ROOT")"
    quoted_env="$(shell_quote "$REMOTE_ROOT/.env")"
    quoted_public="$(shell_quote "$PUBLIC_BASE_URL")"

    log "Updating remote public URL envs to $PUBLIC_BASE_URL"
    ssh "$REMOTE_HOST" "
        set -euo pipefail
        file=$quoted_env
        [ -f \"\$file\" ] || { echo 'Missing remote .env file' >&2; exit 1; }
        update_env() {
            key=\"\$1\"
            value=\"\$2\"
            if grep -q \"^\${key}=\" \"\$file\"; then
                sed -i \"s|^\${key}=.*|\${key}=\${value}|\" \"\$file\"
            else
                printf '%s=%s\n' \"\$key\" \"\$value\" >> \"\$file\"
            fi
        }
        update_env DOMAIN_CLIENT $quoted_public
        update_env CORS_ORIGIN $quoted_public
        update_env NEXT_PUBLIC_API_URL $quoted_public
        update_env NEXT_PUBLIC_COKE_API_URL $quoted_public
        grep -E '^(DOMAIN_CLIENT|CORS_ORIGIN|NEXT_PUBLIC_API_URL|NEXT_PUBLIC_COKE_API_URL)=' \"\$file\"
    "
}

sync_root_repo() {
    local rsync_opts=("$@")
    rsync "${rsync_opts[@]}" \
        --exclude='.git/' \
        --exclude='.gitmodules' \
        --exclude='.worktrees/' \
        --exclude='.venv/' \
        --exclude='.pytest_cache/' \
        --exclude='.DS_Store' \
        --exclude='.env' \
        --exclude='.env.*' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='htmlcov/' \
        --exclude='logs/' \
        --exclude='data/' \
        --exclude='agent/temp/' \
        --exclude='gateway/' \
        "$LOCAL_ROOT/" \
        "$REMOTE_HOST:$REMOTE_ROOT/"
}

sync_gateway_submodule() {
    local rsync_opts=("$@")
    rsync "${rsync_opts[@]}" \
        --exclude='.git' \
        --exclude='.git/' \
        --exclude='node_modules/' \
        --exclude='packages/*/node_modules/' \
        --exclude='packages/*/.next/' \
        --exclude='packages/*/dist/' \
        --exclude='packages/*/out/' \
        "$LOCAL_ROOT/gateway/" \
        "$REMOTE_HOST:$REMOTE_ROOT/gateway/"
}

verify_remote_source_tree() {
    log "Verifying remote gateway source tree"
    ssh "$REMOTE_HOST" "
        set -euo pipefail
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/app/page.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/components/coke-homepage.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/app/(customer)/auth/login/page.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/app/(customer)/auth/register/page.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/app/(customer)/channels/wechat-personal/page.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/web/app/(customer)/account/subscription/page.tsx")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/api/src/index.ts")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/api/src/routes/customer-auth-routes.ts")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/api/src/routes/customer-channel-routes.ts")
        test -f $(shell_quote "$REMOTE_ROOT/gateway/packages/api/src/routes/customer-subscription-routes.ts")
    "
}

verify_remote_runtime() {
    log "Verifying remote health endpoints"
    ssh "$REMOTE_HOST" "
        set -euo pipefail
        curl -fsS http://127.0.0.1:4041/health >/dev/null
        curl -fsS http://127.0.0.1:8090/bridge/healthz >/dev/null
    "
}

verify_public_site() {
    local public_url="$1"
    if [[ -z "$public_url" ]]; then
        echo "Public base URL is empty; cannot verify public site." >&2
        exit 1
    fi

    log "Verifying public site at $public_url"
    ssh "$REMOTE_HOST" "
        set -euo pipefail
        homepage=\$(curl -fsS $(shell_quote "$public_url/"))
        login_page=\$(curl -fsS $(shell_quote "$public_url/auth/login"))
        register_page=\$(curl -fsS $(shell_quote "$public_url/auth/register"))
        login_status=\$(curl -k -s -o /dev/null -w '%{http_code}' $(shell_quote "$public_url/auth/login"))
        register_status=\$(curl -k -s -o /dev/null -w '%{http_code}' $(shell_quote "$public_url/auth/register"))
        old_login_status=\$(curl -k -s -o /dev/null -w '%{http_code}' $(shell_quote "$public_url/login"))
        old_web_namespace_status=\$(curl -k -s -o /dev/null -w '%{http_code}' $(shell_quote "$public_url/coke/login"))
        old_api_namespace_status=\$(curl -k -s -o /dev/null -w '%{http_code}' $(shell_quote "$public_url/api/coke/auth/login"))
        printf '%s' \"\$homepage\" | grep -q '__COKE_LOCALE__'
        printf '%s' \"\$homepage\" | grep -q 'href=\"/auth/login\"'
        printf '%s' \"\$homepage\" | grep -q 'href=\"/auth/register\"'
        printf '%s' \"\$homepage\" | grep -q 'href=\"/channels/wechat-personal\"'
        printf '%s' \"\$homepage\" | grep -q 'href=\"/account/subscription\"'
        printf '%s' \"\$homepage\" | grep -q 'href=\"/login\"' && exit 1 || true
        printf '%s' \"\$homepage\" | grep -q 'href=\"/coke/login\"' && exit 1 || true
        printf '%s' \"\$homepage\" | grep -q '/api/coke/auth/login' && exit 1 || true
        printf '%s' \"\$login_page\" | grep -q '__COKE_LOCALE__'
        printf '%s' \"\$register_page\" | grep -q '__COKE_LOCALE__'
        test \"\$login_status\" = '200'
        test \"\$register_status\" = '200'
        test \"\$old_login_status\" = '404'
        test \"\$old_web_namespace_status\" = '404'
        test \"\$old_api_namespace_status\" = '404'
    "
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --restart)
            RESTART=true
            ;;
        --public-base-url)
            shift
            if [[ $# -eq 0 ]]; then
                echo "--public-base-url requires a value" >&2
                usage
                exit 1
            fi
            PUBLIC_BASE_URL="$1"
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

verify_gateway_submodule_match

RSYNC_OPTS=(-az --delete --checksum)
if [[ "$DRY_RUN" == "true" ]]; then
    RSYNC_OPTS+=(--dry-run)
fi

log "Ensuring remote deploy directories exist"
ssh "$REMOTE_HOST" "mkdir -p '$(shell_quote "$REMOTE_ROOT")' '$(shell_quote "$REMOTE_ROOT/gateway")'"

log "Syncing root repository"
sync_root_repo "${RSYNC_OPTS[@]}"

log "Syncing gateway submodule"
sync_gateway_submodule "${RSYNC_OPTS[@]}"

if [[ "$DRY_RUN" == "false" ]]; then
    verify_remote_source_tree
    update_remote_public_env
fi

if [[ "$RESTART" == "true" && "$DRY_RUN" == "false" ]]; then
    log "Restarting remote compose stack"
    ssh "$REMOTE_HOST" "cd '$(shell_quote "$REMOTE_ROOT")' && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans"

    verify_remote_runtime

    if [[ -z "$PUBLIC_BASE_URL" ]]; then
        PUBLIC_BASE_URL="$(remote_env_public_base_url)"
    fi
    verify_public_site "$PUBLIC_BASE_URL"
fi

log "Deploy script completed"
