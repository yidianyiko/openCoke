#!/bin/bash

set -euo pipefail

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="${REMOTE_HOST:-gcp-coke}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/whoami/coke}"
DRY_RUN=false
RESTART=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --restart)
            RESTART=true
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--restart]"
            exit 1
            ;;
    esac
    shift
done

RSYNC_OPTS=(-az --delete --checksum)
if [[ "$DRY_RUN" == "true" ]]; then
    RSYNC_OPTS+=(--dry-run)
fi

ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_ROOT'"

rsync "${RSYNC_OPTS[@]}" \
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
    --exclude='gateway/node_modules/' \
    --exclude='gateway/packages/*/node_modules/' \
    --exclude='gateway/packages/*/.next/' \
    --exclude='gateway/packages/*/dist/' \
    "$LOCAL_ROOT/" \
    "$REMOTE_HOST:$REMOTE_ROOT/"

if [[ "$RESTART" == "true" && "$DRY_RUN" == "false" ]]; then
    ssh "$REMOTE_HOST" "cd '$REMOTE_ROOT' && docker compose -f docker-compose.prod.yml up -d --build --remove-orphans"
fi
