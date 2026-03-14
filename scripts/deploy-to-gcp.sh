#!/bin/bash
# deploy-to-gcp.sh - Deploy local code changes to gcp-coke server
#
# Usage:
#   ./scripts/deploy-to-gcp.sh                        # Sync all Python source files
#   ./scripts/deploy-to-gcp.sh --files "a.py b/c.py"  # Sync specific files (relative to project root)
#   ./scripts/deploy-to-gcp.sh --dry-run              # Show what would be synced, no changes
#   ./scripts/deploy-to-gcp.sh --restart              # Sync + restart coke-agent
#   ./scripts/deploy-to-gcp.sh --restart all          # Sync + restart all pm2 services
#
# Examples:
#   ./scripts/deploy-to-gcp.sh --restart
#   ./scripts/deploy-to-gcp.sh --files "util/time_util.py agent/runner/context.py" --restart

set -euo pipefail

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_HOST="gcp-coke"
REMOTE_ROOT="~/coke"

DRY_RUN=false
RESTART_TARGET=""
SPECIFIC_FILES=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --restart)
            RESTART_TARGET="${2:-coke-agent}"
            # Only shift the second arg if it was provided and isn't another flag
            if [[ $# -gt 1 && "$2" != --* ]]; then shift; fi
            ;;
        --files)
            SPECIFIC_FILES="$2"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--restart [service|all]] [--files \"file1 file2\"]"
            exit 1
            ;;
    esac
    shift
done

RSYNC_OPTS="-avz --checksum"
[[ "$DRY_RUN" == "true" ]] && RSYNC_OPTS="$RSYNC_OPTS --dry-run"

echo "==> Deploying from $LOCAL_ROOT to $REMOTE_HOST:$REMOTE_ROOT"
[[ "$DRY_RUN" == "true" ]] && echo "    (dry-run: no changes will be made)"

if [[ -n "$SPECIFIC_FILES" ]]; then
    # Sync specific files preserving directory structure
    for f in $SPECIFIC_FILES; do
        remote_dir="$REMOTE_ROOT/$(dirname "$f")"
        echo "  syncing: $f"
        # shellcheck disable=SC2086
        rsync $RSYNC_OPTS "$LOCAL_ROOT/$f" "$REMOTE_HOST:$remote_dir/"
    done
else
    # Sync entire Python source tree, excluding runtime/secrets/build artifacts
    # shellcheck disable=SC2086
    rsync $RSYNC_OPTS \
        --exclude='.venv/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='conf/' \
        --exclude='logs/' \
        --exclude='data/' \
        --exclude='.git/' \
        --exclude='tests/' \
        --exclude='docs/' \
        --exclude='*.db' \
        --exclude='*.db-shm' \
        --exclude='*.db-wal' \
        "$LOCAL_ROOT/" \
        "$REMOTE_HOST:$REMOTE_ROOT/"
fi

echo "==> Sync complete"

if [[ -n "$RESTART_TARGET" && "$DRY_RUN" == "false" ]]; then
    echo "==> Restarting pm2 service: $RESTART_TARGET"
    if [[ "$RESTART_TARGET" == "all" ]]; then
        ssh "$REMOTE_HOST" "cd $REMOTE_ROOT && ./pm2-manager.sh restart"
    else
        ssh "$REMOTE_HOST" "cd $REMOTE_ROOT && ./pm2-manager.sh restart $RESTART_TARGET"
    fi
    echo "==> Waiting 3s then checking logs..."
    sleep 3
    ssh "$REMOTE_HOST" "pm2 logs coke-agent --lines 20 --nostream"
fi

echo "==> Done"
