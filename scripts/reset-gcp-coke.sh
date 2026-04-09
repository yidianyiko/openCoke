#!/bin/bash

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-gcp-coke}"
REMOTE_ROOT="${REMOTE_ROOT:-/home/whoami/coke}"

ssh "$REMOTE_HOST" 'bash -s' <<EOF
set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT}"

pm2 delete all >/dev/null 2>&1 || true

if [ -f "\$REMOTE_ROOT/docker-compose.prod.yml" ]; then
    docker compose -f "\$REMOTE_ROOT/docker-compose.prod.yml" down -v --remove-orphans || true
fi

for container in mongodb redis clawscale_postgres; do
    docker rm -f "\$container" >/dev/null 2>&1 || true
done

sudo systemctl stop redis-server >/dev/null 2>&1 || true
sudo systemctl disable redis-server >/dev/null 2>&1 || true

rm -rf "\$REMOTE_ROOT"

sudo mkdir -p /var/log/mongodb
sudo find /var/log/mongodb -type f -exec truncate -s 0 {} \; >/dev/null 2>&1 || true
sudo find /var/log/mongodb -type f -name '*.gz' -delete >/dev/null 2>&1 || true

sudo journalctl --vacuum-size=200M >/dev/null 2>&1 || true

df -h /
docker ps -a || true
EOF
